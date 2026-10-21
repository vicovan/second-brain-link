#!/usr/bin/env python3
"""report.py - the run's handoff, twice: the chat report in the fixed order and the ```report fence.

SHIPPED BYTE-IDENTICAL in the engine and every plugin (build_plugin.SHARED_FILES). Stdlib only.

Every daily ends with the same two things (R8): a chat report that leads with the goal counter,
then what was done, what needs you, and what is due next with dates - and a fenced ```report
block that `harness.py run-close` turns into an sbl-report/1 note (Inbox when it is news,
Activity only when quiet). One JSON object feeds both:

    {"goal":      {"label": "interviews", "value": 1, "target": 3, "pace": "on pace"},   # optional
     "done":      [{"text": "Applied to Acme — Staff Engineer", "evidence": "`45-jobs/applications/…`"}],
     "not_done":  ["Globex wants a cover letter I could not source"],
     "next":      ["Follow up with Northwind on Thursday"],
     "needs_you": ["Submit the Acme application (gate)"],
     "due":       [{"what": "Follow-up: Northwind", "when": "2026-01-15"}],               # optional
     "explored":  ["jobs.example (new board): 2 found"],                                  # optional
     "wrote":     ["45-jobs/reports/Shortlist 2026-01-15.md"],
     "news":      true}

    report.py fence --json FILE|-                 print the fence (what the model pastes last)
    report.py chat  --json FILE|- [--label L]     print the chat report in the fixed order
    report.py close --json FILE --run RUN [--brain B] [--status done]   write the sbl-report note
    python3 report.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

KEYS = ("done", "not_done", "next", "needs_you", "wrote")


def normalise(d):
    d = dict(d or {})
    out = {}
    for k in KEYS:
        v = d.get(k) or []
        if isinstance(v, str):
            v = [v]
        if k == "done":
            v = [x if isinstance(x, dict) else {"text": str(x), "evidence": ""} for x in v]
            v = [{"text": str(x.get("text") or "").strip(), "evidence": str(x.get("evidence") or "").strip()} for x in v if str(x.get("text") or "").strip()]
        else:
            v = [str(x).strip() for x in v if str(x).strip()]
        out[k] = v
    out["due"] = [x if isinstance(x, dict) else {"what": str(x), "when": ""} for x in (d.get("due") or [])]
    out["explored"] = [str(x) for x in (d.get("explored") or [])]
    g = d.get("goal")
    out["goal"] = dict(g) if isinstance(g, dict) and g.get("label") else None
    news = d.get("news")
    if news is None:
        news = bool(out["done"] or out["needs_you"] or out["not_done"])
    if out["needs_you"] or out["not_done"]:
        news = True   # an open question always reaches the Inbox
    out["news"] = bool(news)
    return out


def fence(d):
    """The block harness.py run-close reads: the harness keys only, compact, one line each."""
    n = normalise(d)
    body = {"done": n["done"], "not_done": n["not_done"], "next": n["next"], "needs_you": n["needs_you"], "news": n["news"]}
    if n["wrote"]:
        body["wrote"] = n["wrote"]
    return "```report\n" + json.dumps(body, ensure_ascii=False) + "\n```"


def chat(d, label=""):
    """The chat report in the fixed order: goal counter · done · needs you · due next."""
    n = normalise(d)
    lines = []
    g = n["goal"]
    if g:
        tgt = f" of {g['target']}" if g.get("target") not in (None, "") else ""
        pace = f" · {g['pace']}" if g.get("pace") else ""
        lines.append(f"**{g['label']}: {g.get('value', 0)}{tgt}{pace}**")
    if n["done"]:
        lines.append("Done: " + "; ".join(x["text"] for x in n["done"]))
    else:
        lines.append("Done: nothing new — a quiet run." if not n["news"] else "Done: nothing finished yet.")
    if n["needs_you"]:
        lines.append("Needs you: " + "; ".join(n["needs_you"]))
    if n["not_done"]:
        lines.append("Not done yet: " + "; ".join(n["not_done"]))
    if n["due"]:
        lines.append("Due next: " + "; ".join(f"{x.get('what')} ({x.get('when')})" if x.get("when") else str(x.get("what")) for x in n["due"]))
    elif n["next"]:
        lines.append("Next: " + "; ".join(n["next"]))
    if n["explored"]:
        lines.append("Explored today: " + "; ".join(n["explored"]))
    return "\n".join(lines)


def close(brain, run, d, status="done"):
    """Write the sbl-report note through harness.run_close (same folder as this file)."""
    import harness as H  # noqa: PLC0415
    n = normalise(d)
    b = H.Brain(str(brain))
    p = b.abs(run) if str(run).endswith(".md") else (H.find_note(b, "activity", str(run)) or b.abs(run))
    return H.run_close(b, p, status, fence(n), n["wrote"])


def _read_json(src):
    txt = sys.stdin.read() if src == "-" else pathlib.Path(src).read_text(encoding="utf-8")
    return json.loads(txt)


def _selftest():
    d = {"goal": {"label": "interviews", "value": 1, "target": 3, "pace": "on pace"},
         "done": [{"text": "Applied to Acme", "evidence": "`x.md`"}, "Drafted Globex"], "needs_you": [], "next": ["Follow up"],
         "due": [{"what": "Follow-up: Northwind", "when": "2026-01-15"}], "news": False}
    n = normalise(d)
    assert n["done"][1] == {"text": "Drafted Globex", "evidence": ""} and n["news"] is False
    f = fence(d)
    assert f.startswith("```report\n{") and f.endswith("\n```") and json.loads(f.split("\n")[1])["news"] is False
    c = chat(d)
    assert c.splitlines()[0] == "**interviews: 1 of 3 · on pace**" and "Due next: Follow-up: Northwind (2026-01-15)" in c
    assert normalise({"needs_you": ["x"], "news": False})["news"] is True
    assert chat({}) == "Done: nothing new — a quiet run."
    print("report: selftest ok")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selftest"]:
        return _selftest()
    ap = argparse.ArgumentParser(prog="report.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fence", "chat", "close"):
        g = sub.add_parser(name)
        g.add_argument("--json", required=True, dest="src")
        if name == "chat":
            g.add_argument("--label", default="")
        if name == "close":
            g.add_argument("--run", required=True)
            g.add_argument("--brain", default="")
            g.add_argument("--status", default="done")
    a = ap.parse_args(argv)
    d = _read_json(a.src)
    if a.cmd == "fence":
        print(fence(d))
    elif a.cmd == "chat":
        print(chat(d, a.label))
    else:
        import harness as H  # noqa: PLC0415
        brain = a.brain or os.environ.get("SBL_BRAIN") or str(H.find_brain() or "")
        if not brain:
            print("report: no brain", file=sys.stderr)
            return 2
        print(json.dumps(close(brain, a.run, d, a.status), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
