#!/usr/bin/env python3
"""ontology.py — the brain's object types + labelled relations, counted from a graph.

The ontology is DATA (`mappings/brain/ontology.json`): which (type, category, kind)
frontmatter combination is which object ("Account", "Channel", "Deal"…), and the
direction + human label of each graph.json edge type ("deal for", "member of").
This module only matches and counts — deterministic, stdlib, no AI — so a built
brain can say what it is made of, from what it actually holds.

Used by graphdata.py (graph.json `ontology` block + node `object`), and readable by
analyze.py / diagrams.py. Stored edges are never rewritten: direction lives on the
relation type, so retrieval.py ↔ brain-retrieval.ts parity is untouched.
"""
from collections import Counter, defaultdict

_CACHE = {}


def load(extra_dirs=None):
    """The ontology spec (cached per override set). {} when none is readable."""
    key = tuple(str(d) for d in (extra_dirs or []))
    if key not in _CACHE:
        try:
            import mapping
            _CACHE[key] = mapping.load_brain_ontology(extra_dirs) or {}
        except Exception:
            _CACHE[key] = {}
    return _CACHE[key]


def _subject_ok(entry, subject):
    want = entry.get("subject")
    if not want:
        return True
    is_company = subject == "company"
    return (want == "company") == is_company


def object_of(node, subject, spec=None):
    """The object id for a node/frontmatter dict carrying type/category/kind, or
    None for meta notes (MOCs, reports, guides…). Unknown types fall back to the
    raw type so nothing is silently dropped."""
    spec = spec if spec is not None else load()
    t = str(node.get("type") or "")
    if not t or t in set(spec.get("meta_types", [])):
        return None
    if node.get("layer") in set(spec.get("meta_layers", [])):
        return None             # plugin/harness layers are work products, not objects
    cat = str(node.get("category") or "")
    kind = str(node.get("kind") or "")
    for o in spec.get("objects", []):
        if not _subject_ok(o, subject):
            continue
        for m in [o.get("match", {})] + list(o.get("also", [])):
            if m.get("type") != t:
                continue
            if "category" in m and m["category"] != cat:
                continue
            if "kind" in m and m["kind"] != kind:
                continue
            return o["id"]
    return t


def _object_meta(spec, oid, subject):
    for o in spec.get("objects", []):
        if o["id"] == oid:
            personal = subject != "company"
            return {"label": (o.get("label_person") if personal and o.get("label_person")
                              else o.get("label", oid)),
                    "meaning": (o.get("meaning_person") if personal and o.get("meaning_person")
                                else o.get("meaning", "")),
                    "color_var": o.get("color_var", ""), "icon": o.get("icon", ""),
                    "type": (o.get("match") or {}).get("type", oid)}
    label = oid.replace("-", " ").replace("_", " ").strip().capitalize()
    return {"label": label, "meaning": "", "color_var": "", "icon": ""}


def _relation_def(spec, etype):
    for r in spec.get("relations", []):
        if r.get("edge_type") == etype:
            return r
    return {"edge_type": etype, "from": [], "to": [],
            "label": etype.replace("_", " "), "inverse": etype.replace("_", " ")}


def orient(spec, etype, oa, ob):
    """(from_obj, to_obj, flipped) for an undirected edge between objects oa, ob."""
    r = _relation_def(spec, etype)
    frm, to = r.get("from") or [], r.get("to") or []
    if oa in frm and (not to or ob in to):
        return oa, ob, False
    if ob in frm and (not to or oa in to):
        return ob, oa, True
    return oa, ob, False


def build(nodes, edges, subject, spec=None):
    """The graph.json `ontology` block from already-built nodes/edges.

    nodes: list of graph.json node dicts (need id, type, optional category/kind/sources)
    edges: list of {a, b, type} dicts
    """
    spec = spec if spec is not None else load()
    if not spec:
        return {}
    obj = {}
    for n in nodes:
        o = object_of(n, subject, spec)
        if o:
            obj[n["id"]] = o

    count, merged, samples = Counter(), Counter(), defaultdict(list)
    srcs = defaultdict(Counter)
    for n in sorted(nodes, key=lambda n: (-int(n.get("deg") or 0), n["id"])):
        o = obj.get(n["id"])
        if not o:
            continue
        count[o] += 1
        ss = [s for s in (n.get("sources") or []) if s and s != "[]"]
        if len(ss) > 1:
            merged[o] += 1
        for s in ss:
            srcs[o][s] += 1
        if len(samples[o]) < 3:
            samples[o].append(n["id"])

    order = [o["id"] for o in spec.get("objects", [])]
    objects = []
    for oid in sorted(count, key=lambda k: (order.index(k) if k in order else len(order), k)):
        meta = _object_meta(spec, oid, subject)
        objects.append({"id": oid, "label": meta["label"], "meaning": meta["meaning"],
                        "type": meta.get("type") or oid,
                        "color_var": meta["color_var"], "icon": meta["icon"],
                        "count": count[oid], "merged": merged[oid],
                        "sources": dict(sorted(srcs[oid].items(), key=lambda kv: (-kv[1], kv[0]))),
                        "sample_ids": samples[oid]})

    by_id = {n["id"]: n for n in nodes}
    rel_count, rel_cross = Counter(), Counter()
    for e in edges:
        oa, ob = obj.get(e["a"]), obj.get(e["b"])
        if not oa or not ob:
            continue
        f, t, _ = orient(spec, e["type"], oa, ob)
        k = (e["type"], f, t)
        rel_count[k] += 1
        sa = set(by_id[e["a"]].get("sources") or []) - {"[]"}
        sb = set(by_id[e["b"]].get("sources") or []) - {"[]"}
        if sa and sb and not (sa & sb):
            rel_cross[k] += 1
    relations = []
    for (etype, f, t), c in sorted(rel_count.items(), key=lambda kv: (-kv[1], kv[0])):
        r = _relation_def(spec, etype)
        relations.append({"edge_type": etype, "from": f, "to": t,
                          "label": (r.get("label_by_to") or {}).get(t, r.get("label", etype)), "inverse": r.get("inverse", ""),
                          "count": c, "cross_source": rel_cross[(etype, f, t)]})

    present = set(count)
    questions = [{k: q[k] for k in ("t", "short", "q") if k in q}
                 for q in spec.get("questions", [])
                 if _subject_ok(q, subject) and set(q.get("requires", [])) <= present]
    metrics = []
    for m in spec.get("metrics", []):
        if m.get("merged"):
            v = sum(merged.values())
        elif m.get("count_of") in present:
            v = count[m["count_of"]]
        else:
            continue
        metrics.append({"id": m["id"], "label": m.get("label", m["id"]), "value": v})

    return {"version": spec.get("version", 1), "objects": objects, "relations": relations,
            "questions": questions, "metrics": metrics,
            "merged_nodes": sum(merged.values())}


def suggest(source_names, subject=None, spec=None):
    """The PRE-BUILD ontology ("Before you build"): which objects the detected sources will
    produce, which sources each object would be merged from, and the relations
    possible between them. Deterministic, from mappings only (no data read)."""
    spec = spec if spec is not None else load()
    so = spec.get("source_objects", {})
    if subject is None:
        try:
            import sources as _src
            comp = any(getattr(_src.BY_NAME.get(s), "SUBJECT", "person") == "company"
                       for s in source_names)
        except Exception:
            comp = False
        subject = "company" if comp else "person"
    by = {}
    for s in source_names:
        for oid in so.get(s, []):
            by.setdefault(oid, []).append(s)
    objects = []
    order = [o["id"] for o in spec.get("objects", [])]
    for oid in sorted(by, key=lambda k: order.index(k) if k in order else len(order)):
        meta = _object_meta(spec, oid, subject)
        objects.append({"id": oid, "label": meta["label"], "meaning": meta["meaning"],
                        "sources": sorted(set(by[oid])),
                        "merge_candidate": len(set(by[oid])) > 1})
    present = set(by)
    relations = []
    for r in spec.get("relations", []):
        if r.get("edge_type") == "linked":
            continue
        for f in r.get("from", []):
            for t in r.get("to", []):
                if f in present and t in present and f != t:
                    relations.append({"edge_type": r["edge_type"], "from": f, "to": t,
                                      "label": (r.get("label_by_to") or {}).get(t, r.get("label"))})
    return {"subject": subject, "objects": objects, "relations": relations}


def questions_for(object_ids, subject, spec=None, limit=None):
    """The spec's starter questions whose required objects are all present."""
    spec = spec if spec is not None else load()
    present = set(object_ids)
    out = [q for q in spec.get("questions", [])
           if _subject_ok(q, subject) and set(q.get("requires", [])) <= present]
    return out[:limit] if limit else out
