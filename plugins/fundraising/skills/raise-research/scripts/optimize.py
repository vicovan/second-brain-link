#!/usr/bin/env python3
"""optimize.py - the weekly self-improvement step: what converted, where the funnel leaks, proposals.

SHIPPED BYTE-IDENTICAL in the engine and every plugin (build_plugin.SHARED_FILES). Stdlib only,
deterministic: the same pipeline, events and sources file give the same proposals, in the same
order, twice.

Inputs are what every agent already has: `pipeline.json` (items with `attrs`), `events.jsonl`,
`profile/sources.md` (explore.py) and the contract's `optimize` block:

    "optimize": {"sources": "profile/sources.md", "scoring": "profile/scoring.md",
                 "signals": ["origin", "segment", "channel"], "explore": 0.2}

Proposals (each with its evidence rows and n):
    leak        the worst conversion step with n >= 20 (informational - tells the skill where to look)
    reweight    a signal value whose success rate (n >= 20) is clearly above / below the funnel's
                -> `weight.<signal>.<value>: up|down` in the scoring file's optimizer block
    source      a candidate that converted (promote) or never found anything (drop), n >= 5 tries
                -> moved in sources.md by explore.py
    idea        a query / angle / idea kind suggestion the SKILL may act on (text only)

Safety (tested): the optimizer may edit ONLY the two files the contract names, inside its own
marker block, and it REFUSES any key that looks like a cap or a gate: `cap.*`, `max_*`, `level`,
`only_when`, `social_auto`, `eu_gate`, `quiet_*`, `days`, `floor`, `daily_target`, `min_*`.
A proposal never raises a cap; "behind pace" widens discovery, never the gates.

    optimize.py propose --pipeline P --events E --signals a,b [--sources F] [--today D] [--json]
    optimize.py apply   --pipeline P --events E --signals a,b --profile DIR --contract studio.json
                        [--level supervised|autonomous] [--today D] [--review-out FILE] [--label L]
    python3 optimize.py --selftest
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explore  # noqa: E402
import kpi  # noqa: E402
from ledger_base import replace_between  # noqa: E402

MIN_RATE_N = 20
MIN_SOURCE_N = 5
LIFT = 1.5           # a group is "clearly above" at 1.5x the funnel's rate, "below" at 1/1.5
SAFETY = re.compile(r"^(cap\.|max_|min_|level$|only_when|social_auto|eu_gate|quiet_|days$|floor$|daily_target|autonomous_gated|send|mail_|smtp|imap|timezone)", re.I)
MARK = "optimizer"


def propose(doc, events, signals, sources=None, today=None, min_rate_n=MIN_RATE_N, min_source_n=MIN_SOURCE_N):
    k = kpi.compute(doc, events, today=today, signals=list(signals or []), min_n=min_rate_n)
    props = []
    for f in k["funnels"]:
        worst = None
        for c in f["conversions"]:
            if c["rate"] is not None and (worst is None or c["rate"] < worst["rate"]):
                worst = c
        if worst:
            props.append({"kind": "leak", "funnel": f["id"], "key": f"{worst['from']}->{worst['to']}", "n": worst["den"],
                          "rate": worst["rate"], "text": f"{f['label']}: the funnel leaks most at {worst['from']} → {worst['to']} "
                          f"({worst['num']} of {worst['den']}, {round(100 * worst['rate'])} %)", "evidence": [worst]})
        base = f["success_rate"]["rate"]
        for s, vals in (f.get("by_signal") or {}).items():
            for v, g in vals.items():
                if g["rate"] is None or base is None:
                    continue
                if base == 0:
                    change = "up" if g["rate"] > 0 else None
                elif g["rate"] >= base * LIFT:
                    change = "up"
                elif g["rate"] <= base / LIFT:
                    change = "down"
                else:
                    change = None
                if change:
                    props.append({"kind": "reweight", "funnel": f["id"], "key": f"weight.{s}.{v}", "change": change, "n": g["n"],
                                  "rate": g["rate"], "base": base, "file": "scoring",
                                  "text": f"{s} = {v}: {g['success']} of {g['n']} reached {f['success_label']} "
                                          f"({round(100 * g['rate'])} % vs {round(100 * base)} % overall) → weight {change}",
                                  "evidence": [{"signal": s, "value": v, **g}]})
    if sources:
        for r in sources.get("candidates") or []:
            if r.get("status") != "active":
                continue
            if int(r.get("converted") or 0) > 0:
                props.append({"kind": "source", "key": r["source"], "change": "promote", "n": int(r.get("tries") or 0), "file": "sources",
                              "text": f"source {r['source']}: converted {r['converted']} — promote to Proven", "evidence": [r]})
            elif int(r.get("tries") or 0) >= min_source_n and int(r.get("found") or 0) == 0:
                props.append({"kind": "source", "key": r["source"], "change": "drop", "n": int(r.get("tries") or 0), "file": "sources",
                              "text": f"source {r['source']}: nothing found in {r['tries']} tries — drop", "evidence": [r]})
        for r in sources.get("proven") or []:
            if int(r.get("tries") or 0) >= 3 * min_source_n and int(r.get("found") or 0) == 0:
                props.append({"kind": "idea", "key": r["source"], "n": int(r.get("tries") or 0), "file": "",
                              "text": f"proven source {r['source']} found nothing in {r['tries']} tries — try new queries there or retire it",
                              "evidence": [r]})
    props.sort(key=lambda p: (p["kind"], p.get("funnel", ""), p["key"], p.get("change", "")))
    return props


def refused(prop):
    """Why a proposal may not be applied (None = fine). Caps and gates are never writable."""
    key = str(prop.get("key") or "")
    if prop["kind"] == "reweight":
        tail = key.split(".", 1)[1] if key.startswith("weight.") else key
        if SAFETY.search(key) or SAFETY.search(tail):
            return f"{key}: a cap or a gate is never changed by the optimizer"
        if prop.get("n", 0) < MIN_RATE_N:
            return f"{key}: n={prop.get('n')} is below the evidence threshold ({MIN_RATE_N})"
        return None
    if prop["kind"] == "source":
        if prop.get("change") == "drop" and prop.get("n", 0) < MIN_SOURCE_N:
            return f"{key}: n={prop.get('n')} is below the evidence threshold ({MIN_SOURCE_N})"
        return None
    return "informational"


def apply(props, profile_dir, contract, level="supervised", today=None):
    """Apply what the level allows: `autonomous` applies reweights and source moves; `supervised`
    (the default) applies nothing and returns the proposals for the Inbox card. Never touches a
    file the contract's `optimize` block does not name, and only inside the optimizer's marker
    block of the scoring file."""
    today = today or _dt.date.today().isoformat()
    opt = contract.get("optimize") or {}
    applied, held, blocked = [], [], []
    scoring_rel, sources_rel = opt.get("scoring"), opt.get("sources")
    profile_dir = pathlib.Path(profile_dir)
    layer_dir = profile_dir.parent
    weights = {}
    for p in props:
        why = refused(p)
        if why and why != "informational":
            blocked.append({**p, "why": why})
            continue
        if why == "informational":
            continue
        if level != "autonomous":
            held.append(p)
            continue
        if p["kind"] == "reweight" and scoring_rel:
            weights[p["key"]] = p
            applied.append(p)
        elif p["kind"] == "source" and sources_rel:
            sp = layer_dir / sources_rel
            d = explore.load(sp)
            row = next((r for r in d["candidates"] if r["source"].lower() == p["key"].lower()), None)
            if row is None:
                continue
            if p["change"] == "promote":
                d["candidates"].remove(row)
                row["status"] = "active"
                d["proven"].append(row)
            else:
                row["status"] = "dropped"
            explore.save(sp, d)
            applied.append(p)
    if weights and scoring_rel:
        sp = layer_dir / scoring_rel
        txt = sp.read_text(encoding="utf-8") if sp.is_file() else "# Scoring\n"
        old = {}
        m = re.search(r"<!-- optimizer:begin -->\n(.*?)<!-- optimizer:end -->", txt, re.S)
        if m:
            for line in m.group(1).splitlines():
                mm = re.match(r"^- (weight\.[^:]+): (up|down)", line)
                if mm:
                    old[mm.group(1)] = mm.group(2)
        for key, p in weights.items():
            old[key] = p["change"]
        body = f"_Set by the weekly review on {today}; rates at n ≥ {MIN_RATE_N}. Edit or delete any line._\n" + \
            "".join(f"- {k}: {v}\n" for k, v in sorted(old.items()))
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(replace_between(txt, MARK, body, heading="Optimizer weights"), encoding="utf-8")
    return {"applied": applied, "held": held, "blocked": blocked, "level": level}


def review_md(label, props, result, today, title=None, since=None):
    """The body of `<Review> <date>.md`: what converted, where it leaks, what changed and why."""
    title = title or f"{label} review {today}"
    L = ["---", "type: review", f"title: {title}", f"date: {today}", "tags:", "  - review", "---", f"# {title}", ""]
    if since:
        L += [since.rstrip("\n"), ""]
    leaks = [p for p in props if p["kind"] == "leak"]
    L += ["## Where the funnel leaks", ""] + ([f"- {p['text']}" for p in leaks] or ["- Not enough evidence yet (a step needs 20 items before a rate is read)."]) + [""]
    L += ["## What converted", ""] + ([f"- {p['text']}" for p in props if p["kind"] == "reweight" and p["change"] == "up"] or ["- Nothing stands out yet."]) + [""]
    L += ["## What I changed and why", ""]
    if result.get("applied"):
        L += [f"- {p['text']} — applied" for p in result["applied"]]
    if result.get("held"):
        L += [f"- {p['text']} — proposed (waiting for your OK)" for p in result["held"]]
    if result.get("blocked"):
        L += [f"- {p.get('text') or p.get('key')} — refused: {p['why']}" for p in result["blocked"]]
    if not (result.get("applied") or result.get("held") or result.get("blocked")):
        L += ["- Nothing to change this week."]
    ideas = [p for p in props if p["kind"] == "idea"]
    if ideas:
        L += ["", "## Worth trying", ""] + [f"- {p['text']}" for p in ideas]
    L += ["", f"Back to [[{label} Dashboard]]", ""]
    return "\n".join(L)


def _selftest():
    import tempfile  # noqa: PLC0415
    import pipeline_doc as pdoc  # noqa: PLC0415
    S = pdoc.stage
    doc = pdoc.new("t", "T", "#000")
    doc["funnels"] = [pdoc.funnel("f", "F", "thing", "won", [S("a", "A", next=["b"]), S("b", "B", next=["won"]), S("won", "Won", "positive"), S("lost", "Lost", "negative")])]
    items = []
    for i in range(60):
        warm = i % 2 == 0
        st = "won" if (warm and i % 4 == 0) or (not warm and i % 20 == 1) else ("b" if i % 3 else "a")
        items.append(pdoc.item(str(i), f"i{i}", st, funnel="f", attrs={"origin": "warm" if warm else "cold", "cap.email": "25"}))
    doc["items"] = items
    assert pdoc.check(doc) == []
    src = explore.parse(explore.HEADER)
    for n in ("c1", "c2"):
        explore.add(src, n)
    for _ in range(5):
        explore.record(src, "c1", found=0, date="2026-01-15")
    src["candidates"][0]["status"] = "active"   # keep it a live candidate for the proposal
    explore.record(src, "c2", found=2, date="2026-01-15")
    src["candidates"][1]["converted"] = 1       # converted but not yet promoted
    p1 = propose(doc, [], ["origin", "cap.email"], sources=src, today="2026-01-15")
    p2 = propose(doc, [], ["origin", "cap.email"], sources=src, today="2026-01-15")
    assert json.dumps(p1) == json.dumps(p2) and p1
    kinds = {(p["kind"], p.get("key"), p.get("change")) for p in p1}
    assert ("reweight", "weight.origin.warm", "up") in kinds and ("reweight", "weight.origin.cold", "down") in kinds, kinds
    assert ("source", "c1", "drop") in kinds and ("source", "c2", "promote") in kinds
    assert all(p["n"] >= MIN_RATE_N for p in p1 if p["kind"] == "reweight")
    bad = {"kind": "reweight", "key": "weight.cap.email.25", "change": "up", "n": 30}
    assert refused(bad) and "never changed" in refused(bad)
    assert "below the evidence" in refused({"kind": "reweight", "key": "weight.origin.warm", "change": "up", "n": 5})
    with tempfile.TemporaryDirectory() as t:
        prof = pathlib.Path(t) / "layer" / "profile"
        prof.mkdir(parents=True)
        (prof / "scoring.md").write_text("# Scoring\n\n```settings\ncap.email: 25\nweight.hiring: 3\n```\n", encoding="utf-8")
        explore.save(prof / "sources.md", src)
        contract = {"optimize": {"sources": "profile/sources.md", "scoring": "profile/scoring.md", "signals": ["origin"]}}
        r = apply(p1 + [bad], prof, contract, level="supervised", today="2026-01-15")
        assert not r["applied"] and r["held"] and any("never changed" in b["why"] for b in r["blocked"])
        assert (prof / "scoring.md").read_text() == "# Scoring\n\n```settings\ncap.email: 25\nweight.hiring: 3\n```\n"
        r = apply(p1 + [bad], prof, contract, level="autonomous", today="2026-01-15")
        txt = (prof / "scoring.md").read_text()
        assert "- weight.origin.warm: up" in txt and "cap.email: 25" in txt and "weight.cap" not in txt
        d = explore.load(prof / "sources.md")
        assert any(x["source"] == "c2" for x in d["proven"]) and next(x for x in d["candidates"] if x["source"] == "c1")["status"] == "dropped"
        r2 = apply(p1, prof, contract, level="autonomous", today="2026-01-15")
        assert (prof / "scoring.md").read_text() == txt   # idempotent
        md = review_md("Test", p1, r, "2026-01-15")
        assert "## What I changed and why" in md and "applied" in md and "refused" in md
    print("optimize: selftest ok")
    return 0


def _load(pipeline, events):
    doc = json.loads(pathlib.Path(pipeline).read_text(encoding="utf-8"))
    evs = []
    if events and pathlib.Path(events).is_file():
        for line in pathlib.Path(events).read_text(encoding="utf-8").splitlines():
            try:
                evs.append(json.loads(line))
            except ValueError:
                pass
    return doc, evs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selftest"]:
        return _selftest()
    ap = argparse.ArgumentParser(prog="optimize.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("propose", "apply"):
        g = sub.add_parser(name)
        g.add_argument("--pipeline", required=True)
        g.add_argument("--events")
        g.add_argument("--signals", default="")
        g.add_argument("--sources")
        g.add_argument("--today")
        g.add_argument("--json", action="store_true")
        if name == "apply":
            g.add_argument("--profile", required=True)
            g.add_argument("--contract", required=True)
            g.add_argument("--level", default="supervised")
            g.add_argument("--review-out")
            g.add_argument("--label", default="Agent")
    a = ap.parse_args(argv)
    doc, evs = _load(a.pipeline, a.events)
    contract = json.loads(pathlib.Path(a.contract).read_text(encoding="utf-8")) if getattr(a, "contract", None) else {}
    signals = [s for s in (a.signals or ",".join((contract.get("optimize") or {}).get("signals") or [])).split(",") if s]
    src_path = a.sources or (str(pathlib.Path(a.profile).parent / (contract.get("optimize") or {}).get("sources", "")) if getattr(a, "profile", None) and (contract.get("optimize") or {}).get("sources") else None)
    sources = explore.load(src_path) if src_path else None
    props = propose(doc, evs, signals, sources=sources, today=a.today)
    if a.cmd == "propose":
        print(json.dumps(props, indent=None if a.json else 1, ensure_ascii=False))
        return 0
    today = a.today or _dt.date.today().isoformat()
    r = apply(props, a.profile, contract, a.level, today)
    if a.review_out:
        pathlib.Path(a.review_out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.review_out).write_text(review_md(a.label, props, r, today), encoding="utf-8")
    print(json.dumps({"proposals": len(props), "applied": len(r["applied"]), "held": len(r["held"]), "blocked": len(r["blocked"]),
                      "level": a.level, "review": a.review_out or ""}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
