#!/usr/bin/env python3
"""pipeline_doc.py - build, check and write an agent's pipeline file (schema sbl-pipeline/2).

SHIPPED BYTE-IDENTICAL in every plugin that has a pipeline (job-search, fundraising,
travel-planner, sales); the plugin build fails if the copies differ.

Every agent writes ONE file, `<its layer>/pipeline.json`, which Second Brain Studio's Pipeline
canvas draws (an isometric terrace of stages, one tile per item) beside every other agent's.
The canvas never writes it: a click or a drag there becomes a chat turn to the agent, which
changes its own ledger and re-renders this file.

    doc = new(agent, label, color)
    doc["stages"].append(stage("applied", "Applied", "open", next=["screen", "rejected"]))
    doc["items"].append(item("acme-cto", "CTO", "applied", sub="Acme · Lisbon", score=82))
    problems = check(doc)          # [] when valid
    write(path, doc)               # deterministic: same ledger -> byte-identical file

Rules the check enforces (the canvas relies on them):
  - stage roles are open | positive | negative | parked; gates none | confirm | reason | owner
  - every `next` names a stage of this pipeline; every item's stage exists; item ids unique
  - a quote (in any item detail) carries `quoted_at` - a price is a snapshot, never a fact
  - stats are num / den (the canvas shows a rate only when den >= min_n); no `rate` field
  - items in parked or negative stages carry no `detail` (keeps a big pipeline small)

    python3 pipeline_doc.py check FILE      exit 1 and list the problems
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

SCHEMA = "sbl-pipeline/2"
ROLES = ("open", "positive", "negative", "parked")
GATES = ("none", "confirm", "reason", "owner")
BLOCKS = ("kv", "text", "people", "steps", "evidence", "quotes", "links", "tags", "bars")


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


def _walk_quotes(o, where, out):
    if isinstance(o, dict):
        if "price" in o and not o.get("quoted_at"):
            out.append(f"{where}: a price without quoted_at")
        for k, v in o.items():
            _walk_quotes(v, f"{where}.{k}", out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk_quotes(v, f"{where}[{i}]", out)


def check(doc):
    p = []
    if doc.get("schema") != SCHEMA:
        p.append("schema must be " + SCHEMA)
    ids = [s.get("id") for s in doc.get("stages") or []]
    if len(set(ids)) != len(ids):
        p.append("duplicate stage ids")
    roles = {}
    for s in doc.get("stages") or []:
        roles[s.get("id")] = s.get("role")
        if s.get("role") not in ROLES:
            p.append(f"stage {s.get('id')}: role {s.get('role')!r}")
        if s.get("gate", "none") not in GATES:
            p.append(f"stage {s.get('id')}: gate {s.get('gate')!r}")
        for n in s.get("next") or []:
            if n not in ids:
                p.append(f"stage {s.get('id')}: next {n!r} is not a stage")
    seen = set()
    for it in doc.get("items") or []:
        if it.get("id") in seen:
            p.append(f"duplicate item id {it.get('id')!r}")
        seen.add(it.get("id"))
        if it.get("stage") not in roles:
            p.append(f"item {it.get('id')}: unknown stage {it.get('stage')!r}")
        elif roles[it["stage"]] in ("parked", "negative") and it.get("detail"):
            p.append(f"item {it.get('id')}: detail on a {roles[it['stage']]} item")
        _walk_quotes(it.get("detail"), f"item {it.get('id')}.detail", p)
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
    """Write only when the content changed (an unchanged ledger leaves the file byte-identical)."""
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


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
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
