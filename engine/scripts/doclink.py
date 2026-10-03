#!/usr/bin/env python3
"""
doclink.py — read-only access to a document store the brain is LINKED to.

A document-store source (`git_docs`, `google_drive`) never copies the store into
`data/`, and never symlinks it. Instead the source folder holds one small file:

    data/company/<entity>/<source>/_SOURCE_LINK.json   (schema sbl-source-link/1)

which points at the original folder. Everything here is READ-ONLY and LOCAL:

  * `load_link()`   validates a link file and resolves its root (refusing `/`,
                    a volume root, $HOME, or anything that contains the data or
                    output folders);
  * `walk()`        lists every file under the root WITHOUT following symlinks and
                    without opening cloud-only placeholders (opening one would make
                    the sync client download it — a network fetch);
  * `open_ro()`     the only way the engine reads an original: `open(path, "rb")`
                    after checking the path really sits under a registered root;
  * `assert_not_linked()` the write guard build_vault.write()/write_bytes_file()
                    call, so no code path can ever write into an original store;
  * `git_meta()`    per-path history from a LOCAL `git log` (names only — never
                    e-mail addresses; no fetch, no lock files, PATH-gated, optional);
  * `manifest_meta()` reads a connector's `_SOURCE_MANIFEST.json` sidecar (Phase 2).

CLI (zero network):
    python3 doclink.py init --kind git_docs --root ~/repos/company-docs \
        --out data/company/<entity>/git_docs/ [--label "Company docs"]
    python3 doclink.py show data/company/<entity>/git_docs/_SOURCE_LINK.json
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

LINK_NAME = "_SOURCE_LINK.json"
MANIFEST_NAME = "_SOURCE_MANIFEST.json"
SCHEMA = "sbl-source-link/1"
MANIFEST_SCHEMA = "sbl-source-manifest/1"
KINDS = ("git_docs", "google_drive")

DEFAULTS = {
    "mode": "local",
    "layout": "auto",
    "include": ["**"],
    "exclude": [],
    "vcs": "auto",
    "copy_files": True,
    "max_copy_bytes": 25 * 1024 * 1024,
    "max_total_copy_bytes": 2 * 1024 * 1024 * 1024,
    "rules": {},
    "connector": None,
}

# id -> resolved root Path, for every link loaded in this process (write guard +
# open_ro). Module-level on purpose: one build process, one set of linked stores.
REGISTERED_ROOTS = {}
# Folders a linked root may never contain (the data root and the output vault) —
# set by build_vault.main() so a link to e.g. ~/Documents can't ingest the brain.
GUARD_PATHS = []


class LinkError(ValueError):
    """A link file that is malformed or points somewhere it must not."""


# ---------------------------------------------------------------------------
# link files
# ---------------------------------------------------------------------------

def _resolve_root(raw, link_dir):
    raw = str(raw or "").strip()
    if not raw:
        raise LinkError("link has no `root`")
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        p = Path(link_dir) / p
    return Path(os.path.realpath(str(p)))


def _refuse_reason(root, guard_paths=()):
    """Why `root` may not be linked (None when it is fine)."""
    r = Path(os.path.realpath(str(root)))
    if str(r) in ("/", os.path.realpath(os.path.expanduser("~"))):
        return "refusing to link the filesystem root or your home folder — link the docs folder itself"
    if r.parent == r or (len(r.parts) <= 3 and r.parts[:2] in (("/", "Volumes"),)):
        return "refusing to link a volume root — link the docs folder itself"
    for g in guard_paths:
        if not g:
            continue
        gp = Path(os.path.realpath(str(g)))
        if gp == r or r in gp.parents:
            return f"refusing a root that contains {gp} (the data or vault folder) — that would loop"
    if r.name.endswith("-brain") and (r / "_GENERATED.json").exists():
        return "refusing to link a brain folder"
    return None


def load_link(path, guard_paths=()):
    """Read + validate a `_SOURCE_LINK.json`. Returns a dict with every default
    filled in plus `root_path` (resolved Path), `link_path`, `link_dir`. Raises
    LinkError on anything invalid. Registers the root for the write guard."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise LinkError(f"{path.name}: not valid JSON ({e})")
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise LinkError(f"{path.name}: schema must be {SCHEMA!r}")
    kind = str(data.get("kind") or "").strip()
    if kind not in KINDS:
        raise LinkError(f"{path.name}: kind must be one of {', '.join(KINDS)}")
    link = dict(DEFAULTS)
    link.update(data)
    link["kind"] = kind
    link["id"] = str(data.get("id") or "").strip() or _stable_id(path)
    link["label"] = str(data.get("label") or "").strip() or kind.replace("_", " ")
    link["link_path"] = path
    link["link_dir"] = path.parent
    root = _resolve_root(data.get("root"), path.parent)
    why = _refuse_reason(root, list(guard_paths or ()) + list(GUARD_PATHS))
    if why:
        raise LinkError(f"{path.name}: {why}")
    link["root_path"] = root
    link["root_exists"] = root.is_dir()
    if link["root_exists"]:
        REGISTERED_ROOTS[link["id"]] = root
    rules = link.get("rules") or {}
    link["rules"] = {k: str(Path(path.parent) / v) for k, v in rules.items()
                     if isinstance(v, str) and v.strip()}
    return link


def _stable_id(path):
    import hashlib
    import base64
    return base64.b32encode(hashlib.sha256(str(Path(path).resolve()).encode("utf-8")).digest()).decode("ascii")[:20].lower()


def assert_not_linked(target):
    """Raise if `target` resolves inside any registered original store. Called by
    every vault writer — the guarantee that no build ever writes into an original."""
    if not REGISTERED_ROOTS:
        return
    t = Path(os.path.realpath(str(target)))
    for root in REGISTERED_ROOTS.values():
        if t == root or root in t.parents:
            raise PermissionError(f"refusing to write inside a linked document store: {t}")


def under_root(path, root):
    rp = Path(os.path.realpath(str(path)))
    r = Path(os.path.realpath(str(root)))
    return rp == r or r in rp.parents


def open_ro(path, root):
    """Open an original read-only (binary). The path must resolve under `root`."""
    if not under_root(path, root):
        raise PermissionError(f"path escapes its linked root: {path}")
    return open(path, "rb")


def read_bytes(path, root, cap=None):
    with open_ro(path, root) as f:
        return f.read() if cap is None else f.read(cap)


# ---------------------------------------------------------------------------
# walking
# ---------------------------------------------------------------------------

def _double_ext(name):
    low = name.lower()
    m = re.search(r"(\.(?:docx|xlsx|pptx|pdf|doc|xls|ppt|html?))\.(md|txt)$", low)
    if m:
        return "." + m.group(2), m.group(1)      # ext, inner ext
    return os.path.splitext(low)[1], ""


PRUNE_DIRS = {".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
              ".pytest_cache", ".mypy_cache", ".tox", ".next", ".turbo"}


def is_cloud_only(st):
    """A Drive/iCloud/OneDrive placeholder whose bytes are not on disk. Opening it
    would trigger a download, so callers must never open such a file."""
    try:
        if os.name == "nt":
            attrs = getattr(st, "st_file_attributes", 0)
            return bool(attrs & 0x00400000 or attrs & 0x00001000)   # RECALL_ON_DATA_ACCESS | OFFLINE
        blocks = getattr(st, "st_blocks", None)
        return blocks is not None and st.st_size > 0 and blocks == 0
    except Exception:
        return False


def _glob_match(rel, patterns):
    for pat in patterns or ():
        pat = str(pat).strip()
        if not pat:
            continue
        if pat in ("**", "*"):
            return True
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, pat.replace("**/", "")):
            return True
        if pat.endswith("/**") and (rel == pat[:-3] or rel.startswith(pat[:-2])):
            return True
    return False


def walk(link):
    """Yield one entry dict per path under the link's root (files + symlinks),
    sorted for determinism. Never follows symlinks; never opens anything.
    Entry: {rel, name, ext, inner_ext, size, mode, mtime, btime, is_symlink,
            cloud_only, user_excluded, abspath}."""
    root = link["root_path"]
    include = link.get("include") or ["**"]
    exclude = link.get("exclude") or []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        d = Path(dirpath)
        # never descend into VCS internals / dependency trees: one summary entry each
        for dn in [x for x in dirnames if x in PRUNE_DIRS]:
            dirnames.remove(dn)
            dp = d / dn
            yield {"rel": dp.relative_to(root).as_posix() + "/", "name": dn, "ext": "",
                   "inner_ext": "", "size": 0, "mode": 0, "mtime": 0, "btime": 0,
                   "is_symlink": False, "cloud_only": False, "user_excluded": False,
                   "abspath": dp, "is_dir": True, "pruned": True}
        # symlinked directories appear in dirnames but are not descended into —
        # report them so coverage can account for them.
        for dn in list(dirnames):
            dp = d / dn
            if dp.is_symlink():
                dirnames.remove(dn)
                rel = dp.relative_to(root).as_posix()
                yield {"rel": rel, "name": dn, "ext": "", "inner_ext": "", "size": 0,
                       "mode": 0, "mtime": 0, "btime": 0, "is_symlink": True,
                       "cloud_only": False, "user_excluded": False, "abspath": dp,
                       "is_dir": True}
        for fn in sorted(filenames):
            p = d / fn
            rel = p.relative_to(root).as_posix()
            try:
                st = os.lstat(p)
            except OSError:
                continue
            is_link = stat.S_ISLNK(st.st_mode)
            ext, inner = _double_ext(fn)
            user_excl = bool(exclude and _glob_match(rel, exclude)) or not _glob_match(rel, include)
            yield {"rel": rel, "name": fn, "ext": ext, "inner_ext": inner,
                   "size": 0 if is_link else st.st_size,
                   "mode": stat.S_IMODE(st.st_mode), "mtime": st.st_mtime,
                   "btime": getattr(st, "st_birthtime", 0) or 0,
                   "is_symlink": is_link,
                   "cloud_only": (not is_link) and is_cloud_only(st),
                   "user_excluded": user_excl, "abspath": p, "is_dir": False}


def dir_modes(root):
    """{rel_dir: mode} for every directory under root (no symlink descent) — the
    scanner uses a 0700 folder inside an otherwise 0755 tree as a privacy hint."""
    out = {}
    for dirpath, dirnames, _ in os.walk(root, followlinks=False):
        try:
            out[Path(dirpath).relative_to(root).as_posix()] = stat.S_IMODE(os.stat(dirpath).st_mode)
        except OSError:
            pass
    return out


# ---------------------------------------------------------------------------
# git metadata (local, read-only, optional)
# ---------------------------------------------------------------------------

_GIT_ENV = {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_PAGER": "cat", "LC_ALL": "C"}


def _git(root, *args, timeout=120):
    env = dict(os.environ)
    env.update(_GIT_ENV)
    cmd = ["git", "-C", str(root), "--no-pager", "-c", "core.fsmonitor=false",
           "-c", "core.quotepath=false", *args]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       env=env, timeout=timeout, check=False)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:200])
    return r.stdout.decode("utf-8", "replace")


def git_meta(root, log=None):
    """Per-path history for a git working tree at (or inside) `root`.
    Returns {"ok": bool, "paths": {rel: {first, last, count, authors:{name:n},
    renamed_from}}, "tracked": set, "untracked": set, "ignored": set, "why": str}.
    Uses ONLY `rev-parse`, `log` and `ls-files` (no status → no index refresh, no
    lock files, never a fetch). Author NAMES only (%an) — never e-mail addresses.
    Bot authors (ending in [bot]) are skipped."""
    out = {"ok": False, "paths": {}, "tracked": set(), "untracked": set(),
           "ignored": set(), "why": "", "commits": []}
    root = Path(root)
    if not shutil.which("git"):
        out["why"] = "git not on PATH — dates fall back to file times"
        return out
    if not ((root / ".git").exists() or _inside_git(root)):
        out["why"] = "not a git working tree — dates fall back to file times"
        return out
    try:
        prefix = _git(root, "rev-parse", "--show-prefix").strip()
        raw = _git(root, "log", "-M", "--name-status", "--no-color",
                   "--format=%x1e%H%x00%an%x00%aI", "--", ".", timeout=300)
    except Exception as e:
        out["why"] = f"git log unavailable ({e}) — dates fall back to file times"
        return out
    paths = out["paths"]

    def strip(p):
        p = p.strip()
        if prefix and p.startswith(prefix):
            return p[len(prefix):]
        return p

    for block in raw.split("\x1e"):
        block = block.strip("\n")
        if not block:
            continue
        head, _, rest = block.partition("\n")
        parts = head.split("\x00")
        if len(parts) < 3:
            continue
        _sha, author, when = parts[0], parts[1].strip(), parts[2][:10]
        bot = author.lower().endswith("[bot]")
        if author and not bot:
            out["commits"].append((_sha[:12], author, when))
        for ln in rest.splitlines():
            if not ln.strip():
                continue
            cols = ln.split("\t")
            status = cols[0]
            if status.startswith("R") and len(cols) >= 3:
                old, new = strip(cols[1]), strip(cols[2])
                rec = paths.setdefault(new, {"first": when, "last": when, "count": 0,
                                             "authors": {}, "renamed_from": ""})
                if not rec["renamed_from"]:
                    rec["renamed_from"] = old
                target = new
            elif len(cols) >= 2:
                target = strip(cols[1])
                rec = paths.setdefault(target, {"first": when, "last": when, "count": 0,
                                                "authors": {}, "renamed_from": ""})
            else:
                continue
            # log is newest-first: keep the max as last, min as first
            rec["count"] += 1
            if when > rec["last"]:
                rec["last"] = when
            if when < rec["first"]:
                rec["first"] = when
            if author and not bot:
                rec["authors"][author] = rec["authors"].get(author, 0) + 1
    try:
        out["tracked"] = {strip(x) for x in _git(root, "ls-files", "-z").split("\x00") if x}
        out["untracked"] = {strip(x) for x in _git(root, "ls-files", "-z", "--others",
                                                   "--exclude-standard").split("\x00") if x}
        out["ignored"] = {strip(x) for x in _git(root, "ls-files", "-z", "--others",
                                                 "--ignored", "--exclude-standard").split("\x00") if x}
    except Exception:
        pass
    out["ok"] = True
    return out


def _inside_git(root):
    p = Path(root)
    for parent in [p, *p.parents]:
        if (parent / ".git").exists():
            return True
    return False


# ---------------------------------------------------------------------------
# connector sidecar (Phase 2)
# ---------------------------------------------------------------------------

def manifest_meta(link):
    """{rel: {...}} from a connector's `_SOURCE_MANIFEST.json` (next to the link
    file, or at the root of the mirror). Display names only; never tokens."""
    for cand in (Path(link["link_dir"]) / MANIFEST_NAME, Path(link["root_path"]) / MANIFEST_NAME):
        if cand.is_file():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
            except Exception:
                return {}
            if not isinstance(data, dict) or data.get("schema") != MANIFEST_SCHEMA:
                return {}
            files = data.get("files") or {}
            clean = {}
            for rel, m in files.items():
                if not isinstance(m, dict):
                    continue
                clean[str(rel)] = {
                    "id": str(m.get("id") or ""),
                    "mime": str(m.get("mime") or ""),
                    "created": str(m.get("created") or "")[:10],
                    "modified": str(m.get("modified") or "")[:10],
                    "url": str(m.get("web_view_link") or ""),
                    "owners": [str(o) for o in (m.get("owners") or []) if o and "@" not in str(o)],
                    "last_modifier": "" if "@" in str(m.get("last_modifier") or "") else str(m.get("last_modifier") or ""),
                }
            return clean
    return {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def new_link_id():
    """A random 26-char lowercase base32 id (letters + 2-7): no long digit runs, so
    it never looks like a phone number to a PII sweep."""
    import base64
    return base64.b32encode(uuid.uuid4().bytes).decode("ascii").rstrip("=").lower()


def make_link(kind, root, label="", created_by="cli", **extra):
    data = {"schema": SCHEMA, "kind": kind, "id": new_link_id(),
            "label": label or Path(root).name, "root": str(root),
            "mode": "local", "layout": "auto", "include": ["**"], "exclude": [],
            "vcs": "auto", "copy_files": True,
            "max_copy_bytes": DEFAULTS["max_copy_bytes"],
            "max_total_copy_bytes": DEFAULTS["max_total_copy_bytes"],
            "rules": {}, "connector": None,
            "created": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "created_by": created_by}
    data.update({k: v for k, v in extra.items() if v is not None})
    return data


def _cmd_init(args):
    root = Path(os.path.expanduser(args.root)).resolve()
    if not root.is_dir():
        print(f"root is not a folder: {root}"); return 2
    why = _refuse_reason(root, [args.out])
    if why:
        print(why); return 2
    out = Path(os.path.expanduser(args.out))
    if out.name == LINK_NAME:
        out = out.parent
    if out.name != args.kind:
        print(f"note: the link folder should be named after the source ({args.kind}/) — "
              f"using {out / args.kind}")
        out = out / args.kind
    out.mkdir(parents=True, exist_ok=True)
    target = out / LINK_NAME
    rules = {}
    for k in ("sensitivity", "taxonomy"):
        if (out / "rules" / f"{k}.json").is_file():
            rules[k] = f"rules/{k}.json"
    if target.exists() and not args.force:
        print(f"{target} already exists (use --force to replace it)"); return 1
    data = make_link(args.kind, root, args.label or "", rules=rules)
    if args.max_copy_mb is not None:
        data["max_copy_bytes"] = int(args.max_copy_mb * 1024 * 1024)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"✓ linked {args.kind} → {root}\n  {target}")
    return 0


def _cmd_show(args):
    try:
        link = load_link(args.link)
    except LinkError as e:
        print(f"invalid: {e}"); return 1
    n = sum(1 for e in walk(link)) if link["root_exists"] else 0
    print(json.dumps({k: (str(v) if isinstance(v, Path) else v) for k, v in link.items()
                      if k not in ("link_path",)}, indent=2, default=str))
    print(f"files under root: {n}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Link a document store to a brain (read-only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("init", help="write a _SOURCE_LINK.json")
    a.add_argument("--kind", required=True, choices=KINDS)
    a.add_argument("--root", required=True, help="the original docs folder (never modified)")
    a.add_argument("--out", required=True, help="data/company/<entity>/<kind>/")
    a.add_argument("--label", default="")
    a.add_argument("--max-copy-mb", type=float, default=None)
    a.add_argument("--force", action="store_true")
    s = sub.add_parser("show", help="validate a link file and count files")
    s.add_argument("link")
    args = ap.parse_args(argv)
    return {"init": _cmd_init, "show": _cmd_show}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
