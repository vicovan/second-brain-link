#!/usr/bin/env python3
"""retrieval.py - graph retrieval over a built brain: deterministic spreading activation
(Personalized PageRank over typed, weighted edges). Stdlib only, no network, no model.

A function-for-function port of Studio's src/lib/brain/brain-retrieval.ts (same constants, same
seeding, same iteration order) — tests/run.py checks it against golden output the TypeScript
produced, so the desktop, the web Studio and this CLI rank a brain identically.

    retrieval.py <brain> "who do I know at Acme?" [--as ROLE] [--top N] [--json | --prompt]

`--as ROLE` is a role lens: the same graph seen by a different reader. The role's words become
extra (half-weight) seeds, so a finance lead and an engineer asking the same question start the
walk from different places.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

TYPE_PRIOR = {"correlated": 1.5, "works_at": 1.2, "member_of": 1.1, "attended": 1.0,
              "purchased_from": 0.9, "linked": 0.6}
DAMPING = 0.85
ITERATIONS = 20
TOP_K = 40
FLOOR = 1e-4
MAX_DF = 0.25
MAX_SEEDS = 40
STOP = set(("the and for with that this from your you are our who all have has was were "
            "what when where which while how does did about into not can will more my me "
            "who is a an of in on to at by it its "
            "do so if up we us no or be as he she they them their there here own get got "
            "am been being had do does doing i").split(" "))
META_TITLE = re.compile(r"^_|^(claude|agents|readme|home|vault structure|network map)$", re.I)


def is_meta(n: dict) -> bool:
    return bool(META_TITLE.search(str(n.get("title") or "").strip()))


def has_word(hay: str, term: str) -> bool:
    stem = term[:-1] if len(term) > 3 and term.endswith("s") else term
    return re.search(r"(^|[^a-z0-9])" + re.escape(stem) + r"s?('s)?($|[^a-z0-9])", hay, re.I) is not None


def query_terms(q: str) -> list:
    terms = re.findall(r"[a-z0-9][a-z0-9'-]{1,}", q.lower())
    return [t for t in terms if t not in STOP and len(t) >= 2]


def find_seeds(query: str, notes: list) -> dict:
    terms = query_terms(query)
    if not terms:
        return {}
    df = {t: 0 for t in terms}
    for n in notes:
        hay = ((n.get("title") or "") + " " + (n.get("body") or "")).lower()
        for t in terms:
            if has_word(hay, t):
                df[t] += 1
    cutoff = max(1, len(notes) * MAX_DF)
    rare = [t for t in terms if df[t] <= cutoff]
    if not rare:
        return {}
    terms = rare
    seeds: dict = {}
    ql = query.strip().lower()
    for n in notes:
        if is_meta(n):
            continue
        title = (n.get("title") or "").lower()
        s = 0.0
        if title and (title in ql or title == ql):
            s = 1.0
        else:
            hit = sum(1 for t in terms if has_word(title, t))
            if hit:
                s = min(1.0, 0.4 + 0.3 * hit)
        if not s and n.get("body"):
            bl = n["body"].lower()
            hit = sum(1 for t in terms if has_word(bl, t))
            if hit >= max(1, -(-len(terms) // 2)):
                s = 0.5
        if s > 0:
            seeds[n["id"]] = max(seeds.get(n["id"], 0.0), s)
    if len(seeds) <= MAX_SEEDS:
        return seeds
    ids = sorted(seeds.keys(), key=lambda i: -seeds[i])[:MAX_SEEDS]  # stable: ties keep note order
    return {i: seeds[i] for i in ids}


def spread(seeds: dict, node_ids: list, edges: list) -> dict:
    idx = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)
    if not n:
        return {}
    nbr = [[] for _ in range(n)]
    wgt = [[] for _ in range(n)]
    wsum = [0.0] * n
    for e in edges:
        ia, ib = idx.get(e.get("a")), idx.get(e.get("b"))
        if ia is None or ib is None or ia == ib:
            continue
        w = (0.3 if e.get("w") is None else e["w"]) * (TYPE_PRIOR.get(e.get("type") or "linked") or 0.6)
        nbr[ia].append(ib)
        wgt[ia].append(w)
        wsum[ia] += w
        nbr[ib].append(ia)
        wgt[ib].append(w)
        wsum[ib] += w
    tp = [0.0] * n
    tsum = 0.0
    for nid, s in seeds.items():
        i = idx.get(nid)
        if i is not None:
            tp[i] = s
            tsum += s
    if not tsum:
        return {}
    tp = [x / tsum for x in tp]
    p = list(tp)
    for _ in range(ITERATIONS):
        q = [0.0] * n
        for i in range(n):
            pi = p[i]
            if pi <= 0:
                continue
            if wsum[i] > 0:
                share = (DAMPING * pi) / wsum[i]
                ns, ws = nbr[i], wgt[i]
                for j in range(len(ns)):
                    q[ns[j]] += share * ws[j]
            else:
                for j in range(n):
                    q[j] += DAMPING * pi * tp[j]
        for i in range(n):
            q[i] += (1 - DAMPING) * tp[i]
        p = q
    return {node_ids[i]: p[i] for i in range(n) if p[i] > FLOOR}


def build_pack(query: str, notes: list, edges: list, extra_seeds: dict | None = None) -> dict:
    lookup = {nn["id"]: nn for nn in notes}
    seeds = find_seeds(query, notes)
    for k, v in (extra_seeds or {}).items():  # a role lens: half-weight seeds from the role's words
        seeds[k] = max(seeds.get(k, 0.0), v)
    scores = spread(seeds, [nn["id"] for nn in notes], edges)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    act: dict = {}
    for sid in seeds:
        if sid in scores:
            act[sid] = scores[sid]
    for sid, s in ranked:
        if len(act) >= TOP_K:
            break
        act[sid] = s
    activated = set(act)
    sub = [e for e in edges if e.get("a") in activated and e.get("b") in activated]
    adj: dict = {}
    for e in sub:
        adj.setdefault(e["a"], []).append(e["b"])
        adj.setdefault(e["b"], []).append(e["a"])
    seed_ids = [s for s in seeds if s in activated]
    waves = []
    assigned = set(seed_ids)
    frontier = sorted(seed_ids)
    while frontier:
        waves.append(frontier)
        nxt = []
        for nid in frontier:
            for nb in adj.get(nid, []):
                if nb not in assigned:
                    assigned.add(nb)
                    nxt.append(nb)
        frontier = sorted(set(nxt))
    rest = sorted(i for i in activated if i not in assigned)
    if rest:
        waves.append(rest)

    def tname(i):
        return (lookup.get(i) or {}).get("title") or i

    triples = sorted(
        f"{tname(e['a'])} —{e['type']}→ {tname(e['b'])}"
        + (f" ({e['src']}" + (f", w {_num(e['w'])}" if e.get("w") is not None else "") + ")" if e.get("src") else "")
        for e in sub if e.get("type") and e.get("type") != "linked")
    return {"query": query, "seeds": seed_ids, "activations": act, "waves": waves,
            "edges": sub, "triples": triples, "used": []}


def _num(w) -> str:
    """JS number → string (1 not 1.0)."""
    return str(int(w)) if float(w).is_integer() else repr(float(w))


def pack_to_prompt(pack: dict, by_id: dict, max_chars: int = 6000) -> str:
    lines = ["Activated knowledge subgraph for this question (via graph traversal):"]
    if pack["triples"]:
        lines += ["", "Relations:"] + ["- " + t for t in pack["triples"][:40]]
    lines += ["", "Notes (by activation):"]
    budget = max_chars - len("\n".join(lines))
    for nid, _ in sorted(pack["activations"].items(), key=lambda kv: -kv[1]):
        n = by_id.get(nid)
        if not n:
            continue
        head = f"- [[{n['title']}]] ({n.get('type')})"
        excerpt = re.sub(r"\s+", " ", n.get("body") or "")[:200]
        row = f"{head}: {excerpt}" if excerpt else head
        if budget - len(row) < 0:
            break
        lines.append(row)
        budget -= len(row) + 1
    lines += ["", "Cite the notes you actually use as [[wikilinks]] so the graph can light the path."]
    return "\n".join(lines)


# ------------------------------------------------------------------ a built brain → notes + edges
_FM_RE = re.compile(r"^---\n.*?\n---\n?", re.S)


def load_brain(brain: pathlib.Path) -> tuple[list, list]:
    """Notes (id/title/type/body) and edges from the brain's graph.json; bodies read from disk."""
    g = json.loads((brain / "graph.json").read_text(encoding="utf-8"))
    notes = []
    for nd in g.get("nodes", []):
        p = brain / str(nd.get("path") or (str(nd["id"]) + ".md"))
        body = ""
        try:
            body = _FM_RE.sub("", p.read_text(encoding="utf-8", errors="replace"), count=1)[:4000]
        except OSError:
            pass
        notes.append({"id": nd["id"], "title": nd.get("title") or nd["id"], "type": nd.get("type") or "note",
                      "body": body})
    edges = [{"a": e.get("a"), "b": e.get("b"), "type": e.get("type"), "w": e.get("w"), "src": e.get("src")}
             for e in g.get("edges", [])]
    return notes, edges


def role_seeds(role: str, notes: list) -> dict:
    """A role lens: the role's own words seed the walk at half weight."""
    return {k: v * 0.5 for k, v in find_seeds(role, notes).items()} if role else {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Graph retrieval (Personalized PageRank) over a built brain")
    ap.add_argument("brain")
    ap.add_argument("query")
    ap.add_argument("--as", dest="role", default="", help="a role lens, e.g. 'finance lead'")
    ap.add_argument("--top", type=int, default=15)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true")
    g.add_argument("--prompt", action="store_true", help="the grounding block a model would get")
    a = ap.parse_args(argv)
    brain = pathlib.Path(a.brain).expanduser()
    if not (brain / "graph.json").is_file():
        print("retrieval: no graph.json in that brain (build it, or run analyze.py --graph-data)", file=sys.stderr)
        return 2
    notes, edges = load_brain(brain)
    pack = build_pack(a.query, notes, edges, role_seeds(a.role, notes))
    by_id = {n["id"]: n for n in notes}
    if a.json:
        print(json.dumps(pack, ensure_ascii=False, indent=1))
    elif a.prompt:
        print(pack_to_prompt(pack, by_id))
    else:
        if not pack["seeds"]:
            print("No note matches the words in that question — try a name, a company or a place.")
            return 0
        for nid, s in sorted(pack["activations"].items(), key=lambda kv: -kv[1])[:a.top]:
            n = by_id.get(nid, {})
            print(f"{s:.4f}  {n.get('title', nid)}  ({n.get('type', '')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
