#!/usr/bin/env python3
"""
diagrams.py — render PII-safe visualizations from a profiler catalog.

Three products, each emitted in consistent formats (Markdown+Mermaid AND an
Obsidian `.canvas`) so they can be viewed either way:

1. MINDMAP — an exhaustive map of every file and every column, grouped by the
   vault layer each file routes to, plus a second diagram showing the
   CORRELATIONS (which files feed which canonical entity, and on what join field).

2. BRAIN STRUCTURE — the designed vault folder/note tree (fixed canonical layers,
   pruned to those that actually have data in this export). Emitted as .md +
   .canvas + a machine-readable .json build-spec the builder consumes.

Nothing here reads raw cell values — it works only off the profiler catalog
(file names, column names, row counts, classes). Column *names* are safe to show;
cell *values* never appear.

Used by profile_export.py. Source-agnostic: known files route to a layer, unknown
files surface under "❓ unmapped".
"""
from collections import OrderedDict

# ---------------------------------------------------------------------------
# Routing: normalized-file-key -> canonical vault layer.
# Mirrors scripts/sources/linkedin.py so the mindmap doubles as a build preview.
# Keys are matched by exact-or-prefix against the profiler's normalized keys
# (norm_file strips shard/member-id suffixes, so "jobapplications" covers _1.._10).
# ---------------------------------------------------------------------------
LAYER_ROUTES = OrderedDict([
    ("00-me",            ["profile", "profilesummary", "positions", "skills",
                          "education", "certifications", "languages", "patents",
                          "volunteering", "workinghours"]),
    ("10-people",        ["connections", "memberfollows", "invitations"]),
    ("15-organizations", ["companyfollows"]),
    ("20-reputation",    ["recommendationsreceived", "recommendationsgiven",
                          "endorsementreceivedinfo", "endorsementgiveninfo"]),
    ("30-voice",         ["shares", "instantreposts", "comments", "reactions",
                          "votes", "hashtagfollows", "saveditems", "richmedia",
                          "articles"]),
    ("40-career",        ["jobapplications", "jobseekerpreferences", "savedjobs",
                          "savedjobalerts", "onlinejobpostings",
                          "jobapplicantsavedanswers",
                          "jobapplicantsavedscreeningquestionresponses"]),
    ("50-mirror",        ["inferencesaboutyou", "adtargeting", "adsclicked",
                          "lanadsengagement"]),
    ("60-learning",      ["learning", "learningcoachmessages",
                          "learningroleplaymessages"]),
    ("70-services",      ["engagements", "opprtunities", "opportunities",
                          "providers"]),
    ("80-search",        ["searchqueries"]),
    ("events",           ["events", "calendar"]),
])

# Sensitive files: catalogued but never imported (shown flagged 🔒).
# Mirrors linkedin.QUARANTINE + message files (bodies never read, only signal).
SENSITIVE_KEYS = {
    "emailaddresses", "phonenumbers", "whatsappphonenumbers", "importedcontacts",
    "logins", "securitychallenges", "registration", "receipts",
    "privateidentityasset", "guidemessages",
    "messages", "learningcoachmessages", "learningroleplaymessages",
}

LAYER_TITLES = {
    "00-me": "00-me · identity",
    "10-people": "10-people",
    "15-organizations": "15-organizations",
    "20-reputation": "20-reputation",
    "30-voice": "30-voice",
    "40-career": "40-career",
    "50-mirror": "50-mirror",
    "60-learning": "60-learning",
    "70-services": "70-services",
    "80-search": "80-search",
    "events": "events / calendar",
    "_quarantine": "🔒 quarantine (catalogued, never imported)",
    "_unmapped": "❓ unmapped (needs an override / adapter)",
}

# Human-facing description of what each canonical layer holds (for brain design).
LAYER_PURPOSE = {
    "00-me": "Identity: profile, positions, education, skills, certs, languages",
    "10-people": "One merged note per person across all sources",
    "15-organizations": "Companies you follow / worked at / targeted",
    "20-reputation": "Recommendations + endorsements (given & received)",
    "30-voice": "Your posts, comments, reactions, interests, saved items",
    "40-career": "Job applications, preferences, saved jobs, reusable answers",
    "50-mirror": "How algorithms see you: inferences + ad targeting",
    "60-learning": "Courses / learning activity",
    "70-services": "Services-marketplace engagements & providers",
    "80-search": "Your search history (topics over time)",
    "85-places": "Saved / reviewed locations (Google Maps, check-ins)",
    "events": "Events / calendar",
}

# Optionally override the routing/titles/purpose from engine/mappings/brain/layout.json
# (and any --mappings override dir). Falls back to the constants above if absent, so
# default output is unchanged. This is what makes the brain layout JSON-configurable.
def apply_layout(layout):
    """Rebuild LAYER_ROUTES/LAYER_TITLES/LAYER_PURPOSE from a brain layout dict."""
    global LAYER_ROUTES, LAYER_TITLES, LAYER_PURPOSE
    layers = (layout or {}).get("layers")
    if not layers:
        return
    routes, titles, purpose = OrderedDict(), {}, {}
    for L in layers:
        f = L["folder"]
        routes[f] = L.get("route_keys", [])
        titles[f] = L.get("title", f)
        purpose[f] = L.get("purpose", "")
    titles.setdefault("_quarantine", "🔒 quarantine (catalogued, never imported)")
    titles.setdefault("_unmapped", "❓ unmapped (needs an override / adapter)")
    LAYER_ROUTES, LAYER_TITLES, LAYER_PURPOSE = routes, titles, purpose

try:  # load the shipped default layout (keeps values identical + adds 85-places)
    import mapping as _mp
    apply_layout(_mp.load_brain_layout())
except Exception:
    pass

# ---------------------------------------------------------------------------
# Correlations: canonical entity -> contributing (file-key, join-field) pairs.
# Curated from the LinkedIn data model so the graph is accurate, not fuzzy.
# Files absent from an export simply produce no edge.
# ---------------------------------------------------------------------------
ENTITY_SOURCES = OrderedDict([
    ("Person", [
        ("connections", "name"), ("invitations", "From/To"),
        ("recommendationsgiven", "name"), ("recommendationsreceived", "name"),
        ("endorsementgiveninfo", "Endorsee"), ("endorsementreceivedinfo", "Endorser"),
        ("memberfollows", "FullName"), ("messages", "FROM/TO"),
        ("importedcontacts", "name"),
    ]),
    ("Organization", [
        ("positions", "Company Name"), ("connections", "Company"),
        ("companyfollows", "Organization"), ("jobapplications", "Company Name"),
        ("savedjobs", "Company Name"), ("onlinejobpostings", "Company Name"),
        ("recommendationsgiven", "Company"), ("recommendationsreceived", "Company"),
        ("adtargeting", "Company Names"), ("jobseekerpreferences", "Dream Companies"),
    ]),
    ("Skill", [
        ("skills", "Name"), ("endorsementgiveninfo", "Skill Name"),
        ("endorsementreceivedinfo", "Skill Name"), ("adtargeting", "Member Skills"),
        ("jobseekerpreferences", "Job Titles"),
    ]),
    ("Job/role", [
        ("positions", "Title"), ("jobapplications", "Job Title"),
        ("savedjobs", "Job Title"), ("onlinejobpostings", "Title"),
        ("jobseekerpreferences", "Job Titles"), ("adtargeting", "Job Titles"),
    ]),
    ("Activity/date", [
        ("comments", "Date"), ("reactions", "Date"), ("votes", "Date"),
        ("shares", "Date"), ("instantreposts", "Date"), ("messages", "DATE"),
        ("searchqueries", "Time"), ("logins", "Login Date"),
        ("events", "Event Time"), ("adsclicked", "Ad clicked Date"),
        ("jobapplications", "Application Date"),
    ]),
    ("Profile URL", [
        ("connections", "URL"), ("invitations", "inviter/inviteeProfileUrl"),
        ("endorsementgiveninfo", "Endorsee Public Url"),
        ("endorsementreceivedinfo", "Endorser Public Url"),
        ("messages", "PROFILE URLS"),
    ]),
])

# ---------------------------------------------------------------------------
# classification helpers
# ---------------------------------------------------------------------------

def route_layer(key):
    """Return the canonical layer for a normalized file key, or None if unknown."""
    for layer, keys in LAYER_ROUTES.items():
        for k in keys:
            if key == k or key.startswith(k):
                return layer
    return None

def classify(entry, quarantine_keys):
    """-> ('_quarantine' | '_unmapped' | <layer>) for a catalog entry."""
    key = entry["key"]
    if key in SENSITIVE_KEYS or key in quarantine_keys or entry.get("class") == "quarantine":
        return "_quarantine"
    layer = route_layer(key)
    return layer or "_unmapped"

def group_catalog(catalog, quarantine_keys):
    """Return OrderedDict layer -> [entries], in LAYER_TITLES order."""
    groups = OrderedDict((l, []) for l in LAYER_TITLES)
    for e in catalog:
        groups[classify(e, quarantine_keys)].append(e)
    # drop empty groups, preserving order
    return OrderedDict((l, v) for l, v in groups.items() if v)

# ---------------------------------------------------------------------------
# mermaid / label sanitizers
# ---------------------------------------------------------------------------

def _mm(text):
    """Sanitize a label for Mermaid mindmap/flowchart node text."""
    s = str(text or "")
    for ch in '()[]{}":;#|<>':
        s = s.replace(ch, " ")
    s = s.replace("\\", " ").replace("\n", " ")
    return " ".join(s.split()) or "?"

def _nid(prefix, key, n=None):
    """Safe mermaid node id."""
    base = "".join(c for c in str(key) if c.isalnum()) or "x"
    return f"{prefix}_{base}" + ("" if n is None else f"_{n}")

# ---------------------------------------------------------------------------
# MINDMAP — markdown (two mermaid diagrams + exhaustive outline)
# ---------------------------------------------------------------------------

def mindmap_markdown(catalog, sources, quarantine_keys, root_label="Export"):
    """Render the data mindmap as Markdown: two Mermaid diagrams (file/field tree
    grouped by vault layer, and a file→entity correlation flowchart) plus an
    exhaustive outline. PII-safe — uses only catalog metadata (file names, column
    names, row counts), never cell values."""
    groups = group_catalog(catalog, quarantine_keys)
    present_keys = {e["key"] for e in catalog}
    n_files = len(catalog)
    n_cols = sum(len(e["columns"]) for e in catalog)

    out = []
    out.append(f"# {root_label} — data mindmap")
    out.append("")
    out.append(f"Sources: **{', '.join(sources) or 'none'}** · "
               f"files: **{n_files}** · total columns: **{n_cols}** · "
               f"layers populated: **{len([g for g in groups if not g.startswith('_')])}**")
    out.append("")
    out.append("Legend: 🔒 = sensitive, catalogued but never imported · "
               "❓ = unmapped (needs an override or new adapter handler).")
    out.append("")

    # ---- Diagram 1: file/field tree
    out.append("## 1. Files & fields (every file, every column)")
    out.append("")
    out.append("```mermaid")
    out.append("mindmap")
    out.append(f"  root(({_mm(root_label)}))")
    for layer, entries in groups.items():
        out.append(f"    {_mm(LAYER_TITLES[layer])}")
        for e in sorted(entries, key=lambda x: x["file"].lower()):
            flag = " 🔒" if layer == "_quarantine" else (" ❓" if layer == "_unmapped" else "")
            out.append(f"      {_mm(e['file'])} {e['rows']}r{flag}")
            for col in e["columns"]:
                out.append(f"        {_mm(col['name'])}")
    out.append("```")
    out.append("")

    # ---- Diagram 2: correlations
    out.append("## 2. Correlations (which files feed which entity, on what field)")
    out.append("")
    out.append("```mermaid")
    out.append("flowchart LR")
    # entity nodes
    for ent in ENTITY_SOURCES:
        out.append(f"  {_nid('E', ent)}(({_mm(ent)}))")
    # edges from present files
    seen_files = set()
    for ent, pairs in ENTITY_SOURCES.items():
        for fkey, field in pairs:
            if any(k == fkey or k.startswith(fkey) for k in present_keys):
                fid = _nid("F", fkey)
                if fkey not in seen_files:
                    out.append(f"  {fid}[{_mm(fkey)}]")
                    seen_files.add(fkey)
                out.append(f"  {fid} -->|{_mm(field)}| {_nid('E', ent)}")
    out.append("```")
    out.append("")

    # ---- Exhaustive outline
    out.append("## 3. Full catalog (outline)")
    out.append("")
    for layer, entries in groups.items():
        out.append(f"### {LAYER_TITLES[layer]}")
        out.append("")
        for e in sorted(entries, key=lambda x: x["file"].lower()):
            flag = " 🔒" if layer == "_quarantine" else (" ❓" if layer == "_unmapped" else "")
            cols = ", ".join(c["name"] for c in e["columns"]) or "_(no columns / empty)_"
            out.append(f"- **{e['file']}** · `{e['key']}` · {e['rows']} rows{flag}")
            out.append(f"  - {cols}")
        out.append("")

    # ---- correlations outline
    out.append("## 4. Correlations (entity → contributing file·field)")
    out.append("")
    for ent, pairs in ENTITY_SOURCES.items():
        live = [(k, f) for k, f in pairs
                if any(pk == k or pk.startswith(k) for pk in present_keys)]
        if not live:
            continue
        out.append(f"- **{ent}** — " + "; ".join(f"`{k}`·{f}" for k, f in live))
    out.append("")
    return "\n".join(out)

# ---------------------------------------------------------------------------
# Obsidian .canvas helpers
# ---------------------------------------------------------------------------

def _canvas_text_node(nid, text, x, y, w, h, color=None):
    """Build one Obsidian .canvas text node dict (id, position, size, optional
    preset color)."""
    node = {"id": nid, "type": "text", "text": text,
            "x": x, "y": y, "width": w, "height": h}
    if color:
        node["color"] = color
    return node

def _canvas_edge(eid, frm, to, label=None, from_side="right", to_side="left"):
    """Build one Obsidian .canvas edge dict connecting node `frm`→`to`, with an
    optional label and connection sides."""
    edge = {"id": eid, "fromNode": frm, "toNode": to,
            "fromSide": from_side, "toSide": to_side}
    if label:
        edge["label"] = label
    return edge

# Obsidian canvas preset colors: "1"=red "2"=orange "3"=yellow "4"=green
# "5"=cyan "6"=purple
_LAYER_COLOR = {
    "00-me": "4", "10-people": "5", "15-organizations": "5", "20-reputation": "4",
    "30-voice": "6", "40-career": "3", "50-mirror": "2", "60-learning": "4",
    "70-services": "5", "80-search": "6", "events": "3",
    "_quarantine": "1", "_unmapped": "2",
}

def mindmap_canvas(catalog, sources, quarantine_keys, root_label="Export"):
    """Render the same mindmap as an Obsidian .canvas JSON string: a root→layer→
    file tree on the left and the correlation entity cluster on the right. PII-safe
    — built only from catalog metadata (file/column names + counts), never cell
    values."""
    import json
    groups = group_catalog(catalog, quarantine_keys)
    present_keys = {e["key"] for e in catalog}
    nodes, edges = [], []

    # root
    nodes.append(_canvas_text_node("root", f"# {root_label}\n\ndata mindmap",
                                   -1700, 0, 240, 120))
    LAYER_X, FILE_X, ENT_X = -1340, -920, 520
    FILE_W = 360
    y = 0
    row_gap = 24
    for layer, entries in groups.items():
        lid = _nid("L", layer)
        entries = sorted(entries, key=lambda x: x["file"].lower())
        layer_top = y
        for e in entries:
            ncol = len(e["columns"])
            h = max(70, 46 + 18 * ncol)
            flag = " 🔒" if layer == "_quarantine" else (" ❓" if layer == "_unmapped" else "")
            cols = "\n".join(f"· {c['name']}" for c in e["columns"]) or "_(empty)_"
            txt = f"**{e['file']}**{flag}\n_{e['key']} · {e['rows']} rows_\n\n{cols}"
            fid = _nid("F", e["key"])
            nodes.append(_canvas_text_node(fid, txt, FILE_X, y, FILE_W, h,
                                           _LAYER_COLOR.get(layer)))
            edges.append(_canvas_edge(_nid("e", layer + e["key"]), lid, fid))
            y += h + row_gap
        layer_h = max(80, y - layer_top - row_gap)
        nodes.append(_canvas_text_node(lid,
                     f"### {LAYER_TITLES[layer]}\n({len(entries)} files)",
                     LAYER_X, layer_top, 300, layer_h, _LAYER_COLOR.get(layer)))
        edges.append(_canvas_edge(_nid("re", layer), "root", lid))
        y += 60

    # entity cluster (correlations) on the right
    ey = 0
    for ent, pairs in ENTITY_SOURCES.items():
        live = [(k, f) for k, f in pairs
                if any(pk == k or pk.startswith(k) for pk in present_keys)]
        if not live:
            continue
        eid = _nid("E", ent)
        nodes.append(_canvas_text_node(eid, f"## {ent}\n({len(live)} sources)",
                                       ENT_X, ey, 260, 120, "6"))
        for k, f in live:
            fid = _nid("F", _firstkey(present_keys, k))
            edges.append(_canvas_edge(_nid("ce", ent + k), fid, eid, f,
                                      from_side="right", to_side="left"))
        ey += 200

    return json.dumps({"nodes": nodes, "edges": edges}, indent=2)

def _firstkey(present_keys, prefix):
    """Return the first present catalog key equal to or prefixed by `prefix` (so a
    correlation edge targets the actual file node, e.g. sharded jobapplications_1);
    falls back to `prefix` itself if none present."""
    for k in present_keys:
        if k == prefix or k.startswith(prefix):
            return k
    return prefix

# ---------------------------------------------------------------------------
# BRAIN STRUCTURE — the designed vault tree (pruned canonical taxonomy).
# Returns (markdown, canvas_json, spec_dict). spec_dict is the build contract.
# ---------------------------------------------------------------------------

# Always-present scaffolding the builder emits regardless of data.
_ALWAYS = ["Home.md", "<agent-guide>.md", "_COVERAGE.md", "_BUILD_REPORT.md"]
# Synthesis + uncategorized + quarantine are conditional, handled below.

def brain_structure(catalog, sources, quarantine_keys, stem="export"):
    """Design the brain folder/note tree from the catalog using the fixed
    canonical taxonomy, pruned to layers that actually have data. Emit
    (markdown, canvas_json, spec_dict)."""
    import json
    groups = group_catalog(catalog, quarantine_keys)
    present_layers = [l for l in LAYER_ROUTES if l in groups]  # canonical order
    has_quar = "_quarantine" in groups
    has_unmapped = "_unmapped" in groups

    # ---- build the spec (machine-readable contract the builder consumes) ----
    spec_layers = []
    for layer in present_layers:
        entries = groups[layer]
        spec_layers.append({
            "folder": layer,
            "purpose": LAYER_PURPOSE.get(layer, ""),
            "source_files": sorted(e["file"] for e in entries),
            "source_keys": sorted(e["key"] for e in entries),
            "color": _LAYER_COLOR.get(layer, ""),
        })
    # synthesis is always offered (deterministic drafts)
    spec_layers.append({
        "folder": "90-synthesis",
        "purpose": "Goal-driven synthesis notes (network map, target companies, "
                   "positions-i-hold [draft], positioning-gaps [draft])",
        "source_files": [], "source_keys": [], "color": "6",
    })
    if has_unmapped:
        spec_layers.append({
            "folder": "99-uncategorized",
            "purpose": "Files no adapter recognized — summarized, never dropped",
            "source_files": sorted(e["file"] for e in groups["_unmapped"]),
            "source_keys": sorted(e["key"] for e in groups["_unmapped"]),
            "color": "2",
        })
    spec = {
        "version": 1,
        "sources": list(sources),
        "taxonomy": "canonical-pruned",
        "always": _ALWAYS,
        "layers": spec_layers,
        "quarantine": {
            "folder": "_quarantine",
            "present": has_quar,
            "files": sorted(e["file"] for e in groups.get("_quarantine", [])),
            "note": "Catalogued for transparency; never imported. Message bodies "
                    "never read (only per-person count + last-contact signal).",
        },
        "entities": {ent: [k for k, _ in pairs
                           if any(e["key"] == k or e["key"].startswith(k)
                                  for e in catalog)]
                     for ent, pairs in ENTITY_SOURCES.items()},
    }

    # ---- markdown (mermaid tree, styled like the mindmap) ----
    out = []
    out.append(f"# {stem.title()} — designed brain structure")
    out.append("")
    out.append(f"Taxonomy: **canonical, pruned** · layers: "
               f"**{len(present_layers)} populated** (+ 90-synthesis"
               f"{', 99-uncategorized' if has_unmapped else ''}). "
               f"Built into `{stem}-brain/`.")
    out.append("")
    out.append("```mermaid")
    out.append("mindmap")
    out.append(f"  root(({_mm(stem + '-brain')}))")
    out.append("    Home.md  + agent guide (CLAUDE.md / AGENTS.md)")
    for layer in present_layers:
        n = len(groups[layer])
        out.append(f"    {_mm(layer)}  {n} sources")
        out.append(f"      {_mm(LAYER_PURPOSE.get(layer, ''))}")
    out.append("    90-synthesis")
    out.append("      network-map / target-companies / drafts")
    if has_unmapped:
        out.append("    99-uncategorized")
        out.append("      unrecognized files summarized")
    if has_quar:
        out.append("    🔒 _quarantine  never imported")
    out.append("    _COVERAGE.md  + _BUILD_REPORT.md")
    out.append("```")
    out.append("")
    out.append("## Layers (source files per layer)")
    out.append("")
    for layer in present_layers:
        out.append(f"### `{layer}/` — {LAYER_PURPOSE.get(layer, '')}")
        files = sorted(e["file"] for e in groups[layer])
        out.append("  - " + ", ".join(files))
        out.append("")
    out.append("### `90-synthesis/` — goal-driven synthesis")
    out.append("  - network-map, target-companies, positions-i-hold (draft), "
               "positioning-gaps (draft)")
    out.append("")
    if has_unmapped:
        out.append("### `99-uncategorized/` — unrecognized (summarized, not dropped)")
        out.append("  - " + ", ".join(sorted(e["file"] for e in groups["_unmapped"])))
        out.append("")
    if has_quar:
        out.append("### 🔒 `_quarantine/` — catalogued, never imported")
        out.append("  - " + ", ".join(sorted(e["file"] for e in groups["_quarantine"])))
        out.append("")

    # ---- canvas (same tree) ----
    nodes, edges = [], []
    nodes.append(_canvas_text_node("broot", f"# {stem}-brain\n\ndesigned structure",
                                   -700, 0, 240, 120))
    y = 0
    order = present_layers + ["90-synthesis"]
    if has_unmapped:
        order.append("99-uncategorized")
    if has_quar:
        order.append("_quarantine")
    for layer in order:
        if layer in groups:
            files = sorted(e["file"] for e in groups[layer])
            body = "\n".join(f"· {f}" for f in files)
            purpose = LAYER_PURPOSE.get(layer, "")
        elif layer == "90-synthesis":
            body = "· network-map\n· target-companies\n· drafts"
            purpose = "synthesis"
        else:
            body = ""
            purpose = ""
        h = max(70, 46 + 18 * (body.count("\n") + 1))
        color = _LAYER_COLOR.get(layer, "6")
        nid = _nid("BL", layer)
        flag = " 🔒" if layer == "_quarantine" else ""
        nodes.append(_canvas_text_node(
            nid, f"### {layer}/{flag}\n_{purpose}_\n\n{body}", -300, y, 360, h, color))
        edges.append(_canvas_edge(_nid("be", layer), "broot", nid))
        y += h + 28
    canvas = json.dumps({"nodes": nodes, "edges": edges}, indent=2)

    return "\n".join(out), canvas, spec
