#!/usr/bin/env python3
"""kpi.py - funnel counts, conversions, rates at n >= 20, trends; the body of <Agent> KPI.md.

SHIPPED BYTE-IDENTICAL in the engine and every plugin (build_plugin.SHARED_FILES). Stdlib only,
deterministic: the same pipeline + events give the same numbers and the same Markdown.

Reads what every agent already writes - its `pipeline.json` (sbl-pipeline/2, with `funnels`) and
its `events.jsonl` (one line per status move: {key, from, to, at}) - and computes, per funnel:

  counts        items per stage (hidden stages included - never lost)
  conversions   between consecutive OPEN stages and into the success stage: num / den, and a
                rate ONLY once the denominator has >= 20 (counts below that - the rule
                `sales-optimize` and the Jobs KPI already follow)
  trend         how many items reached the success stage in the last 7 and 28 days
  by signal     (optional) the success rate per value of an item attribute (`attrs.<signal>`),
                the material optimize.py proposes from

"Reached stage k" = the item sits at stage k or later on the open chain (or in a positive
stage), OR an event moved it into stage k. Items in parked / negative stages count as having
reached every open stage they passed through (by events) and nothing beyond.

    kpi.py --pipeline FILE [--events FILE] [--signals a,b] [--json | --md --label "Jobs"]
    python3 kpi.py --selftest
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline_doc as pdoc  # noqa: E402

MIN_N = 20
TRENDS = (7, 28)


def _at(e):
    return str(e.get("at") or e.get("ts") or "")[:10]


def _key(e):
    return e.get("key") or e.get("account") or e.get("id") or e.get("trip") or ""


def _rate(num, den, min_n=MIN_N):
    return (round(num / den, 3) if den >= min_n and den else None)


def compute(doc, events=None, today=None, signals=None, min_n=MIN_N):
    today = _dt.date.fromisoformat(today) if isinstance(today, str) else (today or _dt.date.today())
    events = events or []
    reached_by_events = {}      # key -> set(stage ids any event moved it into)
    success_at = {}             # key -> earliest date it entered a success stage (per funnel later)
    for e in events:
        k = _key(e)
        for st in (e.get("from"), e.get("to")):
            if k and st:
                reached_by_events.setdefault(k, set()).add(st)
    out = {"schema": "sbl-kpi/1", "generated": today.isoformat(), "funnels": []}
    items = doc.get("items") or []
    for f in pdoc.funnels_of(doc):
        fid = f.get("id") or ""
        stages = f.get("stages") or []
        roles = {s["id"]: s.get("role") for s in stages}
        chain = pdoc.open_chain(f)
        full = pdoc.open_chain(f, include_collapsed=True)      # a collapsed open stage still sits on the path
        fidx = {sid: i for i, sid in enumerate(full)}
        success = f.get("success") or ""
        mine = [it for it in items if (it.get("funnel") or "") == fid]
        counts = {s["id"]: 0 for s in stages}
        for it in mine:
            if it.get("stage") in counts:
                counts[it["stage"]] += 1
        # reached sets
        idx = {sid: i for i, sid in enumerate(chain)}
        reached = {sid: 0 for sid in chain}
        reached_success = 0
        recent = {d: 0 for d in TRENDS}
        by_signal = {s: {} for s in (signals or [])}
        for it in mine:
            st = it.get("stage")
            evs = reached_by_events.get(it.get("id"), set())
            got = set(evs)
            for sid in list(evs):          # reaching a stage on the path means every earlier one was passed
                if sid in fidx:
                    got.update(full[: fidx[sid] + 1])
            if st in fidx:
                got.update(full[: fidx[st] + 1])
            elif roles.get(st) == "positive":
                got.update(chain)
                got.add(st)
            elif st in roles:
                got.add(st)
            for sid in chain:
                if sid in got:
                    reached[sid] += 1
            ok = success in got
            if ok:
                reached_success += 1
                when = str(it.get("stage_since") or it.get("updated") or "")[:10]
                for e in events:
                    if _key(e) == it.get("id") and e.get("to") == success:
                        when = _at(e)
                        break
                try:
                    age = (today - _dt.date.fromisoformat(when)).days
                except ValueError:
                    age = None
                if age is not None:
                    for d in TRENDS:
                        if 0 <= age <= d:
                            recent[d] += 1
            for s in by_signal:
                v = (it.get("attrs") or {}).get(s)
                if v in (None, ""):
                    continue
                v = str(v)
                g = by_signal[s].setdefault(v, {"n": 0, "success": 0})
                g["n"] += 1
                g["success"] += 1 if ok else 0
        conversions = []
        for i in range(len(chain) - 1):
            a, b = chain[i], chain[i + 1]
            conversions.append({"from": a, "to": b, "num": reached[b], "den": reached[a], "rate": _rate(reached[b], reached[a], min_n)})
        den = reached[chain[0]] if chain else len(mine)
        fo = {"id": fid, "label": f.get("label") or fid, "item": f.get("item") or "item", "success": success,
              "success_label": next((s.get("label") for s in stages if s["id"] == success), success),
              "n": len(mine), "counts": counts, "chain": chain, "reached": reached,
              "conversions": conversions,
              "success_rate": {"num": reached_success, "den": den, "rate": _rate(reached_success, den, min_n), "min_n": min_n},
              "trend": {f"{d}d": recent[d] for d in TRENDS},
              "funnel_line": " → ".join(f"{reached[s]}" for s in chain) + (f" → {reached_success}" if success else "")}
        if signals:
            fo["by_signal"] = {s: {v: {**g, "rate": _rate(g["success"], g["n"], min_n)} for v, g in sorted(vals.items())}
                               for s, vals in by_signal.items() if vals}
        if f.get("success2"):
            s2 = f["success2"]
            n2 = sum(1 for it in mine if s2 in (reached_by_events.get(it.get("id"), set()) | ({it.get("stage")} if it.get("stage") == s2 else set())))
            fo["success2"] = {"id": s2, "num": n2, "den": den, "rate": _rate(n2, den, min_n)}
        out["funnels"].append(fo)
    return out


def _pct(x):
    return "—" if x is None else f"{round(100 * x)} %"


def markdown(k, label, title=None, changes=None, extra=None, tags=None, aliases=None):
    """The KPI note: frontmatter + one section per funnel + the last review's changes."""
    title = title or f"{label} KPI"
    lines = ["---", "type: kpi", f"title: {title}", f"agent_label: {label}", f"updated: {k['generated']}",
             "tags:", "  - kpi"] + [f"  - {t}" for t in (tags or [])]
    if aliases:
        lines += ["aliases:"] + [f"  - {json.dumps(a, ensure_ascii=False)}" for a in aliases]
    lines += ["---", f"# {title}", "",
             f"> Numbers from the ledger, rendered {k['generated']}. A rate shows only once its denominator reaches "
             f"{MIN_N}; below that you see the counts. Nothing here is typed by a model.", ""]
    for f in k["funnels"]:
        lines.append(f"## {f['label']} — {f['success_label']} {f['success_rate']['num']}"
                     + (f" of {f['success_rate']['den']}" if f['success_rate']['den'] else "") + "")
        lines.append("")
        lines.append(f"**Funnel:** {f['funnel_line'] or '—'} · **{f['success_label']} rate:** "
                     f"{_pct(f['success_rate']['rate'])} ({f['success_rate']['num']}/{f['success_rate']['den']})"
                     f" · **last 7 d:** {f['trend']['7d']} · **last 28 d:** {f['trend']['28d']}")
        lines.append("")
        lines.append("| Stage | Items now | Reached |")
        lines.append("|---|---|---|")
        for sid in f["chain"]:
            lines.append(f"| {sid} | {f['counts'].get(sid, 0)} | {f['reached'].get(sid, 0)} |")
        for sid, n in f["counts"].items():
            if sid not in f["chain"]:
                lines.append(f"| {sid} | {n} | |")
        lines.append("")
        if f["conversions"]:
            lines.append("| Step | Converted | Rate |")
            lines.append("|---|---|---|")
            for c in f["conversions"]:
                lines.append(f"| {c['from']} → {c['to']} | {c['num']} / {c['den']} | {_pct(c['rate'])} |")
            lines.append("")
        for s, vals in (f.get("by_signal") or {}).items():
            lines.append(f"### By {s}")
            lines.append("")
            lines.append(f"| {s} | Items | {f['success_label']} | Rate |")
            lines.append("|---|---|---|---|")
            for v, g in vals.items():
                lines.append(f"| {v} | {g['n']} | {g['success']} | {_pct(g['rate'])} |")
            lines.append("")
    if changes:
        lines += ["## What the last review changed", ""] + [f"- {c}" for c in changes] + [""]
    if extra:
        lines += [extra.rstrip("\n"), ""]
    lines.append(f"Back to [[{label} Dashboard]]")
    return "\n".join(lines) + "\n"


def _selftest():
    S = pdoc.stage
    T = _dt.date(2026, 1, 15)
    doc = pdoc.new("t", "T", "#000")
    doc["funnels"] = [pdoc.funnel("f", "F", "thing", "won", [S("a", "A", next=["b"]), S("b", "B", next=["c"]), S("c", "C", next=["won"]),
                                                       S("won", "Won", "positive"), S("lost", "Lost", "negative")])]
    items = []
    for i in range(30):
        st = "a" if i < 10 else ("b" if i < 20 else ("c" if i < 25 else ("won" if i < 28 else "lost")))
        items.append(pdoc.item(str(i), f"i{i}", st, funnel="f", attrs={"origin": "warm" if i % 2 else "cold"}, stage_since=(T - _dt.timedelta(days=5)).isoformat()))
    doc["items"] = items
    assert pdoc.check(doc) == []
    evs = [{"key": "29", "from": "b", "to": "lost", "at": (T - _dt.timedelta(days=10)).isoformat()}, {"key": "26", "from": "c", "to": "won", "at": (T - _dt.timedelta(days=19)).isoformat()}]
    k = compute(doc, evs, today=T.isoformat(), signals=["origin"])
    f = k["funnels"][0]
    assert f["counts"]["a"] == 10 and f["reached"]["a"] == 29 and f["reached"]["b"] == 19 and f["reached"]["c"] == 8, f["reached"]
    assert f["success_rate"]["num"] == 3 and f["success_rate"]["den"] == 29 and f["success_rate"]["rate"] == round(3 / 29, 3)
    assert f["conversions"][0]["rate"] == round(19 / 29, 3) and f["conversions"][1]["rate"] is None   # den 19 < 20
    assert f["trend"]["7d"] == 2 and f["trend"]["28d"] == 3
    assert f["by_signal"]["origin"]["cold"]["n"] == 15 and f["by_signal"]["origin"]["cold"]["rate"] is None
    k2 = compute(doc, evs, today=T.isoformat(), signals=["origin"])
    assert json.dumps(k) == json.dumps(k2)
    md = markdown(k, "Test", changes=["re-weighted origin"])
    assert "## F — Won 3 of 29" in md and "| a → b | 19 / 29 | 66 % |" in md and md.endswith("Back to [[Test Dashboard]]\n")
    # a doc without funnels still works (one anonymous funnel)
    old = pdoc.new("t", "T", "#000")
    old["stages"] = [S("x", "X", next=["y"]), S("y", "Y", "positive")]
    old["items"] = [pdoc.item("1", "one", "y")]
    assert compute(old)["funnels"][0]["reached"]["x"] == 1
    print("kpi: selftest ok")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selftest"]:
        return _selftest()
    ap = argparse.ArgumentParser(prog="kpi.py")
    ap.add_argument("--pipeline", required=True)
    ap.add_argument("--events")
    ap.add_argument("--signals", default="")
    ap.add_argument("--today")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--label", default="Agent")
    a = ap.parse_args(argv)
    doc = json.loads(pathlib.Path(a.pipeline).read_text(encoding="utf-8"))
    evs = []
    if a.events and pathlib.Path(a.events).is_file():
        for line in pathlib.Path(a.events).read_text(encoding="utf-8").splitlines():
            try:
                evs.append(json.loads(line))
            except ValueError:
                pass
    k = compute(doc, evs, today=a.today, signals=[s for s in a.signals.split(",") if s])
    if a.md:
        print(markdown(k, a.label), end="")
    else:
        print(json.dumps(k, indent=1 if not a.json else None, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
