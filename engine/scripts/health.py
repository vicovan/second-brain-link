#!/usr/bin/env python3
"""
health.py — the brain's self-check (smart-brain layer, deterministic, zero API).

Writes at the brain root:
  _HEALTH.md    — human report: orphan notes, unresolved-link rate, per-source
                  freshness ("snapshot sharpness" — latest record date each
                  source actually carries; exports are snapshots, we say so),
                  layer balance, near-duplicate name SUSPICIONS (never merged),
                  conflicting merged-person claims, and deterministic
                  link-candidate suggestions an agent can apply/reject.
  _HEALTH.json  — the same, machine-readable (agents act on this).

Also (both fed by graph.json, so they run on any brain built or retrofitted
with the current engine):
  90-synthesis/graph-insights.md — bridge nodes (cross-layer connectors), top
                  cross-source people, dormant strong ties (real revival list).
  _canvas/brain-overview.canvas  — a JSON Canvas map: one node per layer,
                  edges weighted by real cross-layer link counts.

Every number here is derived from the vault on disk. Suspicions are labelled
suspicions; nothing is auto-merged or invented. Stdlib only.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graphdata


def _nk(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# Anything that could read as a phone number must never land in generated
# Markdown (the vault-wide PII sweep enforces this) — date-hash filenames like
# `2023-11-02-9f8e` pattern-match it, so those ids stay in _HEALTH.json only.
_DIGITY = re.compile(r"\d[\d ().-]{9,}\d")


def _md_safe(s):
    return not _DIGITY.search(s or "")


def _wl(node):
    """Obsidian link that RESOLVES: filename stem as target, title as alias
    (a note's title isn't always its filename — identity.md is 'Jane Doe')."""
    stem = Path(node["path"]).stem
    title = node.get("title") or stem
    return f"[[{stem}]]" if stem.lower() == title.lower() else f"[[{stem}|{title}]]"


def build_health(brain: Path):
    """Compute the health dict for a built brain (graph.json is built fresh)."""
    g = graphdata.build_graph_json(brain)
    nodes = g["nodes"]
    edges = g["edges"]
    meta_types = {"structure", "moc", "guide", "dashboard", "catalog", "note", "file"}

    # orphans: content nodes with no edges at all
    orphans = [n for n in nodes
               if n["deg"] == 0 and n["type"] not in meta_types and n["layer"]]

    # unresolved wikilinks: links whose target note doesn't exist
    by_title = {n["title"].lower() for n in nodes}
    by_stem = {Path(n["path"]).stem.lower() for n in nodes}
    total_links = 0
    unresolved = Counter()
    for n in nodes:
        try:
            body = (brain / n["path"]).read_text(encoding="utf-8")
        except Exception:
            continue
        for m in re.finditer(r"\[\[([^\]\|#]+)(?:[\|#][^\]]*)?\]\]", body):
            total_links += 1
            t = m.group(1).strip().lower()
            if t not in by_title and t not in by_stem:
                unresolved[m.group(1).strip()] += 1

    # per-source freshness: the latest record date each source actually carries
    fresh = {}
    for n in nodes:
        d = ""
        for k in ("last_contact", "created"):
            v = str(n.get(k, "") or "")
            if re.match(r"^\d{4}-\d{2}", v):
                d = v[:10]
                break
        if not d:
            continue
        for s in n.get("sources", []):
            if d > fresh.get(s, ""):
                fresh[s] = d
    # fall back to frontmatter created via a scan of raw files is already covered
    # (graphdata carries created only for some kinds; last_contact for people)

    # near-duplicate name suspicions: same nk() prefix families among people
    people = [n for n in nodes if n["type"] == "person"]
    by_key = defaultdict(list)
    for n in people:
        k = _nk(n["title"])
        if len(k) >= 6:
            by_key[k[:10]].append(n["title"])
    suspects = sorted(set(
        tuple(sorted(set(v))) for v in by_key.values() if len(set(v)) > 1))

    # conflicting merged-person claims (the alt_* fields the builder preserves)
    conflicts = []
    for n in people:
        try:
            head = (brain / n["path"]).read_text(encoding="utf-8")[:2000]
        except Exception:
            continue
        for m in re.finditer(r"^alt_(company|role|industry|location):", head, re.M):
            conflicts.append({"note": n["id"], "field": m.group(1)})

    # deterministic link candidates for orphans: shared org/company mention or
    # a shared non-source tag family — suggestions only, agent applies/rejects
    cand = []
    if orphans:
        tag_index = defaultdict(set)
        for n in nodes:
            if n["type"] in meta_types:
                continue
            try:
                fmd, _ = graphdata._parse_front((brain / n["path"]).read_text(encoding="utf-8"))
            except Exception:
                continue
            tags = fmd.get("tags")
            tags = tags if isinstance(tags, list) else []
            for t in tags:
                if isinstance(t, str) and "/" in t and not t.startswith("source/"):
                    tag_index[t].add(n["id"])
        for o in orphans[:50]:
            try:
                fmd, _ = graphdata._parse_front((brain / o["path"]).read_text(encoding="utf-8"))
            except Exception:
                continue
            tags = fmd.get("tags")
            tags = tags if isinstance(tags, list) else []
            for t in tags:
                peers = tag_index.get(t, set()) - {o["id"]}
                if peers and not t.startswith("source/"):
                    cand.append({"orphan": o["id"], "via": t,
                                 "suggest": sorted(peers)[:3]})
                    break

    layers = [{"key": l["key"], "folder": l["folder"], "count": l["count"]}
              for l in g["layers"]]
    return {
        "schema": "sbl-health/1",
        "stats": g["stats"],
        "orphans": sorted(o["id"] for o in orphans),
        "links": {"total": total_links,
                  "unresolved": sum(unresolved.values()),
                  "unresolved_titles": [t for t, _ in unresolved.most_common(20)]},
        "freshness": dict(sorted(fresh.items())),
        "layers": layers,
        "duplicate_suspicions": [list(t) for t in suspects[:20]],
        "conflicts": conflicts[:50],
        "link_candidates": cand[:40],
    }, g


def render_health_md(h):
    L = ["---", "type: health", "tags: [health]", "---", "",
         "# 🩺 Brain health", "",
         f"Nodes: **{h['stats']['nodes']}** · edges: **{h['stats']['edges']}** · "
         f"cross-source edges: **{h['stats']['cross_source_edges']}**", "",
         "## Snapshot freshness (per source)", "",
         "Exports are snapshots — sharp on history, blind to this week. The latest "
         "record date each source actually carries:", ""]
    if h["freshness"]:
        L += ["| Source | Latest record |", "|---|---|"]
        L += [f"| {s} | {d} |" for s, d in h["freshness"].items()]
    else:
        L.append("*(no dated records found)*")
    L += ["", "## Links", "",
          f"- {h['links']['total']} wikilinks · **{h['links']['unresolved']}** unresolved"]
    for t in [x for x in h["links"]["unresolved_titles"] if _md_safe(x)][:10]:
        L.append(f"    - `[[{t}]]` has no note")
    L += ["", f"## Orphan notes ({len(h['orphans'])})", "",
          "Notes with no connections — candidates for linking or pruning:", ""]
    listable = [o for o in h["orphans"] if _md_safe(o)]
    hidden = len(h["orphans"]) - len(listable)
    L += [f"- `{o}`" for o in listable[:30]] or (
        [] if hidden else ["*(none — well linked)*"])
    if hidden:
        L.append(f"- …plus {hidden} dated note(s) — full list in `_HEALTH.json`")
    if h["link_candidates"]:
        cands = [c for c in h["link_candidates"][:20]
                 if _md_safe(c["orphan"]) and all(_md_safe(s) for s in c["suggest"])]
        if cands:
            L += ["", "## Link candidates (suggestions — apply or reject, never automatic)", ""]
            for c in cands:
                L.append(f"- `{c['orphan']}` shares `{c['via']}` with "
                         + ", ".join(f"`{s}`" for s in c["suggest"]))
    if h["duplicate_suspicions"]:
        L += ["", "## Possible duplicate people (SUSPICIONS ONLY — never auto-merged)", ""]
        for grp in h["duplicate_suspicions"][:10]:
            L.append("- " + " · ".join(grp))
    if h["conflicts"]:
        L += ["", "## Conflicting claims across sources", "",
              "The builder preserved both versions (`alt_*` fields) — reconcile by hand "
              "or ask your agent to write 90-synthesis/reconciliation.md:", ""]
        seen = set()
        for c in [x for x in h["conflicts"] if _md_safe(x["note"])][:20]:
            k = c["note"] + c["field"]
            if k in seen:
                continue
            seen.add(k)
            L.append(f"- `{c['note']}` — conflicting **{c['field']}**")
    L += ["", "## Layer balance", "", "| Layer | Notes |", "|---|---|"]
    L += [f"| `{l['folder']}/` | {l['count']} |" for l in h["layers"]]
    L += ["", "_Generated by health.py (deterministic). Machine-readable twin: `_HEALTH.json`._"]
    return "\n".join(L)


def write_graph_insights(brain: Path, g):
    """90-synthesis/graph-insights.md — bridge nodes, cross-source people,
    dormant strong ties. All from the real graph; drafts nothing."""
    nodes = {n["id"]: n for n in g["nodes"]}
    # bridge nodes: connect the most distinct layers
    span = defaultdict(set)
    for e in g["edges"]:
        a, b = nodes.get(e["a"]), nodes.get(e["b"])
        if not a or not b:
            continue
        if a["layer"] != b["layer"]:
            span[e["a"]].add(b["layer"])
            span[e["b"]].add(a["layer"])
    bridges = sorted(((len(v), k) for k, v in span.items()), reverse=True)[:10]
    multi = sorted((n for n in g["nodes"]
                    if n["type"] == "person" and len(n.get("sources", [])) >= 2),
                   key=lambda n: -len(n.get("sources", [])))[:15]
    dormant = sorted((n for n in g["nodes"]
                      if n["type"] == "person" and (n.get("strength") or 0) >= 4
                      and str(n.get("status", "")) in ("dormant", "cold")),
                     key=lambda n: -(n.get("strength") or 0))[:15]
    L = ["---", "type: synthesis", "tags: [synthesis, graph]", "---", "",
         "# Graph insights", "",
         "Derived from `graph.json` (typed, weighted edges — the same data the "
         "Studio's Neural view traverses).", "",
         "## Bridge nodes (connect the most layers)", ""]
    L += [f"- {_wl(nodes[k])} — spans {n} layers" for n, k in bridges] or ["*(none)*"]
    L += ["", "## Strongest multi-context people (appear in several sources)", ""]
    L += [f"- {_wl(n)} — {', '.join(n['sources'])}" for n in multi] or ["*(none)*"]
    L += ["", "## Dormant strong ties (real revival candidates)", ""]
    L += [f"- {_wl(n)} — strength {n.get('strength')}/5, last contact "
          f"{n.get('last_contact', n.get('created', '?')) or '?'}" for n in dormant] or ["*(none)*"]
    out = brain / "90-synthesis" / "graph-insights.md"
    if not out.parent.is_dir():   # company variant keeps 90-synthesis; guard anyway
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


def write_overview_canvas(brain: Path, g):
    """_canvas/brain-overview.canvas — JSON Canvas: one node per layer, edges
    weighted by real cross-layer link counts (opens natively in Obsidian)."""
    lay_nodes = []
    pos = {}
    n_layers = max(1, len(g["layers"]))
    for i, l in enumerate(g["layers"]):
        x = (i % 4) * 360
        y = (i // 4) * 240
        pos[l["key"]] = f"layer-{l['key']}"
        lay_nodes.append({"id": f"layer-{l['key']}", "type": "text",
                          "text": f"## {l['label']}\n`{l['folder']}/` — {l['count']} notes",
                          "x": x, "y": y, "width": 300, "height": 140})
    cross = Counter()
    nodes = {n["id"]: n for n in g["nodes"]}
    for e in g["edges"]:
        a, b = nodes.get(e["a"]), nodes.get(e["b"])
        if not a or not b or a["layer"] == b["layer"]:
            continue
        key = tuple(sorted((a["layer"], b["layer"])))
        cross[key] += 1
    canvas_edges = []
    for i, ((la, lb), n) in enumerate(sorted(cross.items())):
        if la not in pos or lb not in pos:
            continue
        canvas_edges.append({"id": f"e{i}", "fromNode": pos[la], "toNode": pos[lb],
                             "fromSide": "right", "toSide": "left",
                             "label": f"{n} links"})
    out = brain / "_canvas" / "brain-overview.canvas"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"nodes": lay_nodes, "edges": canvas_edges},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def run(brain: Path):
    """Write all health artifacts for `brain`. Returns the health dict."""
    brain = Path(brain)
    h, g = build_health(brain)
    (brain / "_HEALTH.json").write_text(
        json.dumps(h, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (brain / "_HEALTH.md").write_text(render_health_md(h) + "\n", encoding="utf-8")
    write_graph_insights(brain, g)
    write_overview_canvas(brain, g)
    return h


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Brain health report + graph insights + overview canvas.")
    ap.add_argument("brain")
    args = ap.parse_args()
    h = run(Path(args.brain).expanduser())
    print(f"_HEALTH.md/.json: {len(h['orphans'])} orphans, "
          f"{h['links']['unresolved']} unresolved links, "
          f"{len(h['duplicate_suspicions'])} duplicate suspicions "
          f"→ + 90-synthesis/graph-insights.md + _canvas/brain-overview.canvas")
