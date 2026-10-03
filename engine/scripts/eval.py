#!/usr/bin/env python3
"""eval.py - benchmarks you can rerun, over the synthetic fixtures. Stdlib only, offline.

    eval.py              retrieval: does graph retrieval surface the right notes? (ground truth
                         computed by query.py — counted, never guessed)
    eval.py --harness    the Harness's safety rules, scripted with no model at all:
                         a failed check costs nothing · caps refuse · a "no" keeps its reason ·
                         a missed slot is reported · a write outside its folder is caught ·
                         an unproven "done" is downgraded · a goal is met only by a real counter

Prints a table; exits 1 if anything fails. Ships in the engine skill; `sbl eval` runs it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import time

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _fixtures() -> pathlib.Path | None:
    for d in [HERE, *HERE.parents]:
        f = d / "tests" / "fixtures"
        if f.is_dir():
            return f
    return None


def _build(src: pathlib.Path, out: pathlib.Path) -> bool:
    r = subprocess.run([sys.executable, str(HERE / "build_vault.py"), str(src), "-o", str(out)], capture_output=True, text=True)
    return r.returncode == 0


# ------------------------------------------------------------------ retrieval (task level)
def eval_retrieval(fx: pathlib.Path) -> list[tuple[str, bool, str]]:
    import query
    import retrieval
    rows = []
    with tempfile.TemporaryDirectory() as d:
        brain = pathlib.Path(d) / "acme"
        if not _build(fx / "company" / "acme", brain):
            return [("build the acme fixture", False, "build failed")]
        notes, edges = retrieval.load_brain(brain)
        title = {n["id"]: n["title"] for n in notes}
        tasks = [("Who works at Acme Robotics?", "people-at", "Acme"),
                 ("Who is Grace Hopper?", "sql", "SELECT title FROM notes WHERE title='Grace Hopper'"),
                 ("Who is in research?", "sql", "SELECT title FROM notes WHERE title='Alan Turing'")]
        for q, how, arg in tasks:
            cols, truth_rows = query.run(brain, ask=how, arg=arg) if how != "sql" else query.run(brain, sql=arg)
            truth = {r[0] for r in truth_rows}
            pack = retrieval.build_pack(q, notes, edges)
            got = {title.get(i) for i in sorted(pack["activations"], key=lambda k: -pack["activations"][k])[:10]}
            hit = len(truth & got)
            rows.append((q, bool(truth) and hit == len(truth), f"{hit}/{len(truth)} in the top 10"))
    return rows


# ------------------------------------------------------------------ the Harness's rules (no model)
def eval_harness(fx: pathlib.Path) -> list[tuple[str, bool, str]]:
    import harness as H
    rows: list = []
    with tempfile.TemporaryDirectory() as d:
        brain = pathlib.Path(d) / "ada"
        if not _build(fx / "personal" / "ada" / "linkedin", brain):
            return [("build the ada fixture", False, "build failed")]
        b = H.Brain(str(brain))

        def routine(title, agent="brain", **kw):
            fm, body = H.routine_note(agent, title, **kw)
            p = H.unique_path(b.dir("routines"), H.safe_name(title))
            H.write_note(p, fm, body)
            return p.stem

        # 1 a failed check-before-start spends nothing
        r1 = routine("Ghost", agent="no-such-agent")
        t0 = time.time()
        res = H.dry_run(b, r1)
        rows.append(("A routine that can't start costs nothing and lands in the Inbox",
                     res["status"] == "preflight-failed" and res["news"] is True and time.time() - t0 < 5,
                     res["status"]))
        # 2 caps refuse
        r2 = routine("Capped", schedule="DAILY 07:00", enabled=True, max_per_day=1)
        H._NOW = None
        import datetime as dt
        H._NOW = dt.datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        p = H.run_open(b, "brain", routine=r2, trigger="schedule")
        H.run_close(b, p, "done")
        due = {x["routine"]: x for x in H.due(b, 5)}
        rows.append(("A routine never runs past its daily cap", due[r2]["action"] in ("skip", "wait"), due[r2]["why"]))
        # 3 a missed slot is reported as late
        r3 = routine("Late", schedule="DAILY 07:00", enabled=True)
        late = {x["routine"]: x for x in H.due(b, 5)}[r3]
        rows.append(("A slot missed while asleep runs once and says how late", late.get("late_minutes", 0) >= 60 and late["action"] == "run",
                     f"{late.get('late_minutes')} min late"))
        H._NOW = None
        # 4 a "no" keeps its reason
        p4 = H.run_open(b, "brain", routine=r3, trigger="schedule")
        H.run_close(b, p4, "done", asks=[{"question": "Send it?", "answered": True, "answer": "No", "reason": "wrong timing"}])
        rows.append(("Your reason for saying no is saved with the run", "wrong timing" in p4.read_text(encoding="utf-8"), ""))
        # 5 a write outside its folder is caught
        p5 = H.run_open(b, "brain", routine=r3, trigger="schedule")
        time.sleep(1.2)
        people = sorted((brain / H.layer_folder(b, "people")).glob("*.md"))
        if people:
            people[0].write_text(people[0].read_text(encoding="utf-8") + "\n", encoding="utf-8")
        c5 = H.run_close(b, p5, "done")
        rep = (brain / c5["report"]).read_text(encoding="utf-8") if c5.get("report") else ""
        rows.append(("A change outside its own folder is flagged and queued for review", "outside its own folder" in rep, ""))
        # 6 an unproven "done" is downgraded
        p6 = H.run_open(b, "brain", routine=r3, trigger="schedule")
        final = "```report\n" + json.dumps({"done": [{"text": "Claimed it"}], "news": True}) + "\n```"
        c6 = H.run_close(b, p6, "done", final_text=final)
        rep6 = (brain / c6["report"]).read_text(encoding="utf-8")
        rows.append(('A "done" with no evidence is marked "couldn\'t verify"', "Claimed it (couldn't verify)" in rep6, ""))
        # 7 a goal is met only by its counter
        gfm, gbody = H.goal_note("brain", "Reconnect", "manual", 2, routines=[r3])
        gp = H.unique_path(b.dir("goals"), "Reconnect")
        H.write_note(gp, gfm, gbody)
        before = H.goal_check(b, gp)["status"]
        H.set_fm(gp, progress=2)
        after = H.goal_check(b, gp)["status"]
        rfm = H.read_note(b.dir("routines") / (r3 + ".md"))[0]
        rows.append(("A goal is met only by a real count — and its routines pause", before == "active" and after == "met" and rfm.get("enabled") is False,
                     f"{before} → {after}"))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Second Brain benchmarks (offline, deterministic)")
    ap.add_argument("--harness", action="store_true", help="the Harness's safety rules, with no model")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    fx = _fixtures()
    if not fx:
        print("eval: the synthetic fixtures are not here (run from the repo)", file=sys.stderr)
        return 2
    rows = eval_harness(fx) if a.harness else eval_retrieval(fx)
    if a.json:
        print(json.dumps([{"check": r[0], "ok": r[1], "detail": r[2]} for r in rows], ensure_ascii=False, indent=1))
    else:
        print(("Harness rules" if a.harness else "Retrieval") + " — " + str(sum(r[1] for r in rows)) + "/" + str(len(rows)) + "\n")
        for name, ok, detail in rows:
            print(("  ✓ " if ok else "  ✗ ") + name + (f"  ({detail})" if detail else ""))
    return 0 if all(r[1] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
