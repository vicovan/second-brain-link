#!/usr/bin/env python3
"""
_docs.py — shared orchestration for the document-store sources (`git_docs`,
`google_drive`). The leading underscore keeps the registry from treating this
module as an adapter; `sources/company/git_docs.py` and `google_drive.py` are the
thin adapters that call `extract_store()`.

Pipeline per linked store (all local, read-only, zero network):

    _SOURCE_LINK.json ─ doclink.load_link ─ doclink.walk (no symlinks, no cloud-only opens)
        → docscan.classify per file (tier + reason ids; text only for clean files)
        → doctax.classify per file (category, doc_type, entity) — path/name only
        → render pairing (same folder + stem), sha256 dedup, version groups
        → col.add_document(...)  ← the privacy boundary drops content for stubs
        → col.add_person (document authors, names only) + message signal per commit
        → col.add_org (counterparty entities)
        → col.doc_coverage: one status row for EVERY walked path

The renderer (`VaultWriter.documents`) writes the `docs` layer from the records.
"""
import hashlib
import mimetypes
import os
import re
from collections import defaultdict
from pathlib import Path

import doclink
import docscan
import doctax
import docentities
from sources.common import norm_file, nk

GOOGLE_NATIVE = {".gdoc": "google-doc", ".gsheet": "google-sheet", ".gslides": "google-slides",
                 ".gdraw": "diagram", ".gform": "form", ".gmap": "map", ".gsite": "webpage",
                 ".gjam": "whiteboard", ".gscript": "code"}
MD_EXTS = {".md", ".markdown"}
CODE_FENCE_EXTS = {".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".ini": "ini",
                   ".py": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript",
                   ".tsx": "tsx", ".jsx": "jsx", ".sh": "bash", ".bash": "bash", ".zsh": "bash",
                   ".sql": "sql", ".xml": "xml", ".csv": "csv", ".tsv": "", ".go": "go",
                   ".java": "java", ".rb": "ruby", ".php": "php", ".rs": "rust", ".css": "css",
                   ".mmd": "mermaid", ".mermaid": "mermaid", ".puml": "plantuml", ".tf": "hcl",
                   ".graphql": "graphql", ".ps1": "powershell", ".swift": "swift", ".kt": "kotlin",
                   ".c": "c", ".h": "c", ".cpp": "cpp", ".cs": "csharp", ".ipynb": "json",
                   ".canvas": "json", ".svg": "xml", ".log": "", ".txt": "", ".eml": "",
                   ".rst": "", ".adoc": "", ".tex": "latex", ".http": "http", ".rest": "http"}
GENERIC_GROUPS = {"", "docs", "doc", "documents", "documentation", "files", "general", "misc",
                  "other", "shared", "my-drive", "drive", "notes", "archive", "old", "new", "src", "data"}
PEOPLE_SKIP = {"mockup", "mockups", "template", "templates", "prototype", "prototypes", "wireframe",
               "wireframes", "design-system", "scraps", "fixtures", "fixture", "samples", "sample",
               "examples", "example", "demo", "demos", "lorem", "placeholder", "placeholders",
               "claude-design", "figma", "tutorial", "tutorials"}
# areas whose people are a COUNTERPARTY's (customers, vendors, prospects, investor
# targets) — never person notes in this company's brain
EXTERNAL_CATS = {"customers", "sales/rfps", "sales", "engineering/vendors", "research", "fundraising"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff",
              ".heic", ".avif", ".ico"}


# ---------------------------------------------------------------------------
# entry point used by the two adapters
# ---------------------------------------------------------------------------

def find_links(source, file_index):
    out = []
    for p in file_index.get("sourcelink", []) or []:
        try:
            import json
            k = (json.loads(Path(p).read_text(encoding="utf-8")) or {}).get("kind")
        except Exception:
            continue
        if k == source:
            out.append(Path(p))
    return out


def inline_root(source, root, all_paths):
    """Inline mode: no link file, the store's files sit under `<entity>/<source>/`."""
    cand = Path(root) / source
    if cand.is_dir() and not (cand / doclink.LINK_NAME).exists():
        return cand
    for p in all_paths or ():
        parts = Path(p).parts
        if source in parts and doclink.LINK_NAME not in parts:
            i = parts.index(source)
            return Path(*parts[: i + 1])
    return None


def detect_store(source, file_index, extra_markers=None):
    if find_links(source, file_index):
        return True
    for paths in file_index.values():
        for p in paths:
            if source in Path(p).parts:
                return True
    return False


def extract_store(source, root, file_index, all_paths, col, extra_mapping_dirs=None):
    """Run every linked (or inline) store of kind `source` into `col`.
    Returns the consumed file_index keys."""
    consumed = set()
    links = find_links(source, file_index)
    for lp in links:
        consumed.add(norm_file(lp.name))
        try:
            link = doclink.load_link(lp, guard_paths=[root])
        except doclink.LinkError as e:
            col.note(f"[{source}] {e}")
            continue
        for k, rp in (link.get("rules") or {}).items():
            consumed.add(norm_file(Path(rp).name))
        consumed.add(norm_file(doclink.MANIFEST_NAME))
        if not link["root_exists"]:
            col.note(f"[{source}] linked root not found: {link['label']} — nothing imported")
            col.linked_sources.append({"source": source, "id": link["id"], "label": link["label"],
                                       "missing": True, "walked": 0})
            continue
        _process(source, link, col, extra_mapping_dirs)
    # a rules/ folder next to the link file is configuration, not data
    for key, paths in file_index.items():
        for p in paths:
            pp = Path(p)
            if "rules" in pp.parts and source in pp.parts:
                consumed.add(key)
    if not links:
        ir = inline_root(source, root, all_paths)
        if ir is not None:
            link = {"kind": source, "id": content_id(hashlib.sha256(str(ir.resolve()).encode()).hexdigest()),
                    "label": f"{source.replace('_', ' ')} (inline)", "root_path": ir.resolve(),
                    "root_exists": True, "mode": "inline", "include": ["**"], "exclude": [],
                    "vcs": "auto", "copy_files": True, "layout": "auto",
                    "max_copy_bytes": doclink.DEFAULTS["max_copy_bytes"],
                    "max_total_copy_bytes": doclink.DEFAULTS["max_total_copy_bytes"],
                    "rules": {}, "link_dir": ir, "link_path": None}
            doclink.REGISTERED_ROOTS[link["id"]] = ir.resolve()
            _process(source, link, col, extra_mapping_dirs)
            for key, paths in file_index.items():
                if any(doclink.under_root(p, ir) for p in paths):
                    consumed.add(key)
    return consumed


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def content_id(hexdigest):
    """A 12-char content id from a sha256 hex digest, in lowercase base32 —
    stable, collision-safe for a vault, and never a long digit run."""
    import base64
    if not hexdigest:
        return ""
    return base64.b32encode(bytes.fromhex(hexdigest)).decode("ascii")[:12].lower()


def _sha256_file(path, root, cap):
    h = hashlib.sha256()
    n = 0
    with doclink.open_ro(path, root) as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
            n += len(b)
            if n > cap:
                return ""
    return h.hexdigest()


def _mime(name, data=None):
    m, _ = mimetypes.guess_type(name)
    if m:
        return m
    if data:
        if data[:4] == b"%PDF":
            return "application/pdf"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if data[:4] == b"PK\x03\x04":
            return "application/zip"
    ext = os.path.splitext(name)[1].lower()
    return {".md": "text/markdown", ".gdoc": "application/vnd.google-apps.document",
            ".gsheet": "application/vnd.google-apps.spreadsheet",
            ".gslides": "application/vnd.google-apps.presentation"}.get(ext, "application/octet-stream")


def _iso(ts):
    if not ts:
        return ""
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _headings(md):
    out = []
    for ln in md.splitlines():
        m = re.match(r"^(#{1,2})\s+(.+?)\s*#*\s*$", ln)
        if m:
            out.append(m.group(2).strip()[:120])
        if len(out) >= 12:
            break
    return out


def _plain(text):
    t = re.sub(r"(?s)```.*?```", " ", text or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[#>*_`|\[\]()!]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _printable_ratio(t):
    if not t:
        return 0.0
    sample = t[:4000]
    ok = sum(1 for c in sample if c.isalnum() or c in " .,;:'\"-()\n")
    return ok / max(len(sample), 1)


def _html_text(html):
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</h\d>|</li>|</tr>", "\n", html)
    t = re.sub(r"<[^>]+>", " ", html)
    import html as _h
    t = _h.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def _split_front_matter(md):
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            return md[3:end].strip("\n"), md[end + 4:].lstrip("\n")
    return "", md


# ---------------------------------------------------------------------------
# the per-store pipeline
# ---------------------------------------------------------------------------

def _process(source, link, col, extra_mapping_dirs):
    root = link["root_path"]
    label = link["label"]
    srules = docscan.load_rules(extra_mapping_dirs, (link.get("rules") or {}).get("sensitivity"))
    trules = doctax.load_rules(extra_mapping_dirs, (link.get("rules") or {}).get("taxonomy"))
    max_copy = int(link.get("max_copy_bytes") or doclink.DEFAULTS["max_copy_bytes"])
    budget = int(link.get("max_total_copy_bytes") or doclink.DEFAULTS["max_total_copy_bytes"])
    copy_files = bool(link.get("copy_files", True))
    max_hash = int(srules.limits.get("max_hash_bytes", 500 * 1024 * 1024))
    max_body = int(srules.limits.get("max_body_chars", 60000))
    takeout = source == "google_drive" and (root / "Takeout" / "Drive").is_dir()

    def logical(rel):
        """Display / taxonomy path (Takeout prefix stripped)."""
        if takeout and rel.startswith("Takeout/Drive/"):
            return rel[len("Takeout/Drive/"):]
        return rel

    modes = doclink.dir_modes(root)
    root_mode = modes.get(".", 0o755)

    # ---- git metadata (git_docs only, optional) ----
    gm = {"ok": False, "paths": {}, "tracked": set(), "untracked": set(), "ignored": set(),
          "why": "", "commits": []}
    if source == "git_docs" and link.get("vcs", "auto") in ("auto", "git"):
        gm = doclink.git_meta(root)
        if not gm["ok"] and gm.get("why"):
            col.note(f"[{source}] {label}: {gm['why']}")
    man = doclink.manifest_meta(link)

    entries, verdicts, coverage = {}, {}, {}
    sha = {}
    for e in doclink.walk(link):
        rel = e["rel"]
        if e.get("is_dir"):
            coverage[rel] = ("excluded (folder not walked — version-control / dependency internals)"
                             if e.get("pruned") else "symlink (not followed)")
            continue
        entries[rel] = e
        if e["is_symlink"]:
            coverage[rel] = "symlink (not followed)"
            continue
        ex = docscan.is_excluded(e, srules)
        if ex:
            coverage[rel] = f"excluded ({ex})"
            continue
        if e["user_excluded"]:
            coverage[rel] = "excluded (link include/exclude)"
            continue
        why = doctax.is_tax_excluded(logical(rel), trules)
        if why:
            coverage[rel] = f"excluded ({why})"
            continue
        data = None
        if not e["cloud_only"] and e["size"] <= srules.max_scan_bytes:
            try:
                data = doclink.read_bytes(e["abspath"], root)
            except OSError as err:
                coverage[rel] = f"unreadable ({type(err).__name__})"
                continue
        v = docscan.classify(e, data, srules, modes, root_mode)
        verdicts[rel] = v
        if data is not None:
            sha[rel] = hashlib.sha256(data).hexdigest()
            if not v.get("meta") and e["ext"] in srules.ooxml_exts:
                pass
        elif not e["cloud_only"] and e["size"] <= max_hash:
            try:
                sha[rel] = _sha256_file(e["abspath"], root, max_hash)
            except OSError:
                sha[rel] = ""
        data = None

    # ---- grouping: assets vs documents, render pairs ----
    asset_rels, doc_rels = [], []
    for rel in verdicts:
        e = entries[rel]
        lrel = logical(rel)
        if doctax.is_asset_path(lrel, trules) or (e["ext"] in IMAGE_EXTS and e["ext"] != ".svg"
                                                   and not e["inner_ext"]):
            asset_rels.append(rel)
        else:
            doc_rels.append(rel)

    prio = trules.get("render_priority", [])
    groups = defaultdict(list)          # (dir, stem-lower) -> [rel]
    for rel in doc_rels:
        e = entries[rel]
        ext = e["ext"] if not e["inner_ext"] else e["inner_ext"]
        if ext in prio or e["inner_ext"]:
            d = rel.rsplit("/", 1)[0] if "/" in rel else ""
            groups[(d, doctax.stem_of(e["name"]).lower())].append(rel)
        else:
            groups[(rel, "")].append(rel)

    def _prio(rel):
        e = entries[rel]
        ext = e["ext"]
        if e["inner_ext"]:
            return prio.index(".md") if ".md" in prio else 0
        return prio.index(ext) if ext in prio else len(prio)

    primaries = {}                      # primary rel -> [render rels]
    for key, members in groups.items():
        members.sort(key=lambda r: (_prio(r), r))
        primaries[members[0]] = members[1:]

    # a partial/unreadable PDF render of a clean source is trusted
    trusted = set()
    for prim, renders in primaries.items():
        if verdicts[prim]["tier"] == "clean":
            trusted.update(r for r in renders if entries[r]["ext"] == ".pdf")
    docscan.apply_neighbour_policy(verdicts, srules, clean_siblings=trusted)

    # ---- dedup by content (primaries only) ----
    by_hash = defaultdict(list)

    def _canon_rank(r):
        segs = [x.lower() for x in r.split("/")[:-1]]
        stale = any(x in ("archive", "archived", "old", "backup", "backups", "trash", "deprecated")
                    or x.startswith(("archive-", "old-", "backup-")) for x in segs)
        return (stale, len(segs), r)
    for prim in sorted(primaries, key=_canon_rank):
        h = sha.get(prim)
        if h:
            by_hash[h].append(prim)
    alias_of = {}
    for h, rels in by_hash.items():
        for other in rels[1:]:
            alias_of[other] = rels[0]
    canon = [p for p in sorted(primaries) if p not in alias_of]

    # ---- taxonomy + names ----
    tax = {rel: doctax.classify(logical(rel), trules) for rel in canon}
    used_names = set()
    note_of = {}                        # rel (primary/alias/render) -> note name
    note_dir = {}
    for rel in canon:
        e = entries[rel]
        t = tax[rel]
        cat = doctax.category_path(t["category"], t["entity"])
        lrel = logical(rel)
        top = lrel.split("/")[0] if "/" in lrel else ""
        group = ""
        if top and t["category"] not in ("customers", "sales/rfps", "engineering/vendors"):
            group = doctax.kebab(re.sub(r"(?i)^docs?[-_]", "", top))
            cat_words = set(re.split(r"[/-]", cat)) | set(re.split(r"[/-]", t["category"]))
            # keep the source folder as a sub-group (it is how the company organised the
            # area) unless it just repeats the area or is a generic container name
            if (group in cat_words or group in GENERIC_GROUPS
                    or set(group.split("-")) <= cat_words):
                group = ""
        base = doctax.kebab(doctax.stem_of(e["name"]))
        name = base
        if name in used_names:
            parent = lrel.split("/")[-2] if lrel.count("/") >= 1 else ""
            alt = f"{base}--{doctax.kebab(parent)}" if parent else base
            name = alt
            i = 2
            while name in used_names:
                name = f"{alt}-{i}"
                i += 1
        used_names.add(name)
        note_of[rel] = name
        note_dir[rel] = "/".join(x for x in (cat, group) if x)
        for r in primaries[rel]:
            note_of[r] = name
    for a, c in alias_of.items():
        note_of[a] = note_of.get(c, "")
        for r in primaries.get(a, []):
            note_of.setdefault(r, note_of.get(c, ""))

    # ---- version groups ----
    vgroups = defaultdict(list)
    vinfo = {}
    for rel in canon:
        e = entries[rel]
        t = tax[rel]
        lrel = logical(rel)
        key, label_v, rank = doctax.version_info(doctax.stem_of(e["name"]), lrel.split("/")[:-1], trules)
        vinfo[rel] = (key, label_v, rank)
        vgroups[(t["category"], t["entity"], key)].append(rel)
    latest, supersedes, superseded_by = {}, {}, {}
    for gk, rels in vgroups.items():
        if len(rels) < 2:
            continue
        def _k(r):
            gl = (gm["paths"].get(r) or {}).get("last", "")
            return (vinfo[r][2], gl or _iso(entries[r]["mtime"]), r)
        ordered = sorted(rels, key=_k)
        for i, r in enumerate(ordered):
            latest[r] = (i == len(ordered) - 1)
            if i > 0:
                supersedes[r] = ordered[i - 1]
            if i < len(ordered) - 1:
                superseded_by[r] = ordered[i + 1]

    # ---- asset references (md bodies) ----
    asset_set = set(asset_rels)
    copy_budget = [budget]

    def _copyable(rel):
        e = entries[rel]
        return (copy_files and not e["cloud_only"] and e["size"] <= max_copy
                and e["size"] <= copy_budget[0])

    def _spend(rel):
        copy_budget[0] -= entries[rel]["size"]

    # ---- the company itself: display name + its own logo (filename-based) ----
    entity_slug = Path(link.get("link_dir") or root).parent.name if link.get("link_path") else Path(root).parent.name
    company_name = str(trules.get("company_name") or "").strip() or \
        " ".join(w.capitalize() for w in re.split(r"[-_]+", entity_slug) if w)
    image_rels = [r for r in list(asset_rels) + list(canon)
                  if entries[r]["ext"] in docentities.LOGO_EXTS
                  and verdicts.get(r, {}).get("tier") in ("clean", "unverified")
                  and not entries[r]["cloud_only"]]
    logo_rel = docentities.pick_logo([logical(r) for r in image_rels], entity_slug,
                                     {logical(r): entries[r]["size"] for r in image_rels})
    if not getattr(col, "doc_org_hint", None):
        hint = {"name": company_name, "source": source}
        if logo_rel:
            raw_rel = next(r for r in image_rels if logical(r) == logo_rel)
            try:
                hint["logo_bytes"] = doclink.read_bytes(entries[raw_rel]["abspath"], root, 1_000_001)
                hint["logo_rel"] = logo_rel
                if len(hint["logo_bytes"]) > 1_000_000:
                    hint.pop("logo_bytes")
            except OSError:
                pass
        col.doc_org_hint = hint
    col.org_logos = getattr(col, "org_logos", {}) or {}
    for ent_name in sorted({tax[r]["entity"] for r in canon if tax[r]["entity"]}):
        if ent_name in col.org_logos:
            continue
        lr = docentities.match_org_logo([logical(r) for r in image_rels], ent_name)
        if lr:
            raw_rel = next(r for r in image_rels if logical(r) == lr)
            try:
                b = doclink.read_bytes(entries[raw_rel]["abspath"], root, 1_000_001)
                if len(b) <= 1_000_000:
                    col.org_logos[ent_name] = b
            except OSError:
                pass

    # ---- authors / entities ----
    authors_all = set()
    for c_sha, author, when in gm.get("commits", [])[:20000]:
        authors_all.add(author)
    def _is_person_author(a):
        # the company's own account or an all-caps handle is not a person
        from sources.common import nk as _nk
        a = a.strip()
        return not (_nk(a) == _nk(company_name) or _nk(a) == _nk(entity_slug)
                    or (a.isupper() and " " not in a))
    authors_all = {a for a in authors_all if _is_person_author(a)}
    for a in sorted(authors_all):
        col.add_person(source, a, tags=["person/author"])
    sig = defaultdict(int)
    for c_sha, author, when in gm.get("commits", []):
        if sig[author] >= 500:
            continue
        sig[author] += 1
        col.add_message_signal(source, author, date=when, ts=f"git:{c_sha}")
    for rel in canon:
        t = tax[rel]
        if t["entity"]:
            col.add_org(source, t["entity"], category=t["entity_kind"] or "counterparty",
                        tags=[f"org/{t['entity_kind'] or 'counterparty'}", "org/document-entity"])

    first_roles = {}      # "Rich" → "CEO" from "Rich (CEO)"; resolved after every document
    people_exclude = set(trules.get("people_exclude") or [])
    for nm, prole in sorted((trules.get("people") or {}).items()):
        pcls = docentities._role_class(str(prole))
        col.add_person(source, nm, role=str(prole),
                       company=company_name if pcls in ("founder", "executive", "team") else "",
                       tags=[f"person/{pcls}", "person/listed-in-rules"])

    # ---- records ----
    tier_counts = defaultdict(int)
    for rel in canon:
        e = entries[rel]
        v = verdicts[rel]
        t = tax[rel]
        lrel = logical(rel)
        g = gm["paths"].get(rel) or {}
        m = man.get(rel) or man.get(lrel) or {}
        tier = v["tier"]
        tier_counts[tier] += 1
        ext = e["ext"]
        authors = sorted((g.get("authors") or {}).keys(), key=lambda a: -g["authors"][a])
        authors += [o for o in m.get("owners", []) if o not in authors]
        if m.get("last_modifier") and m["last_modifier"] not in authors:
            authors.append(m["last_modifier"])
        authors = [a for a in authors if _is_person_author(a)]
        for a in authors:
            if a not in authors_all:
                col.add_person(source, a, tags=["person/author"])
                authors_all.add(a)
        vcs = ("tracked" if rel in gm["tracked"] else "untracked" if rel in gm["untracked"]
               else "ignored" if rel in gm["ignored"] else "unknown") if gm["ok"] else "unknown"
        created = g.get("first") or m.get("created") or _iso(e.get("btime")) or _iso(e["mtime"])
        updated = g.get("last") or m.get("modified") or _iso(e["mtime"])
        if created and updated and created > updated:
            created = updated
        rec = {
            "doc_id": content_id(hashlib.sha256(f"{link['id']}:{rel}".encode("utf-8")).hexdigest()),
            "title": doctax.nice_title(doctax.stem_of(e["name"])),
            "note_name": note_of[rel], "note_dir": note_dir[rel],
            "category": t["category"], "doc_type": t["doc_type"],
            "entity": t["entity"], "entity_kind": t["entity_kind"],
            "authored_by": t["authored_by"],
            "root_id": link["id"], "root_label": label,
            "original_path": lrel, "original_name": e["name"],
            "original_ext": (e["inner_ext"] + ext) if e["inner_ext"] else ext,
            "mime": _mime(e["name"]), "size_bytes": e["size"],
            "sha12": content_id(sha.get(rel) or ""),
            "created": created, "updated": updated,
            "date_in_name": doctax.date_in_name(e["name"]),
            "vcs_status": vcs, "first_commit": g.get("first", ""), "last_commit": g.get("last", ""),
            "commit_count": g.get("count", 0), "authors": authors,
            "renamed_from": g.get("renamed_from", ""),
            "version_group": vinfo[rel][0] if (t["category"], t["entity"], vinfo[rel][0]) in vgroups
            and len(vgroups[(t["category"], t["entity"], vinfo[rel][0])]) > 1 else "",
            "version": vinfo[rel][1],
            "is_latest": latest.get(rel, True),
            "supersedes": note_of.get(supersedes.get(rel, ""), ""),
            "superseded_by": note_of.get(superseded_by.get(rel, ""), ""),
            "also_at": [logical(a) for a, c in sorted(alias_of.items()) if c == rel],
            "url": m.get("url", ""),
            "sensitivity": "clean" if tier == "clean" else tier,
            "sensitivity_reasons": list(dict.fromkeys(v["reasons"])),
            "scan_method": v["scan_method"], "scan_chars": v["scan_chars"],
            "mode": link.get("mode", "local"),
        }
        if ext in GOOGLE_NATIVE:
            rec["doc_type"] = GOOGLE_NATIVE[ext]
            rec["file_status"] = "native-google"
            nat = _google_native(e, root) if not e["cloud_only"] else {}
            rec["url"] = rec["url"] or nat.get("url", "")
            rec["google_id"] = nat.get("doc_id", "")
            if tier == "clean":
                rec["sensitivity"] = "clean"
        # ---- content (only meaningful for clean; the Collector enforces it) ----
        text = v.get("text") or ""
        if tier == "clean" and ext not in GOOGLE_NATIVE:
            body = ""
            if ext in MD_EXTS or e["inner_ext"]:
                fmtext, md = _split_front_matter(text)
                rec["headings"] = _headings(md)
                body = md
                if fmtext:
                    body = md.rstrip() + "\n\n## Original front matter\n\n```yaml\n" + fmtext + "\n```\n"
                rec["md_links"] = True
            elif ext in (".html", ".htm"):
                body = _html_text(text)
            elif ext == ".svg":
                # a diagram: shown as itself (the renderer embeds the in-vault copy),
                # never as XML source
                rec["embed_image"] = True
                body = ""
            elif ext in CODE_FENCE_EXTS:
                lang = CODE_FENCE_EXTS[ext]
                body = f"```{lang}\n{text.rstrip()}\n```" if text.strip() else ""
            elif v["scan_method"] == "ooxml" and text.strip():
                body = "## Extracted text\n\n" + re.sub(r"[ \t]+", " ", text).strip()
            elif v["scan_method"] == "pdf-partial" and text.strip() and _printable_ratio(text) > 0.85:
                body = "## Extracted text (best effort)\n\n" + re.sub(r"\s+", " ", text).strip()
            if len(body) > max_body:
                body = body[:max_body].rsplit("\n", 1)[0] + "\n\n*(truncated — open the file for the rest)*"
            rec["body"] = body
            plain = _plain(md if (ext in MD_EXTS or e["inner_ext"]) else body)
            rec["excerpt"] = plain[:300]
            rec["word_count"] = len(plain.split())
            # people named WITH a role (founders, advisors, board, investors, team) and
            # goal statements — mined from this clean document's own text only
            if ext in MD_EXTS or e["inner_ext"] or ext in (".txt", ".html", ".htm") \
                    or v["scan_method"] in ("ooxml", "pdf-partial"):
                mined = md if (ext in MD_EXTS or e["inner_ext"]) else \
                    (_html_text(text) if ext in (".html", ".htm") else text)
                ppl = docentities.extract_people(mined)
                for fn, frole in (ppl.pop("__first__", None) or {}).items():
                    first_roles.setdefault(fn, frole)
                own = ("founder", "executive", "team")
                for nm in list(ppl):
                    if nm in people_exclude:
                        ppl.pop(nm)
                # placeholder content (design mockups, templates, samples) names nobody real
                segs_l = {x.lower() for x in lrel.split("/")[:-1]}
                if segs_l & PEOPLE_SKIP or any(x.endswith(("-design", "-mockup", "-template")) for x in segs_l) \
                        or any(set(re.split(r"[-_. ]+", x)) & PEOPLE_SKIP for x in segs_l):
                    ppl = {}
                # people in a customer / RFP / vendor / research document are THAT
                # counterparty's staff, not this company's: they never become person
                # notes here (the document itself stays, linked to the counterparty org)
                # (the store's own authors are insiders: their role there still counts)
                if any(t["category"] == c or t["category"].startswith(c + "/") for c in EXTERNAL_CATS):
                    ppl = {k: v for k, v in ppl.items() if nk(k) in {nk(a) for a in authors_all}}
                for nm, info in sorted(ppl.items()):
                    col.add_person(source, nm, role=info["role"],
                                   company=company_name if info["class"] in own else "",
                                   tags=[f"person/{info['class']}", "person/mentioned-in-docs"])
                rec["mentions"] = sorted(ppl)
                if ext in MD_EXTS or e["inner_ext"] or ext == ".txt" or v["scan_method"] == "ooxml":
                    gl = docentities.extract_goals(md if (ext in MD_EXTS or e["inner_ext"]) else text)
                    if gl:
                        rec["goals"] = [f"{h}: {g}" if h and h.lower() not in g.lower() else g for h, g in gl]
        # ---- the file copy (clean or unverified only — enforced again by the Collector) ----
        if ext not in MD_EXTS and not e["inner_ext"] and ext not in GOOGLE_NATIVE:
            if tier in ("clean", "unverified") and _copyable(rel):
                rec["copy_from"] = str(e["abspath"])
                rec["file_name"] = e["name"]
                rec["file_status"] = "copied"
                _spend(rel)
            elif tier in ("clean", "unverified"):
                rec["file_status"] = "too-large" if e["size"] > max_copy else ("cloud-only" if e["cloud_only"] else "not-copied")
            else:
                rec["file_status"] = "cloud-only" if e["cloud_only"] else "stub"
        elif "file_status" not in rec:
            rec["file_status"] = "note" if tier == "clean" else "stub"
        # ---- renders ----
        rnds = []
        for r in primaries[rel]:
            re_ = entries[r]
            rv = verdicts[r]
            item = {"ext": re_["ext"], "rel": logical(r), "name": re_["name"],
                    "size": re_["size"], "sha12": content_id(sha.get(r) or ""),
                    "sensitivity": rv["tier"], "reasons": rv["reasons"], "copy_from": None,
                    "status": "stub"}
            if rv["tier"] in ("clean", "unverified") and _copyable(r):
                item["copy_from"] = str(re_["abspath"])
                item["status"] = "copied"
                _spend(r)
            elif rv["tier"] in ("clean", "unverified"):
                item["status"] = "too-large" if re_["size"] > max_copy else "not-copied"
            rnds.append(item)
            coverage[r] = f"render → {note_of[rel]}" + ("" if item["status"] == "copied" else f" ({item['status']})")
        rec["renders"] = rnds
        col.add_document(source, rec)
        coverage[rel] = ("imported (note, online link)" if rec.get("file_status") == "native-google" and rec["sensitivity"] == "clean"
                         else "imported (note + file)" if rec.get("file_status") == "copied" and rec["sensitivity"] == "clean"
                         else "imported (note, unverified copy)" if rec.get("file_status") == "copied"
                         else "imported (note, text)" if rec["sensitivity"] == "clean"
                         else f"stub ({rec['sensitivity']})")
    # first names with a role ("Rich (CEO), Adrian (CTO)") → the ONE known person whose
    # first name starts with it; ambiguous or unknown first names are dropped
    for fn, frole in sorted(first_roles.items()):
        cands = [r["name"] for r in col.people.values()
                 if r["name"].split()[0].lower().startswith(fn.lower()) and len(r["name"].split()) >= 2]
        if len(cands) == 1:
            info_cls = docentities._role_class(frole)
            col.add_person(source, cands[0], role=docentities._clean_role(frole),
                           company=company_name if info_cls in ("founder", "executive", "team") else "",
                           tags=[f"person/{info_cls}", "person/mentioned-in-docs"])
    for a, c in alias_of.items():
        coverage[a] = f"duplicate → {note_of.get(c, '')}"
        for r in primaries.get(a, []):
            coverage[r] = f"duplicate render → {note_of.get(c, '')}"

    # ---- assets ----
    assets = []
    for rel in sorted(asset_rels):
        e = entries[rel]
        v = verdicts[rel]
        item = {"rel": logical(rel), "name": e["name"], "size": e["size"],
                "sha12": content_id(sha.get(rel) or ""), "sensitivity": v["tier"],
                "reasons": v["reasons"], "copy_from": None,
                "dir": logical(rel).rsplit("/", 1)[0] if "/" in logical(rel) else ""}
        if v["tier"] in ("clean", "unverified") and trules.get("copy_unreferenced_assets", True) and _copyable(rel):
            item["copy_from"] = str(e["abspath"])
            _spend(rel)
            coverage[rel] = "asset (copied)"
        else:
            coverage[rel] = ("asset (not copied)" if v["tier"] in ("clean", "unverified")
                             else f"asset stub ({v['tier']})")
        assets.append(item)
    col.doc_assets = getattr(col, "doc_assets", []) + [{**a, "root_id": link["id"], "source": source}
                                                       for a in assets]

    for rel, st in coverage.items():
        col.doc_coverage.append((source, label, logical(rel), st))
    col.linked_sources.append({
        "source": source, "id": link["id"], "label": label, "mode": link.get("mode", "local"),
        "root": str(root), "walked": len(coverage), "documents": len(canon),
        "stubs": sum(1 for rel in canon if verdicts[rel]["tier"] not in ("clean", "unverified")),
        "assets": len(asset_rels), "git": gm["ok"], "tiers": dict(tier_counts),
    })
    col.note(f"[{source}] {label}: {len(coverage)} paths walked → {len(canon)} documents "
             f"({sum(1 for r in canon if verdicts[r]['tier'] not in ('clean', 'unverified'))} metadata-only stubs), "
             f"{len(asset_rels)} assets, {len(alias_of)} duplicates"
             + ("" if gm["ok"] or source != "git_docs" else " · no git history"))


def _google_native(e, root):
    """url + doc id from a Drive-for-Desktop pointer file. ONLY these two keys
    are read; the account e-mail the pointer also carries is never stored."""
    import json
    try:
        data = json.loads(doclink.read_bytes(e["abspath"], root, 65536).decode("utf-8", "replace"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    url = str(data.get("url") or "").split("?", 1)[0].split("#", 1)[0]
    if (url and not url.startswith("https://")) or "@" in url:
        url = ""
    did = str(data.get("doc_id") or data.get("resource_id") or "")
    return {"url": url, "doc_id": re.sub(r"[^A-Za-z0-9:_-]", "", did)[:120]}
