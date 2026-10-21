#!/usr/bin/env python3
"""stages.py - the user's stage labels and hidden stages: profile/stages.json (sbl-stages/1).

SHIPPED BYTE-IDENTICAL in the engine and every plugin (build_plugin.SHARED_FILES). Stdlib only.

The plugin fixes the stage IDs, roles and gates in its contract (`studio.json` `funnels`); the
user only ever renames a stage or hides an optional one. That lives in ONE file, written by
onboarding with the defaults and editable in the agent's settings:

    {"schema": "sbl-stages/1",
     "funnels": {"accounts": {"trial": {"label": "Pilot"}, "nurture": {"hidden": true}}}}

Every renderer applies it at render time (`pipeline_doc.apply_profile`): a renamed stage keeps
its ID, a hidden stage is emitted `collapsed: true`, leaves the Floor, and its items still
count. Studio reads only `pipeline.json`; it never sees this file.

    stages.py init  --contract studio.json --profile DIR      write the defaults (never overwrites)
    stages.py show  --profile DIR                             the current file, validated
    stages.py set   --profile DIR --funnel F --stage S [--label L] [--hide | --unhide]
    stages.py check --contract studio.json --profile DIR      IDs the contract does not know
    python3 stages.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline_doc as pdoc  # noqa: E402

SCHEMA = pdoc.STAGES_SCHEMA
FILE = "stages.json"


def defaults(contract):
    """The contract's own labels, one entry per stage - the file onboarding seeds."""
    out = {"schema": SCHEMA, "funnels": {}}
    for f in contract.get("funnels") or []:
        fid = f.get("id") or ""
        out["funnels"][fid] = {s["id"]: {"label": s.get("label") or s["id"].replace("_", " ").title()}
                               for s in f.get("stages") or [] if s.get("id")}
    return out


def load(profile_dir):
    p = pathlib.Path(profile_dir) / FILE
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) and d.get("schema") == SCHEMA else {}


def validate(d, contract=None):
    p = []
    if d.get("schema") != SCHEMA:
        p.append("schema must be " + SCHEMA)
    fs = d.get("funnels")
    if not isinstance(fs, dict):
        p.append("funnels must be an object")
        return p
    known = {f.get("id"): {s.get("id"): s for s in f.get("stages") or []} for f in (contract or {}).get("funnels") or []}
    for fid, rules in fs.items():
        if not isinstance(rules, dict):
            p.append(f"funnel {fid}: rules must be an object")
            continue
        if contract and fid not in known:
            p.append(f"funnel {fid}: not in the contract")
        for sid, r in rules.items():
            if not isinstance(r, dict):
                p.append(f"{fid}.{sid}: must be an object")
                continue
            if contract and fid in known and sid not in known[fid]:
                p.append(f"{fid}.{sid}: not a stage of that funnel")
            if "label" in r and (not isinstance(r["label"], str) or not r["label"].strip() or len(r["label"]) > 40):
                p.append(f"{fid}.{sid}: label must be 1-40 characters")
            if "hidden" in r and not isinstance(r["hidden"], bool):
                p.append(f"{fid}.{sid}: hidden must be true/false")
            if contract and fid in known and sid in known[fid] and r.get("hidden") is True:
                s = known[fid][sid]
                f = next(x for x in contract["funnels"] if x.get("id") == fid)
                if sid == f.get("success") or s.get("role") == "positive":
                    p.append(f"{fid}.{sid}: a success / positive stage cannot be hidden")
    return p


def save(profile_dir, d):
    p = pathlib.Path(profile_dir) / FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p


def init(profile_dir, contract, force=False):
    """Seed the defaults; an existing file is never overwritten (the user owns it)."""
    p = pathlib.Path(profile_dir) / FILE
    if p.is_file() and not force:
        return p, "kept"
    save(profile_dir, defaults(contract))
    return p, "created"


def apply(doc, profile_dir):
    """Apply profile/stages.json to a pipeline doc (no file = the contract's labels)."""
    return pdoc.apply_profile(doc, load(profile_dir))


def set_rule(profile_dir, funnel, stage, label=None, hidden=None, contract=None):
    d = load(profile_dir) or ({"schema": SCHEMA, "funnels": {}} if not contract else defaults(contract))
    r = d.setdefault("funnels", {}).setdefault(funnel, {}).setdefault(stage, {})
    if label is not None:
        r["label"] = label.strip()[:40]
    if hidden is not None:
        if hidden:
            r["hidden"] = True
        else:
            r.pop("hidden", None)
    probs = validate(d, contract)
    if probs:
        raise ValueError("; ".join(probs))
    save(profile_dir, d)
    return d


def _selftest():
    import tempfile  # noqa: PLC0415
    contract = {"funnels": [{"id": "a", "label": "A", "item": "x", "success": "won",
                             "stages": [{"id": "x", "label": "X", "role": "open"}, {"id": "won", "label": "Won", "role": "positive"}]}]}
    d = defaults(contract)
    assert d["funnels"]["a"]["x"]["label"] == "X" and validate(d, contract) == []
    with tempfile.TemporaryDirectory() as t:
        p, r = init(t, contract)
        assert r == "created" and init(t, contract)[1] == "kept"
        set_rule(t, "a", "x", label="Ex", hidden=True, contract=contract)
        assert load(t)["funnels"]["a"]["x"] == {"label": "Ex", "hidden": True}
        try:
            set_rule(t, "a", "won", hidden=True, contract=contract)
            raise AssertionError("hid the success stage")
        except ValueError:
            pass
        doc = pdoc.new("t", "T", "#000")
        doc["funnels"] = [pdoc.funnel("a", "A", "x", "won", [pdoc.stage("x", "X"), pdoc.stage("won", "Won", "positive")])]
        doc["items"] = [pdoc.item("1", "one", "x", funnel="a")]
        doc["floor"] = [pdoc.floor_group("g", "X", ["x"], funnel="a")]
        apply(doc, t)
        assert pdoc.stage_of(doc, "a", "x")["label"] == "Ex" and doc["floor"] == [] and pdoc.check(doc) == []
    assert validate({"schema": SCHEMA, "funnels": {"zz": {}}}, contract) == ["funnel zz: not in the contract"]
    print("stages: selftest ok")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selftest"]:
        return _selftest()
    ap = argparse.ArgumentParser(prog="stages.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "show", "set", "check"):
        g = sub.add_parser(name)
        g.add_argument("--profile", required=True)
        if name in ("init", "check", "set"):
            g.add_argument("--contract", required=(name != "set"))
        if name == "set":
            g.add_argument("--funnel", required=True)
            g.add_argument("--stage", required=True)
            g.add_argument("--label")
            g.add_argument("--hide", action="store_true")
            g.add_argument("--unhide", action="store_true")
        if name == "init":
            g.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    contract = {}
    if getattr(a, "contract", None):
        contract = json.loads(pathlib.Path(a.contract).read_text(encoding="utf-8"))
    if a.cmd == "init":
        p, r = init(a.profile, contract, a.force)
        print(f"{r}: {p}")
    elif a.cmd == "show":
        print(json.dumps(load(a.profile), indent=1, ensure_ascii=False))
    elif a.cmd == "set":
        hidden = True if a.hide else (False if a.unhide else None)
        try:
            set_rule(a.profile, a.funnel, a.stage, a.label, hidden, contract or None)
        except ValueError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 1
        print("ok")
    elif a.cmd == "check":
        probs = validate(load(a.profile) or defaults(contract), contract)
        for x in probs:
            print("  ! " + x)
        print("ok" if not probs else f"{len(probs)} problem(s)")
        return 0 if not probs else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
