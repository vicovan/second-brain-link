#!/usr/bin/env python3
"""pipeline_doc.py - build, check and write an agent's pipeline file (schema sbl-pipeline/2).

SHIPPED BYTE-IDENTICAL in the engine (`engine/scripts/`, the canonical copy) and in every
plugin that has a pipeline (job-search, fundraising, travel-planner, sales); the plugin build
fails if the copies differ.

Every agent writes ONE file, `<its layer>/pipeline.json`, which Second Brain Studio's Runtime
draws (the Floor's machines, the Lines' terraces, one tile per item) beside every other agent's.
The canvas never writes it: a click or a drag there becomes a chat turn to the agent, which
changes its own ledger and re-renders this file.

    doc = new(agent, label, color)
    doc["funnels"] = [funnel("postings", "Postings", "posting", "interview", [
        stage("shortlist", "Shortlist", "open", next=["prepared"]), ...])]
    doc["floor"] = [floor_group("screen", "Screen", ["shortlist", "prepared"], funnel="postings"), ...]
    doc["items"].append(item("acme-cto", "CTO", "applied", funnel="postings", score=82))
    apply_profile(doc, stages_json)     # the user's labels / hidden stages (profile/stages.json)
    problems = check(doc)               # [] when valid
    write(path, doc)                    # deterministic: same ledger -> byte-identical file

Two optional, additive blocks (absent = the single-stage-list file of before):

  funnels  one terrace per item kind: {id, label, item, success, success2?, stages[]}. When
           present, the top-level `stages` list is EMPTY and every item carries `funnel`.
           Stage IDs are namespaced by funnel (two funnels may both have `screened`).
  floor    <= 8 machine groups {id, label, stages[], funnel?}: with `funnel` the IDs match in
           that funnel only; without it they match in every funnel that has them (a shared
           machine). Each (funnel, stage) sits in at most one group. Only open / positive
           stages may be on the floor. Without `floor` the fallback is the first eight
           open/positive stages (third-party agents only).

Rules the check enforces (the canvas relies on them):
  - stage roles are open | positive | negative | parked; gates none | confirm | reason | owner
  - every `next` names a stage of the same funnel; every item's (funnel, stage) exists; item ids unique
  - a quote (in any item detail) carries `quoted_at` - a price is a snapshot, never a fact
  - stats are num / den (the canvas shows a rate only when den >= min_n); no `rate` field
  - items in parked or negative stages carry no `detail` (keeps a big pipeline small)

    python3 pipeline_doc.py check FILE      exit 1 and list the problems
    python3 pipeline_doc.py --selftest
"""
from __future__ import annotations

import copy
import json
import os
import pathlib
import sys

SCHEMA = "sbl-pipeline/2"
STAGES_SCHEMA = "sbl-stages/1"
ROLES = ("open", "positive", "negative", "parked")
GATES = ("none", "confirm", "reason", "owner")
BLOCKS = ("kv", "text", "people", "steps", "evidence", "quotes", "links", "tags", "bars")
MAX_FLOOR = 8


def new(agent, label, color):
    return {"schema": SCHEMA, "agent": agent, "label": label, "color": color, "generated": "",
            "headline": None, "stats": [], "notices": [], "stages": [], "lenses": [], "facets": [],
            "items": [], "panel": {"top": [], "sections": [], "actions": []}, "actions": []}


def stage(sid, label, role="open", next=None, gate="none", move_prompt="Move {title} to {stage_label}.",
          actions=None, collapsed=False):
    s = {"id": sid, "label": label, "role": role, "next": list(next or []), "gate": gate, "move_prompt": move_prompt}
    if actions:
        s["actions"] = actions
    if collapsed:
        s["collapsed"] = True
    return s


def funnel(fid, label, item, success, stages, success2=None):
    """One terrace: the stages of one item kind, with the stage that counts as success."""
    f = {"id": fid, "label": label, "item": item, "success": success, "stages": list(stages)}
    if success2:
        f["success2"] = success2
    return f


def floor_group(gid, label, stages, funnel=None):
    """One machine on the Floor: the stage IDs it stands for (open / positive only)."""
    g = {"id": gid, "label": label, "stages": list(stages)}
    if funnel:
        g["funnel"] = funnel
    return g


def action(label, prompt, kind="secondary", stages=None, bulk=False, flag=None):
    a = {"label": label, "prompt": prompt, "kind": kind}
    if bulk:
        a["bulk"] = True
    when = {}
    if stages:
        when["stage"] = list(stages)
    if flag:
        when["flag"] = flag
    if when:
        a["when"] = when
    return a


def item(iid, title, stage_id, **kw):
    it = {"id": str(iid), "title": str(title or iid), "stage": stage_id}
    for k, v in kw.items():
        if v not in (None, "", [], {}):
            it[k] = v
    return it


def lens(lid, label, attr, scale="linear", domain=None, buckets=None, value=None):
    L = {"id": lid, "label": label, "attr": attr, "scale": scale}
    if domain is not None:
        L["domain"] = list(domain)
    if buckets is not None:
        L["buckets"] = list(buckets)
    if value is not None:
        L["value"] = value
    return L


def facet(fid, label, attr, values=None):
    f = {"id": fid, "label": label, "attr": attr}
    if values:
        f["values"] = values
    return f


# ------------------------------------------------------------------ reading a doc
def funnels_of(doc):
    """The funnels as a list; a doc without the block is ONE anonymous funnel over `stages`."""
    fs = doc.get("funnels") or []
    if fs:
        return fs
    return [{"id": "", "label": doc.get("label") or "", "item": "item", "success": "",
             "stages": doc.get("stages") or []}]


def funnel_of(doc, fid):
    for f in funnels_of(doc):
        if f.get("id") == (fid or ""):
            return f
    return None


def stage_of(doc, fid, sid):
    f = funnel_of(doc, fid)
    for s in (f or {}).get("stages") or []:
        if s.get("id") == sid:
            return s
    return None


def open_chain(f, include_collapsed=False):
    """The open stages of a funnel in declared order (the path the counts follow). A collapsed
    stage (off-path, or hidden by the user's profile) is left out of the path unless asked for;
    its items still count."""
    return [s["id"] for s in f.get("stages") or [] if s.get("role") == "open" and (include_collapsed or not s.get("collapsed"))]


def counts(doc):
    """{funnel id: {stage id: n}} over the items - hidden stages included (never lost)."""
    out = {f.get("id") or "": {s["id"]: 0 for s in f.get("stages") or []} for f in funnels_of(doc)}
    for it in doc.get("items") or []:
        fid = it.get("funnel") or ""
        if fid in out and it.get("stage") in out[fid]:
            out[fid][it["stage"]] += 1
    return out


def default_floor(doc):
    """Without a `floor` block: the first eight open/positive stages, across the funnels."""
    groups = []
    for f in funnels_of(doc):
        for s in f.get("stages") or []:
            if s.get("role") in ("open", "positive") and not s.get("collapsed") and len(groups) < MAX_FLOOR:
                groups.append(floor_group(s["id"] if not f.get("id") else f"{f['id']}-{s['id']}", s["label"], [s["id"]],
                                          funnel=f.get("id") or None))
    return groups


# ------------------------------------------------------------------ the user's profile
def apply_profile(doc, stages_json):
    """Apply profile/stages.json (sbl-stages/1) at render time: a renamed stage keeps its ID; a
    hidden stage is emitted `collapsed: true`, dropped from the floor, and its items still count.
    Returns the doc (mutated). Studio reads only the result; it never sees the profile."""
    if not isinstance(stages_json, dict):
        return doc
    per_funnel = stages_json.get("funnels") if isinstance(stages_json.get("funnels"), dict) else {}
    flat = stages_json.get("stages") if isinstance(stages_json.get("stages"), dict) else {}
    hidden = set()
    for f in funnels_of(doc):
        fid = f.get("id") or ""
        rules = dict(flat)
        rules.update(per_funnel.get(fid) or {}) if fid else None
        if not fid:
            rules.update(per_funnel.get("") or {})
        for s in f.get("stages") or []:
            r = rules.get(s.get("id"))
            if not isinstance(r, dict):
                continue
            lab = r.get("label")
            if isinstance(lab, str) and lab.strip():
                s["label"] = lab.strip()[:40]
            if r.get("hidden") is True:
                s["collapsed"] = True
                hidden.add((fid, s["id"]))
    if hidden and doc.get("floor"):
        kept = []
        for g in doc["floor"]:
            gf = g.get("funnel")
            keep = []
            for sid in g.get("stages") or []:
                if gf:
                    if (gf, sid) not in hidden:
                        keep.append(sid)
                else:
                    if any((f.get("id") or "", sid) not in hidden and stage_of(doc, f.get("id") or "", sid)
                           for f in funnels_of(doc)):
                        keep.append(sid)
            if keep:
                g["stages"] = keep
                kept.append(g)
        doc["floor"] = kept
    return doc


def throughput(label, dates, today=None, days=12):
    """The lane monitor block (additive, optional): {label, value, series} - `dates` are the ISO
    days of each counted act (an application sent, a draft filed, a touch, a place tried); `series`
    is one integer per day for the last `days` days, oldest first; `value` is today's."""
    import datetime as _dt  # noqa: PLC0415
    today = _dt.date.fromisoformat(today) if isinstance(today, str) else (today or _dt.date.today())
    counts = {}
    for d in dates:
        k = str(d or "")[:10]
        if k:
            counts[k] = counts.get(k, 0) + 1
    series = [counts.get((today - _dt.timedelta(days=i)).isoformat(), 0) for i in range(days - 1, -1, -1)]
    return {"label": label, "value": series[-1] if series else 0, "series": series}


def _walk_quotes(o, where, out):
    if isinstance(o, dict):
        if "price" in o and not o.get("quoted_at"):
            out.append(f"{where}: a price without quoted_at")
        for k, v in o.items():
            _walk_quotes(v, f"{where}.{k}", out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk_quotes(v, f"{where}[{i}]", out)


def _check_stages(stages, where, p):
    ids = [s.get("id") for s in stages]
    if len(set(ids)) != len(ids):
        p.append(f"{where}: duplicate stage ids")
    roles = {}
    for s in stages:
        roles[s.get("id")] = s.get("role")
        if s.get("role") not in ROLES:
            p.append(f"{where} stage {s.get('id')}: role {s.get('role')!r}")
        if s.get("gate", "none") not in GATES:
            p.append(f"{where} stage {s.get('id')}: gate {s.get('gate')!r}")
        for n in s.get("next") or []:
            if n not in ids:
                p.append(f"{where} stage {s.get('id')}: next {n!r} is not a stage")
    return roles


def check(doc):
    p = []
    if doc.get("schema") != SCHEMA:
        p.append("schema must be " + SCHEMA)
    funnels = doc.get("funnels") or []
    roles_by_funnel = {}
    if funnels:
        if doc.get("stages"):
            p.append("with funnels, the top-level stages list must be empty")
        fids = [f.get("id") for f in funnels]
        if len(set(fids)) != len(fids) or any(not f for f in fids):
            p.append("funnel ids must be unique and non-empty")
        for f in funnels:
            fid = f.get("id") or "?"
            roles = _check_stages(f.get("stages") or [], f"funnel {fid}", p)
            roles_by_funnel[fid] = roles
            if not f.get("item"):
                p.append(f"funnel {fid}: item kind missing")
            if f.get("success") not in roles:
                p.append(f"funnel {fid}: success stage {f.get('success')!r} is not one of its stages")
            if f.get("success2") and f.get("success2") not in roles:
                p.append(f"funnel {fid}: success2 stage {f.get('success2')!r} is not one of its stages")
    else:
        roles_by_funnel[""] = _check_stages(doc.get("stages") or [], "stages", p)
    seen = set()
    for it in doc.get("items") or []:
        if it.get("id") in seen:
            p.append(f"duplicate item id {it.get('id')!r}")
        seen.add(it.get("id"))
        fid = it.get("funnel") or ""
        if funnels and not fid:
            p.append(f"item {it.get('id')}: no funnel")
            continue
        roles = roles_by_funnel.get(fid)
        if roles is None:
            p.append(f"item {it.get('id')}: unknown funnel {fid!r}")
        elif it.get("stage") not in roles:
            p.append(f"item {it.get('id')}: unknown stage {it.get('stage')!r}" + (f" in funnel {fid}" if fid else ""))
        elif roles[it["stage"]] in ("parked", "negative") and it.get("detail"):
            p.append(f"item {it.get('id')}: detail on a {roles[it['stage']]} item")
        _walk_quotes(it.get("detail"), f"item {it.get('id')}.detail", p)
    floor = doc.get("floor")
    if floor is not None:
        if not isinstance(floor, list):
            p.append("floor must be a list of groups")
        else:
            if len(floor) > MAX_FLOOR:
                p.append(f"floor has {len(floor)} groups (max {MAX_FLOOR})")
            gids = [g.get("id") for g in floor]
            if len(set(gids)) != len(gids):
                p.append("duplicate floor group ids")
            taken = {}
            for g in floor:
                gid = g.get("id") or "?"
                if not g.get("stages"):
                    p.append(f"floor group {gid}: no stages")
                gf = g.get("funnel")
                if gf is not None and gf not in roles_by_funnel:
                    p.append(f"floor group {gid}: unknown funnel {gf!r}")
                    continue
                for sid in g.get("stages") or []:
                    targets = [gf] if gf is not None else [f for f, r in roles_by_funnel.items() if sid in r]
                    if not targets:
                        p.append(f"floor group {gid}: stage {sid!r} is in no funnel")
                    for f in targets:
                        role = roles_by_funnel.get(f, {}).get(sid)
                        if role is None:
                            p.append(f"floor group {gid}: stage {sid!r} is not in funnel {f!r}")
                        elif role not in ("open", "positive"):
                            p.append(f"floor group {gid}: stage {sid!r} is {role}, not open/positive")
                        if (f, sid) in taken:
                            p.append(f"floor: stage {sid!r} of funnel {f!r} is in groups {taken[(f, sid)]} and {gid}")
                        taken[(f, sid)] = gid
    for st in doc.get("stats") or []:
        if "rate" in st or "num" not in st or "den" not in st:
            p.append(f"stat {st.get('label')!r}: give num and den, never a rate")
    for sec in (doc.get("panel") or {}).get("sections") or []:
        if sec.get("type") not in BLOCKS:
            p.append(f"panel section type {sec.get('type')!r}")
    return p


def dumps(doc):
    """Compact and sorted: a pipeline can hold thousands of items, and a byte-identical re-render
    needs a canonical form."""
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def write(path, doc):
    """Atomic (tmp + rename) and only when the content changed (an unchanged ledger leaves the
    file byte-identical)."""
    path = pathlib.Path(path)
    txt = dumps(doc)
    try:
        if path.read_text(encoding="utf-8") == txt:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(txt, encoding="utf-8")
    os.replace(tmp, path)
    return True


# ------------------------------------------------------------------ selftest
def _selftest():
    S = stage
    d = new("t", "T", "#000")
    d["funnels"] = [funnel("a", "A", "thing", "won", [S("x", "X", next=["y"]), S("y", "Y", next=["won"]),
                                                   S("won", "Won", "positive"), S("lost", "Lost", "negative")]),
                    funnel("b", "B", "other", "done", [S("x", "X", next=["done"]), S("done", "Done", "positive")])]
    d["items"] = [item("1", "one", "x", funnel="a"), item("2", "two", "x", funnel="b"), item("3", "three", "won", funnel="a")]
    d["floor"] = [floor_group("g1", "Start", ["x"]), floor_group("g2", "Y", ["y"], funnel="a"),
                  floor_group("g3", "Done", ["won", "done"])]
    assert check(d) == [], check(d)
    assert counts(d) == {"a": {"x": 1, "y": 0, "won": 1, "lost": 0}, "b": {"x": 1, "done": 0}}
    bad = copy.deepcopy(d)
    bad["floor"].append(floor_group("g4", "Again", ["x"], funnel="a"))
    assert any("is in groups" in x for x in check(bad)), check(bad)
    bad = copy.deepcopy(d)
    bad["floor"] = [floor_group(f"g{i}", "G", ["x"]) for i in range(9)]
    assert any("max 8" in x for x in check(bad))
    bad = copy.deepcopy(d)
    bad["items"].append(item("4", "four", "nope", funnel="a"))
    assert any("unknown stage" in x for x in check(bad))
    bad = copy.deepcopy(d)
    bad["items"].append(item("5", "five", "x", funnel="zzz"))
    assert any("unknown funnel" in x for x in check(bad))
    bad = copy.deepcopy(d)
    bad["floor"] = [floor_group("g", "Lost", ["lost"], funnel="a")]
    assert any("not open/positive" in x for x in check(bad))
    bad = copy.deepcopy(d)
    bad["stages"] = [S("z", "Z")]
    assert any("must be empty" in x for x in check(bad))
    # a doc without the new blocks passes as before
    old = new("t", "T", "#000")
    old["stages"] = [S("x", "X", next=["y"]), S("y", "Y", "positive")]
    old["items"] = [item("1", "one", "x")]
    assert check(old) == []
    assert len(default_floor(old)) == 2
    # the profile: renamed keeps its id, hidden collapses and leaves the floor, items still count
    prof = {"schema": STAGES_SCHEMA, "funnels": {"a": {"y": {"label": "Why"}, "x": {"hidden": True}}}}
    pd = apply_profile(copy.deepcopy(d), prof)
    assert stage_of(pd, "a", "y")["label"] == "Why" and stage_of(pd, "a", "x").get("collapsed") is True
    assert check(pd) == [] and counts(pd)["a"]["x"] == 1
    g1 = next(g for g in pd["floor"] if g["id"] == "g1")
    assert g1["stages"] == ["x"]          # shared machine keeps x for funnel b
    assert dumps(pd) == dumps(json.loads(dumps(pd)))
    tp = throughput("x / day", ["2026-01-15", "2026-01-15", "2026-01-15T09:00:00", "nope"], today="2026-01-15", days=3)
    assert tp == {"label": "x / day", "value": 3, "series": [0, 0, 3]}, tp
    print("pipeline_doc: selftest ok")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selftest"]:
        return _selftest()
    if len(argv) != 2 or argv[0] != "check":
        print(__doc__.split("\n\n")[0])
        return 2
    try:
        doc = json.loads(pathlib.Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"cannot read {argv[1]}: {e}")
        return 1
    probs = check(doc)
    for x in probs:
        print("  ! " + x)
    print("ok" if not probs else f"{len(probs)} problem(s)")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
