#!/usr/bin/env python3
"""
graphdata.py — machine-readable graph sidecar (`graph.json`, schema sbl-graph/1).

Scans a BUILT brain (the rendered Obsidian vault) and emits one compact JSON
describing the knowledge graph: nodes (one per note, with layer/type/sources/
strength/geo/avatar), typed+weighted edges (derived from the same structures the
vault renders — a person's `company:` property, event attendee links, an org's
"People here" list, purchase merchants, plain wikilinks), ordered layers with
per-layer counts + dominant sources, and summary stats.

This is what the Studio's Neural view and graph-augmented retrieval consume, and
what any agent can read as the traversal map instead of re-parsing every note
(documented in `_GRAPH.md`). NOT an `--emit` target: it is an always-on sidecar
of the Obsidian vault, like `_SUMMARY.md`.

NOTE the name collision: `.obsidian/graph.json` (written by `analyze.py
--graph-config`) is Obsidian's own graph-STYLING config. THIS file lives at the
brain root and is a node/edge DATASET. Different files, both documented in
`_STRUCTURE.md`.

Privacy: node ids/titles are note paths/titles already public in the vault.
Frontmatter fields carried over are the graph-relevant subset only — never
email/phone (which default builds don't write anyway).

Stdlib only. Zero network. Deterministic (sorted output).
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SCHEMA = "sbl-graph/1"

# Layer display order — mirrors the build order in build_vault.layer_roles(),
# plus the analyze-written 95-goals pseudo-layer. Folders resolve per subject
# through build_vault.layout_for() (never hardcode a layer folder).
LAYER_ORDER = ["root", "people", "orgs", "reputation", "voice", "shopping",
               "career", "jobs", "mirror", "learning", "services", "search", "places",
               "synthesis", "goals", "uncategorized"]

# (person label, company label) per layer key — honest short names for HUD cards.
LAYER_LABELS = {
    "root": ("Me", "Organization"), "people": ("People", "People"),
    "orgs": ("Organizations", "Organizations"),
    "reputation": ("Reputation", "Brand"), "voice": ("Voice", "Content"),
    "shopping": ("Shopping", "Procurement"), "career": ("Career", "Pipeline"),
    "jobs": ("Jobs", "Hiring"),
    "mirror": ("Mirror", "Market view"), "learning": ("Learning", "Knowledge"),
    "services": ("Services", "Support"), "search": ("Search", "Signals"),
    "places": ("Places", "Locations"), "synthesis": ("Synthesis", "Synthesis"),
    "goals": ("Goals", "Goals"),
    "uncategorized": ("Uncategorized", "Uncategorized"),
}

# folders never scanned into the graph
_SKIP_DIRS = {"_quarantine", "_notes", ".obsidian", ".trash", "attachments",
              "_assets", "_profile", "copilot-prompts", "gbrain"}

# edge type → weight used when no better signal exists
_W_DEFAULT = {"linked": 0.3, "works_at": 0.8, "member_of": 0.5,
              "attended": 0.4, "purchased_from": 0.4, "correlated": 1.0}

_WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+)(?:[\|#][^\]]*)?\]\]")


def _parse_front(text):
    """Parse the engine's own fm() frontmatter format (a strict subset of YAML:
    `key: scalar` + block lists of `  - item`). Returns (dict, body). Quoted
    scalars are unquoted. Good enough because WE wrote the format."""
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    fmd, i, key = {}, 1, None
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            i += 1
            break
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            fmd[key] = _unquote(val) if val else ""
        elif key and re.match(r"^\s+-\s", line):
            item = _unquote(re.sub(r"^\s+-\s*", "", line).strip())
            if not isinstance(fmd.get(key), list):
                fmd[key] = [] if fmd.get(key) in ("", None) else [fmd[key]]
            fmd[key].append(item)
        i += 1
    return fmd, "\n".join(lines[i:])


def _unquote(s):
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return s


def _inner_link(s):
    """`[[Acme Cloud]]` → `Acme Cloud`; plain strings pass through."""
    m = _WIKILINK_RE.search(s or "")
    return m.group(1).strip() if m else (s or "").strip()


def _sources_of(fmd):
    """A note's contributing sources: the `sources` list, else source/* tags."""
    srcs = fmd.get("sources")
    if isinstance(srcs, list) and srcs:
        return sorted(str(s) for s in srcs if s)
    if isinstance(srcs, str) and srcs:
        return [srcs]
    tags = fmd.get("tags")
    tags = tags if isinstance(tags, list) else ([tags] if tags else [])
    out = sorted({t.split("/", 1)[1] for t in tags
                  if isinstance(t, str) and t.startswith("source/")})
    return out


def _layer_maps(subject):
    """(folder→layer_key, layer_key→folder) for `subject`, including 95-goals."""
    import build_vault
    lay = dict(build_vault.layout_for(subject))
    lay["goals"] = "95-goals"
    folder_to_key = {v: k for k, v in lay.items()}
    return folder_to_key, lay


def detect_subject(brain_root):
    """'company' iff the company-variant root folder exists, else 'person'."""
    import build_vault
    comp_root = build_vault.layout_for("company")["root"]
    return "company" if (Path(brain_root) / comp_root).is_dir() else "person"


def build_graph_json(brain_root, subject=None, entity=""):
    """Scan the built brain at `brain_root` → the sbl-graph/1 dict. Pure function
    of the vault on disk; caller serializes/writes (so the manifest records it)."""
    root = Path(brain_root)
    subject = subject or detect_subject(root)
    folder_to_key, key_to_folder = _layer_maps(subject)

    notes = {}          # rel path (no .md) -> node dict
    by_title = {}       # lower title -> id (first wins, sorted walk = stable)
    raw = {}            # id -> (fmd, body)

    md_files = sorted(p for p in root.rglob("*.md")
                      if not any(seg in _SKIP_DIRS or seg.startswith(".")
                                 for seg in p.relative_to(root).parts[:-1]))
    for p in md_files:
        rel = p.relative_to(root)
        nid = str(rel)[:-3].replace("\\", "/")
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        fmd, body = _parse_front(text)
        top = rel.parts[0] if len(rel.parts) > 1 else ""
        layer = folder_to_key.get(top, "")
        title = str(fmd.get("title") or p.stem)
        node = {"id": nid, "path": str(rel).replace("\\", "/"),
                "title": title, "layer": layer,
                "type": str(fmd.get("type") or "note")}
        srcs = _sources_of(fmd)
        if srcs:
            node["sources"] = srcs
        for f_num in ("strength", "lat", "lng"):
            v = fmd.get(f_num)
            if v not in ("", None, []):
                try:
                    node[f_num] = float(v) if "." in str(v) else int(float(v))
                except (TypeError, ValueError):
                    pass
        for f_str in ("avatar", "avatar_url", "status", "relationship"):
            v = fmd.get(f_str)
            if isinstance(v, str) and v:
                node[f_str] = v
        notes[nid] = node
        raw[nid] = (fmd, body)
        by_title.setdefault(p.stem.lower(), nid)

    # ---- edges (typed, weighted, deduped on undirected (a,b,type) max-w) ----
    edges = {}

    def add_edge(a, b, etype, w=None, src=""):
        if not a or not b or a == b:
            return
        key = (min(a, b), max(a, b), etype)
        w = w if w is not None else _W_DEFAULT.get(etype, 0.3)
        w = round(min(max(w, 0.05), 1.0), 2)
        cur = edges.get(key)
        if cur is None or w > cur["w"]:
            edges[key] = {"a": a, "b": b, "type": etype, "w": w,
                          **({"src": src} if src else {})}

    def resolve(title):
        return by_title.get((title or "").strip().lower())

    for nid, node in notes.items():
        fmd, body = raw[nid]
        ntype = node["type"]
        src0 = (node.get("sources") or [""])[0]
        strength = node.get("strength")

        # frontmatter-typed relations
        comp = _inner_link(str(fmd.get("company") or ""))
        if comp and ntype == "person":
            add_edge(nid, resolve(comp), "works_at",
                     (strength / 5.0) if strength else None, src0)
        dept = _inner_link(str(fmd.get("dept") or ""))
        if dept:
            add_edge(nid, resolve(dept), "member_of", 0.6, src0)
        merch = _inner_link(str(fmd.get("merchant") or ""))
        if merch and ntype == "purchase":
            add_edge(nid, resolve(merch), "purchased_from", None, src0)

        # body wikilinks, typed by the note that carries them
        body_type = ("attended" if ntype in ("events", "meetings")
                     else "member_of" if ntype in ("company", "organization")
                     else "works_at" if ntype == "identity"
                     else "linked")
        hits = Counter(m.group(1).strip() for m in _WIKILINK_RE.finditer(body))
        for target_title, n in hits.items():
            tid = resolve(target_title)
            if tid is None:
                continue
            if body_type == "attended":
                add_edge(nid, tid, "attended", min(n, 5) / 5.0, src0)
            elif body_type == "member_of" and notes[tid]["type"] == "person":
                add_edge(nid, tid, "member_of", 0.5, src0)
            elif body_type == "works_at" and notes[tid]["type"] in ("company",
                                                                    "organization"):
                add_edge(nid, tid, "works_at", 1.0, src0)
            else:
                add_edge(nid, tid, "linked", None, src0)

    edge_list = sorted(edges.values(), key=lambda e: (e["a"], e["b"], e["type"]))

    # ---- degree ------------------------------------------------------------
    deg = Counter()
    for e in edge_list:
        deg[e["a"]] += 1
        deg[e["b"]] += 1
    for nid, node in notes.items():
        node["deg"] = deg.get(nid, 0)

    # ---- layers (ordered, non-empty only) ----------------------------------
    idx = 1 if subject == "company" else 0
    layers = []
    for key in LAYER_ORDER:
        members = [n for n in notes.values() if n["layer"] == key]
        if not members:
            continue
        scount = Counter()
        for n in members:
            for s in n.get("sources", []):
                scount[s] += 1
        layers.append({"key": key, "folder": key_to_folder.get(key, ""),
                       "label": LAYER_LABELS.get(key, (key, key))[idx],
                       "count": len(members),
                       "sources": dict(sorted(scount.items()))})

    # ---- stats -------------------------------------------------------------
    def _cross(e):
        sa = set(notes[e["a"]].get("sources", []))
        sb = set(notes[e["b"]].get("sources", []))
        return bool(sa) and bool(sb) and not (sa & sb)

    node_list = [notes[k] for k in sorted(notes)]
    return {"schema": SCHEMA, "subject": subject,
            "entity": entity or root.name.replace("-brain", ""),
            "generated": datetime.now().strftime("%Y-%m-%d"),
            "layers": layers, "nodes": node_list, "edges": edge_list,
            "stats": {"nodes": len(node_list), "edges": len(edge_list),
                      "cross_source_edges": sum(1 for e in edge_list if _cross(e))}}


def write_graph_json(brain_root, subject=None, entity="", write_fn=None):
    """Build + write `<brain_root>/graph.json`. `write_fn(path, text)` lets the
    build pipeline route the write through its manifest recorder; defaults to a
    plain filesystem write (the analyze.py retrofit path)."""
    graph = build_graph_json(brain_root, subject=subject, entity=entity)
    text = json.dumps(graph, ensure_ascii=False, indent=1)
    out = Path(brain_root) / "graph.json"
    if write_fn is not None:
        write_fn(out, text)
    else:
        out.write_text(text.rstrip() + "\n", encoding="utf-8")
    return graph


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Emit graph.json for a built brain.")
    ap.add_argument("brain", help="path to a built brain (the folder with Home.md)")
    args = ap.parse_args()
    g = write_graph_json(Path(args.brain).expanduser())
    print(f"graph.json: {g['stats']['nodes']} nodes, {g['stats']['edges']} edges, "
          f"{len(g['layers'])} layers → {Path(args.brain) / 'graph.json'}")
