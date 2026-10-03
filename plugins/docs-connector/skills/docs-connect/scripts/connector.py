#!/usr/bin/env python3
"""
connector.py — pull a company's documents from a REMOTE store into a local mirror,
then link the mirror to a brain. The networked half of the document-store sources.

The Second Brain Link engine never touches the network: its `git_docs` and
`google_drive` sources only ever READ a local folder (read-only, through a
`_SOURCE_LINK.json`). This plugin is the separate, network-declaring surface that
fills such a folder from a remote:

  git     clone / fast-forward pull a repository the user names (their own git
          credentials — SSH agent or credential helper; a URL with an embedded
          password is refused)
  drive   Google Drive API v3, read-only scope, with the user's OWN OAuth client
          (a "Desktop app" client from their Google Cloud project). Native Docs /
          Sheets / Slides are exported to .docx / .xlsx / .pptx; everything else is
          downloaded as is. Incremental: unchanged files are not downloaded again.

The mirror lives OUTSIDE the data folder (default ~/.second-brain/sources/<entity>/
<source>/mirror) so no other adapter ever sees it; the link file in
data/company/<entity>/<source>/ points at it with mode "connector", and the
metadata sidecar `_SOURCE_MANIFEST.json` (sbl-source-manifest/1 — ids, mime types,
dates, sizes, owners' DISPLAY NAMES; never e-mail addresses, never tokens) sits next
to the link file. Then reseed: the engine's scanner tiers every file as usual.

    python3 connector.py add-git   --data <data-dir> --entity <slug> --url <remote> [--branch main]
    python3 connector.py add-drive --data <data-dir> --entity <slug> --folder <folder-id|root>
                                   --client-secret <client_secret.json> [--shared-drive <id>]
    python3 connector.py auth-drive --client-secret <client_secret.json>
    python3 connector.py sync      --data <data-dir> [--entity <slug>] [--source git_docs|google_drive]
    python3 connector.py status    --data <data-dir>

Stdlib only. Tokens: ~/.second-brain/connectors/google_drive/token.json (mode 0600) —
or, inside Second Brain Studio, the app's encrypted store hands the token in through
$SBL_DRIVE_TOKEN_FILE.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

LINK_NAME = "_SOURCE_LINK.json"
MANIFEST_NAME = "_SOURCE_MANIFEST.json"
LINK_SCHEMA = "sbl-source-link/1"
MANIFEST_SCHEMA = "sbl-source-manifest/1"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_API = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.I)
EXPORTS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
}
SKIP_NATIVE = {"application/vnd.google-apps.form", "application/vnd.google-apps.map",
               "application/vnd.google-apps.site", "application/vnd.google-apps.shortcut",
               "application/vnd.google-apps.jam", "application/vnd.google-apps.script"}
FOLDER_MIME = "application/vnd.google-apps.folder"
MAX_FILE_BYTES = 200 * 1024 * 1024


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def home():
    return Path(os.environ.get("SBL_CONNECTOR_HOME") or (Path.home() / ".second-brain"))


def new_link_id():
    return base64.b32encode(uuid.uuid4().bytes).decode("ascii").rstrip("=").lower()


def mirror_dir(entity, source, override=None):
    if override:
        return Path(os.path.expanduser(override)).resolve()
    return (home() / "sources" / entity / source / "mirror").resolve()


def link_dir(data, entity, source):
    return Path(os.path.expanduser(data)).resolve() / "company" / entity / source


def _check_entity(entity):
    if not NAME_RE.match(entity or ""):
        raise SystemExit(f"entity must be a folder-safe slug (got {entity!r})")


def _guard_mirror(mirror, data):
    m = Path(mirror).resolve()
    d = Path(os.path.expanduser(data)).resolve()
    if m == d or d in m.parents or m in d.parents:
        raise SystemExit("the mirror must live OUTSIDE the data folder (and must not contain it)")


def write_link(data, entity, source, mirror, label, remote):
    d = link_dir(data, entity, source)
    d.mkdir(parents=True, exist_ok=True)
    lf = d / LINK_NAME
    prev = {}
    if lf.is_file():
        try:
            prev = json.loads(lf.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    rules = prev.get("rules") or {}
    for k in ("sensitivity", "taxonomy"):
        if (d / "rules" / f"{k}.json").is_file():
            rules[k] = f"rules/{k}.json"
    link = {"schema": LINK_SCHEMA, "kind": source, "id": prev.get("id") or new_link_id(),
            "label": label or prev.get("label") or f"{entity} {source.replace('_', ' ')}",
            "root": str(mirror), "mode": "connector", "layout": "auto",
            "include": prev.get("include") or ["**"], "exclude": prev.get("exclude") or [],
            "vcs": "auto", "copy_files": True,
            "max_copy_bytes": prev.get("max_copy_bytes") or 25 * 1024 * 1024,
            "max_total_copy_bytes": prev.get("max_total_copy_bytes") or 2 * 1024 ** 3,
            "rules": rules,
            "connector": {"plugin": "docs-connector", "remote": remote,
                          "manifest": MANIFEST_NAME if source == "google_drive" else None,
                          "last_sync": (prev.get("connector") or {}).get("last_sync")},
            "created": prev.get("created") or now_iso(), "created_by": "docs-connector"}
    lf.write_text(json.dumps(link, indent=2) + "\n", encoding="utf-8")
    return lf


def _mark_synced(data, entity, source, ok, note=""):
    lf = link_dir(data, entity, source) / LINK_NAME
    link = json.loads(lf.read_text(encoding="utf-8"))
    c = link.get("connector") or {}
    if ok:
        c["last_sync"] = now_iso()
    c["last_result"] = ("ok" if ok else "failed") + (f" — {note}" if note else "")
    link["connector"] = c
    lf.write_text(json.dumps(link, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------

def _redact_url(url):
    """Never store or print credentials embedded in a URL."""
    return re.sub(r"(://)[^/@]+@", r"\1", url)


def check_git_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme in ("http", "https") and ("@" in p.netloc):
        raise SystemExit("refusing a URL with embedded credentials — use your git credential "
                         "helper or an SSH remote instead")
    if not url or url.startswith("-"):
        raise SystemExit("bad repository URL")
    return url


def _git(args, cwd=None, timeout=1800):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    r = subprocess.run(["git", *args], cwd=cwd, env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[-400:])
    return r.stdout.decode("utf-8", "replace")


def sync_git(mirror, url, branch=None):
    """Clone into an empty mirror, or fast-forward an existing one. The mirror is
    this plugin's own folder — never the user's working copy."""
    if not shutil.which("git"):
        raise RuntimeError("git is not installed")
    mirror = Path(mirror)
    if (mirror / ".git").exists():
        _git(["-C", str(mirror), "fetch", "--prune", "origin"])
        b = branch or _git(["-C", str(mirror), "rev-parse", "--abbrev-ref", "HEAD"]).strip()
        _git(["-C", str(mirror), "merge", "--ff-only", f"origin/{b}"])
        return "pulled"
    if mirror.exists() and any(mirror.iterdir()):
        raise RuntimeError(f"{mirror} is not empty and not a clone made by this plugin")
    mirror.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "--no-tags"]
    if branch:
        args += ["--branch", branch, "--single-branch"]
    _git(args + ["--", url, str(mirror)])
    return "cloned"


# ---------------------------------------------------------------------------
# Google Drive (OAuth installed-app flow + Drive API v3)
# ---------------------------------------------------------------------------

def token_path():
    env = os.environ.get("SBL_DRIVE_TOKEN_FILE")
    return Path(env) if env else home() / "connectors" / "google_drive" / "token.json"


def _save_token(tok):
    p = token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(tok), encoding="utf-8")
    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)


def _client(client_secret):
    data = json.loads(Path(os.path.expanduser(client_secret)).read_text(encoding="utf-8"))
    c = data.get("installed") or data.get("web") or {}
    if not c.get("client_id"):
        raise SystemExit("client_secret.json must be an OAuth client of type 'Desktop app'")
    return {"client_id": c["client_id"], "client_secret": c.get("client_secret", "")}


def _post_form(url, fields, http=None):
    body = urllib.parse.urlencode(fields).encode()
    if http:
        return http("POST", url, body, {"Content-Type": "application/x-www-form-urlencoded"})
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def auth_drive(client_secret, open_browser=True):
    """Loopback OAuth (RFC 8252): opens the consent page, receives the code on
    127.0.0.1, exchanges it for a refresh token stored with mode 0600."""
    cl = _client(client_secret)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    redirect = f"http://127.0.0.1:{port}/"
    verifier = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = uuid.uuid4().hex
    got = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if q.get("state", [""])[0] == state:
                got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<p>Second Brain Link — you can close this tab.</p>".encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", port), H)
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cl["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": DRIVE_SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print("Open this page to allow read-only access to Google Drive:\n" + url)
    if open_browser:
        webbrowser.open(url)
    t.join(timeout=300)
    srv.server_close()
    if "code" not in got:
        raise SystemExit("no authorization code received (timed out or denied)")
    tok = _post_form(TOKEN_URL, {"code": got["code"], "client_id": cl["client_id"],
                                 "client_secret": cl["client_secret"], "redirect_uri": redirect,
                                 "grant_type": "authorization_code", "code_verifier": verifier})
    if not tok.get("refresh_token"):
        raise SystemExit("Google returned no refresh token — revoke the app's access and retry")
    _save_token({"refresh_token": tok["refresh_token"], "client_id": cl["client_id"],
                 "client_secret": cl["client_secret"], "scope": DRIVE_SCOPE})
    print(f"✓ authorized — token saved to {token_path()} (mode 600)")


class Drive:
    """Minimal Drive v3 client. `http(method, url, body, headers) -> dict|bytes`
    can be injected for offline tests; the default uses urllib."""

    def __init__(self, http=None):
        self.http = http
        self._access = None
        self._exp = 0

    def _token(self):
        if self._access and time.time() < self._exp - 60:
            return self._access
        p = token_path()
        if not p.is_file():
            raise SystemExit("not authorized — run: connector.py auth-drive --client-secret <file>")
        t = json.loads(p.read_text(encoding="utf-8"))
        r = _post_form(TOKEN_URL, {"refresh_token": t["refresh_token"], "client_id": t["client_id"],
                                   "client_secret": t.get("client_secret", ""),
                                   "grant_type": "refresh_token"}, self.http)
        self._access = r["access_token"]
        self._exp = time.time() + int(r.get("expires_in", 3600))
        return self._access

    def get(self, path, params=None, raw=False):
        url = DRIVE_API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        hdr = {"Authorization": "Bearer " + self._token()}
        if self.http:
            return self.http("GET", url, None, hdr)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=300) as r:
                    data = r.read()
                return data if raw else json.loads(data.decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise

    def children(self, folder_id, drive_id=None):
        params = {"q": f"'{folder_id}' in parents and trashed = false", "pageSize": 1000,
                  "fields": "nextPageToken, files(id, name, mimeType, size, md5Checksum, createdTime, "
                            "modifiedTime, version, webViewLink, owners(displayName), "
                            "lastModifyingUser(displayName))",
                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        if drive_id:
            params.update({"corpora": "drive", "driveId": drive_id})
        token = None
        while True:
            if token:
                params["pageToken"] = token
            r = self.get("/files", params)
            for f in r.get("files", []):
                yield f
            token = r.get("nextPageToken")
            if not token:
                break


def _safe(name):
    n = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip().strip(".") or "untitled"
    return n[:200]


def sync_drive(mirror, folder_id, data, entity, drive_id=None, http=None, max_bytes=MAX_FILE_BYTES):
    """Mirror a Drive folder tree. Writes files under `mirror` and the metadata
    sidecar next to the link file. Unchanged files (same md5 / modifiedTime) are
    not downloaded again; files removed from Drive are removed from the mirror
    (the mirror is this plugin's own copy, not the user's data)."""
    dv = Drive(http)
    mirror = Path(mirror)
    mirror.mkdir(parents=True, exist_ok=True)
    side = link_dir(data, entity, "google_drive") / MANIFEST_NAME
    old = {}
    if side.is_file():
        try:
            old = json.loads(side.read_text(encoding="utf-8")).get("files", {})
        except Exception:
            old = {}
    files, stats = {}, {"downloaded": 0, "unchanged": 0, "skipped": 0, "removed": 0}
    stack = [(folder_id, "")]
    seen_names = set()
    while stack:
        fid, prefix = stack.pop()
        for f in dv.children(fid, drive_id):
            name = _safe(f.get("name", ""))
            mime = f.get("mimeType", "")
            if mime == FOLDER_MIME:
                stack.append((f["id"], f"{prefix}{name}/"))
                continue
            if mime in SKIP_NATIVE:
                stats["skipped"] += 1
                continue
            export = EXPORTS.get(mime)
            if export:
                name = os.path.splitext(name)[0] + export[1]
            rel = prefix + name
            if rel.lower() in seen_names:                 # Drive allows duplicate names
                stem, ext = os.path.splitext(name)
                rel = prefix + f"{stem} ({f['id'][:6]}){ext}"
            seen_names.add(rel.lower())
            size = int(f.get("size") or 0)
            meta = {"id": f["id"], "mime": mime, "created": (f.get("createdTime") or "")[:10],
                    "modified": (f.get("modifiedTime") or "")[:10], "size": size,
                    "md5": f.get("md5Checksum", ""), "version": str(f.get("version", "")),
                    "web_view_link": f.get("webViewLink", ""),
                    "owners": [o.get("displayName", "") for o in f.get("owners") or [] if o.get("displayName")],
                    "last_modifier": (f.get("lastModifyingUser") or {}).get("displayName", ""),
                    "_modifiedTime": f.get("modifiedTime", "")}
            dest = mirror / rel
            prev = old.get(rel) or {}
            if dest.is_file() and prev.get("id") == meta["id"] and \
                    prev.get("_modifiedTime") == meta["_modifiedTime"] and prev.get("md5", "") == meta["md5"]:
                stats["unchanged"] += 1
                files[rel] = meta
                continue
            if size > max_bytes:
                stats["skipped"] += 1
                continue
            if export:
                data_b = dv.get(f"/files/{f['id']}/export", {"mimeType": export[0]}, raw=True)
            else:
                data_b = dv.get(f"/files/{f['id']}", {"alt": "media", "supportsAllDrives": "true"}, raw=True)
            if isinstance(data_b, dict):
                data_b = json.dumps(data_b).encode()
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(data_b)
            os.replace(tmp, dest)
            stats["downloaded"] += 1
            files[rel] = meta
    for rel in sorted(set(old) - set(files)):
        p = mirror / rel
        if p.is_file():
            p.unlink()
            stats["removed"] += 1
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text(json.dumps({"schema": MANIFEST_SCHEMA, "kind": "google_drive",
                                "synced_at": now_iso(),
                                "remote": {"host": "drive.google.com", "name": folder_id},
                                "files": files}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _links(data):
    base = Path(os.path.expanduser(data)).resolve() / "company"
    out = []
    if not base.is_dir():
        return out
    for ent in sorted(base.iterdir()):
        for src in ("git_docs", "google_drive"):
            lf = ent / src / LINK_NAME
            if lf.is_file():
                try:
                    out.append((ent.name, src, json.loads(lf.read_text(encoding="utf-8"))))
                except Exception:
                    pass
    return out


def cmd_add_git(a):
    _check_entity(a.entity)
    url = check_git_url(a.url)
    m = mirror_dir(a.entity, "git_docs", a.mirror)
    _guard_mirror(m, a.data)
    lf = write_link(a.data, a.entity, "git_docs", m, a.label,
                    {"kind": "git", "url": _redact_url(url), "branch": a.branch or ""})
    print(f"✓ connector added → {lf}\n  mirror: {m}")
    if not a.no_sync:
        return cmd_sync(argparse.Namespace(data=a.data, entity=a.entity, source="git_docs", url=url))
    return 0


def cmd_add_drive(a):
    _check_entity(a.entity)
    _client(a.client_secret)          # validate early
    m = mirror_dir(a.entity, "google_drive", a.mirror)
    _guard_mirror(m, a.data)
    lf = write_link(a.data, a.entity, "google_drive", m, a.label,
                    {"kind": "drive", "folder": a.folder, "shared_drive": a.shared_drive or ""})
    print(f"✓ connector added → {lf}\n  mirror: {m}")
    if not token_path().is_file():
        auth_drive(a.client_secret)
    if not a.no_sync:
        return cmd_sync(argparse.Namespace(data=a.data, entity=a.entity, source="google_drive", url=None))
    return 0


def cmd_sync(a):
    rc = 0
    for ent, src, link in _links(a.data):
        if a.entity and ent != a.entity or a.source and src != a.source:
            continue
        if link.get("mode") != "connector":
            continue
        rem = (link.get("connector") or {}).get("remote") or {}
        mirror = Path(link["root"])
        try:
            if src == "git_docs":
                url = getattr(a, "url", None) or rem.get("url", "")
                how = sync_git(mirror, url, rem.get("branch") or None)
                note = how
            else:
                st = sync_drive(mirror, rem.get("folder") or "root", a.data, ent,
                                rem.get("shared_drive") or None)
                note = ", ".join(f"{k} {v}" for k, v in st.items())
            _mark_synced(a.data, ent, src, True, note)
            print(f"✓ {ent}/{src}: {note}")
        except (RuntimeError, urllib.error.URLError, OSError) as e:
            _mark_synced(a.data, ent, src, False, str(e)[:200])
            print(f"✗ {ent}/{src}: {e}")
            rc = 1
    print("Next: reseed the brain (Studio → Reseed, or build_vault.py … --refresh).")
    return rc


def cmd_status(a):
    rows = _links(a.data)
    if not rows:
        print("no linked document stores")
    for ent, src, link in rows:
        c = link.get("connector") or {}
        print(f"{ent}/{src}: mode={link.get('mode')} root={link.get('root')} "
              f"last_sync={c.get('last_sync') or '—'} {c.get('last_result') or ''}")
    print(f"drive token: {'present' if token_path().is_file() else 'not authorized'}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pull a remote document store into a local mirror and link it.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    data_default = os.environ.get("SBL_DATA_DIR") or str(Path.home() / "Documents" / "SecondBrainLink" / "data")
    g = sub.add_parser("add-git")
    g.add_argument("--data", default=data_default)
    g.add_argument("--entity", required=True)
    g.add_argument("--url", required=True)
    g.add_argument("--branch", default="")
    g.add_argument("--label", default="")
    g.add_argument("--mirror", default=None)
    g.add_argument("--no-sync", action="store_true")
    d = sub.add_parser("add-drive")
    d.add_argument("--data", default=data_default)
    d.add_argument("--entity", required=True)
    d.add_argument("--folder", default="root", help="Drive folder id (default: My Drive root)")
    d.add_argument("--shared-drive", default="")
    d.add_argument("--client-secret", required=True)
    d.add_argument("--label", default="")
    d.add_argument("--mirror", default=None)
    d.add_argument("--no-sync", action="store_true")
    au = sub.add_parser("auth-drive")
    au.add_argument("--client-secret", required=True)
    au.add_argument("--no-browser", action="store_true")
    s = sub.add_parser("sync")
    s.add_argument("--data", default=data_default)
    s.add_argument("--entity", default="")
    s.add_argument("--source", default="", choices=["", "git_docs", "google_drive"])
    st = sub.add_parser("status")
    st.add_argument("--data", default=data_default)
    a = ap.parse_args(argv)
    if a.cmd == "auth-drive":
        auth_drive(a.client_secret, not a.no_browser)
        return 0
    return {"add-git": cmd_add_git, "add-drive": cmd_add_drive, "sync": cmd_sync,
            "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
