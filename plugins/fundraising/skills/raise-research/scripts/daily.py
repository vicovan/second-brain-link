#!/usr/bin/env python3
"""daily.py - the shared runner every agent's daily follows (the Jobs loop, made generic).

SHIPPED BYTE-IDENTICAL in the engine and every plugin (build_plugin.SHARED_FILES). Stdlib only,
no network, no model. The skill text stays where the domain happens (what to search, how to
score, what to draft); this file guarantees the SHAPE of the run:

    daily.py start  --agent ID [--routine "Daily raise"] [--mode daily|week|today] [--city X] [--dry]
        0 preflight   the profile the contract requires exists (the AI and Chrome are Studio's checks)
        1 recall      memory.py recall --scope <agent>          (printed for the model; skipped on --dry)
        2 orient      the contract's outcome counters + throughput + goal pace, one line each
        3 OPEN THE DAILY NOTE  <layer>/reports/<daily.note> with ## Status first - the dated home
          + opens the harness run (Activity) and renders the line (R1: render early)
    daily.py status "<one line>" [--phase discovering|screening|shortlisting|acting|rendering|reflecting]
        rewrites ## Status, appends the step to the run, re-renders (debounced <= 2 s, atomic)
    daily.py section "<Heading>" --file F | --text T       script-rendered text between markers (R2)
    daily.py explore [--budget N]                          today's 20 % explore slice (explore.py)
    daily.py pace                                          goal progress vs date: on pace | behind
    daily.py close --report report.json [--status done]    report fence -> sbl-report (harness), final render
    daily.py note                                          the daily note's path

Everything it writes is a plain note in the brain or the plugin's own hidden state
(`.plugins/<agent>/daily/<date>.json`). Where it runs: inside a brain (--brain, $SBL_BRAIN, or the
cwd walked up to an identity note). The contract is the plugin's own studio.json (found upward
from this file, or --plugin-dir).

    python3 daily.py --selftest
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import harness as H  # noqa: E402
from ledger_base import replace_between  # noqa: E402

SCHEMA = "sbl-daily/1"
PHASES = ("picking-up", "discovering", "screening", "shortlisting", "acting", "rendering", "reflecting")
DEFAULT_SECTIONS = ("New today", "Due", "Needs you", "Explored today")
DEBOUNCE_S = 2.0
PACE_WORDS = {"on-track": "on pace", "behind": "behind: widen within caps", "met": "met", "overdue": "overdue",
              "unknown": "no date set"}


# ------------------------------------------------------------------ where things are
def find_plugin_dir(agent: str, explicit: str = "") -> pathlib.Path | None:
    if explicit:
        p = pathlib.Path(explicit).expanduser().resolve()
        return p if (p / "studio.json").is_file() else None
    for d in [HERE] + list(HERE.parents):
        sj = d / "studio.json"
        if sj.is_file():
            try:
                if json.loads(sj.read_text(encoding="utf-8")).get("id") == agent:
                    return d
            except (OSError, ValueError):
                pass
    return H.plugin_dir(agent)


def contract_of(pdir: pathlib.Path) -> dict:
    try:
        return json.loads((pdir / "studio.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def script_in(pdir: pathlib.Path, name: str) -> pathlib.Path | None:
    if not re.match(r"^[A-Za-z0-9_.-]+\.py$", name or ""):
        return None
    for p in sorted(pdir.glob("skills/*/scripts/" + name)) + sorted(pdir.glob("scripts/" + name)) + sorted(pdir.glob(name)):
        if p.is_file():
            return p.resolve()
    return None


def run_cmd(pdir: pathlib.Path, brain: pathlib.Path, cmd: str, timeout: int = 180) -> tuple[int, str]:
    parts = shlex.split(cmd or "")
    if not parts:
        return 2, "empty command"
    script = script_in(pdir, parts[0])
    if not script:
        return 2, f"not a script of this agent: {parts[0]}"
    env = dict(os.environ, SBL_BRAIN=str(brain), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env.setdefault("CLAUDE_PROJECT_DIR", str(brain))
    try:
        r = subprocess.run([sys.executable, str(script), *parts[1:]], cwd=str(brain), env=env,
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 2, str(e)
    return r.returncode, ((r.stdout or "") + (("\n" + r.stderr) if r.returncode and r.stderr else "")).strip()


class Run:
    """One daily run: the brain, the contract, today's state file."""

    def __init__(self, agent: str, brain: str = "", plugin_dir: str = "", date: str = ""):
        self.agent = agent
        self.b = H.Brain(brain or None)
        self.brain = self.b.root
        self.pdir = find_plugin_dir(agent, plugin_dir)
        if not self.pdir:
            raise SystemExit(f"daily: no studio.json for agent '{agent}' (pass --plugin-dir)")
        self.c = contract_of(self.pdir)
        self.today = date or H.now().date().isoformat()
        self.layer = str(self.c.get("layer") or "")
        if not self.layer or re.search(r"(^|/)\.\.?(/|$)", self.layer):
            raise SystemExit("daily: the contract has no layer")
        lay = self.c.get("layout") if isinstance(self.c.get("layout"), dict) else {}
        self.reports = str(lay.get("reports") or "reports")
        self.label = str(self.c.get("label") or agent).replace(" Agent", "")
        self.dashboard = str(lay.get("dashboard") or f"{self.label} Dashboard.md")
        self.state_dir = self.brain / ".plugins" / agent / "daily"

    # state
    @property
    def state_path(self) -> pathlib.Path:
        return self.state_dir / f"{self.today}.json"

    def state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_state(self, d: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(self.state_path.name + ".tmp")
        tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.state_path)

    # the daily note
    def note_name(self, mode: str = "daily", city: str = "") -> str:
        d = self.c.get("daily") if isinstance(self.c.get("daily"), dict) else {}
        tmpl = str(d.get("weekly") if mode == "week" else d.get("note") or f"{self.label} today {{date}}")
        name = tmpl.replace("{date}", self.today).replace("{city}", city or "here")
        return H.safe_name(name)

    def note_path(self, mode: str = "daily", city: str = "") -> pathlib.Path:
        st = self.state()
        if st.get("note"):
            return self.brain / st["note"]
        return self.brain / self.layer / self.reports / (self.note_name(mode, city) + ".md")

    def sections(self) -> list[str]:
        d = self.c.get("daily") if isinstance(self.c.get("daily"), dict) else {}
        secs = d.get("sections") if isinstance(d.get("sections"), list) else []
        return [str(s) for s in secs if str(s).strip()] or list(DEFAULT_SECTIONS)

    def open_note(self, p: pathlib.Path, routine: str, run_rel: str, goal_lines: list[str], pickup: str, mode: str) -> str:
        """Create the dated note with ## Status first; an existing note keeps every section and
        only its Status, run and goal lines are refreshed."""
        title = p.stem
        adopted = ""
        if p.is_file():
            txt = p.read_text(encoding="utf-8")
            head = txt.split("---", 2)[1] if txt.startswith("---") else ""
            if f"schema: {SCHEMA}" in head:
                txt = self._set_section(txt, "Status", f"_starting again · {H.now():%H:%M}_")
                if run_rel:
                    txt = re.sub(r"^run: .*$", f"run: \"[[{pathlib.Path(run_rel).stem}]]\"", txt, count=1, flags=re.M)
                p.write_text(txt, encoding="utf-8")
                return "kept"
            # a note a renderer wrote under the daily's name before the daily opened it (the scout
            # ran first): adopt its body into the first section, never lose it
            adopted = re.sub(r"\A\ufeff?\s*---\s*\n.*?\n---[ \t]*\n", "", txt, count=1, flags=re.S)
            adopted = re.sub(r"\A\s*#\s+.*\n", "", adopted, count=1).strip("\n")
        fm = ["---", "type: daily", f"schema: {SCHEMA}", f"title: {title}", f"agent: {self.agent}", f"date: {self.today}",
              f"mode: {mode}", f"routine: {json.dumps('[[' + routine + ']]') if routine else ''}",
              f"run: {json.dumps('[[' + pathlib.Path(run_rel).stem + ']]') if run_rel else ''}",
              "tags:", "  - daily", f"  - agent/{H.slug(self.agent)}", "---"]
        body = [f"# {title}", "", "## Status", "", f"_starting · {H.now():%H:%M}_", "", "## Goal", ""]
        body += (goal_lines or ["_No goal set yet — add one in Goals or the Daily settings._"]) + [""]
        body += ["## Picking up", "", pickup or "_Nothing carried over._", ""]
        for i, s in enumerate(self.sections()):
            if i == 0 and adopted:
                key = H.slug(s)
                body += [f"## {s}", "", f"<!-- {key}:begin -->", adopted, f"<!-- {key}:end -->", ""]
            else:
                body += [f"## {s}", "", ""]
        body += [f"Back to [[{self.dashboard[:-3] if self.dashboard.endswith('.md') else self.dashboard}]]", ""]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(fm) + "\n" + "\n".join(body), encoding="utf-8")
        return "adopted" if adopted else "created"

    @staticmethod
    def _set_section(txt: str, heading: str, body: str) -> str:
        pat = re.compile(rf"(^## {re.escape(heading)}\n)(.*?)(?=^## |^Back to \[\[|\Z)", re.S | re.M)
        if pat.search(txt):
            return pat.sub(lambda m: m.group(1) + "\n" + body.rstrip("\n") + "\n\n", txt, count=1)
        return txt.rstrip("\n") + f"\n\n## {heading}\n\n{body.rstrip()}\n"

    # render (R1)
    def render(self, force: bool = False) -> dict:
        st = self.state()
        cmd = str((self.c.get("render") or {}).get("cmd") or "")
        if not cmd:
            return {"ran": False, "why": "no render command"}
        last = float(st.get("rendered_at") or 0)
        if not force and time.time() - last < DEBOUNCE_S:
            st["render_pending"] = True
            self.save_state(st)
            return {"ran": False, "why": "debounced"}
        rc, out = run_cmd(self.pdir, self.brain, cmd)
        st = self.state()
        st["rendered_at"] = time.time()
        st["render_pending"] = False
        st["render_rc"] = rc
        self.save_state(st)
        return {"ran": True, "code": rc, "out": out[-400:]}

    # orient
    def goals(self) -> list[dict]:
        out = []
        for n in H.list_notes(self.b, "goals"):
            if str(n["fm"].get("agent") or "") == self.agent and str(n["fm"].get("status") or "active") == "active":
                out.append(H.goal_progress(self.b, self.b.abs(n["path"])))
        return out

    def pace(self) -> list[dict]:
        rows = []
        for g in self.goals():
            words = PACE_WORDS.get(g.get("pace") or "unknown", g.get("pace") or "")
            v = g.get("value")
            tgt = g.get("target")
            line = f"{g.get('label') or g.get('metric')} {v if v is not None else '?'}" + (f" of {tgt}" if tgt not in (None, "") else "") + f" · {words}"
            rows.append({**g, "words": words, "line": line})
        return rows

    def orient(self) -> list[str]:
        lines = []
        d = self.c.get("daily") if isinstance(self.c.get("daily"), dict) else {}
        for cmd in (d.get("orient") or []):
            rc, out = run_cmd(self.pdir, self.brain, str(cmd), timeout=60)
            lines.append(f"{cmd}: " + (out.splitlines()[-1] if out else f"exit {rc}"))
        for key, oc in (self.c.get("outcomes") or {}).items():
            if isinstance(oc, dict) and oc.get("cmd"):
                rc, out = run_cmd(self.pdir, self.brain, str(oc["cmd"]), timeout=60)
                lines.append(f"{oc.get('label') or key}: {out.splitlines()[-1] if out else '?'}")
        tp = self.c.get("throughput") if isinstance(self.c.get("throughput"), dict) else {}
        if tp.get("cmd"):
            rc, out = run_cmd(self.pdir, self.brain, str(tp["cmd"]), timeout=60)
            lines.append(f"{tp.get('label') or 'throughput'}: {out.splitlines()[-1] if out else '?'}")
        return lines

    def recall(self) -> str:
        try:
            import memory as M  # noqa: PLC0415
            items = M.recall(self.agent, None, 1200, brain=str(self.brain))
            return "\n".join(M.recall_line(it) for it in items)
        except Exception as e:  # noqa: BLE001 - recall must never stop a run
            return f"(memory unavailable: {e})"

    def preflight(self, dry: bool = False) -> list[str]:
        fails = []
        req = self.c.get("requires") if isinstance(self.c.get("requires"), dict) else {}
        prof = str(req.get("profile") or "")
        if prof and not (self.brain / prof).is_file():
            fails.append(f"not set up: {prof} is missing — run the {req.get('onboardSkill') or 'onboarding'} skill first")
        if not self.c.get("pipeline"):
            fails.append("the contract declares no pipeline file")
        return fails


# ------------------------------------------------------------------ commands
def _chat_run(b, routine: str, goal: str):
    """Started from inside a Studio chat (SBL_RUN_ID = that chat): the chat already has its Activity note, so the
    daily continues it (named after its routine) instead of opening a second "running" run beside it — one run,
    one row, one status."""
    convo = os.environ.get("SBL_RUN_ID", "")
    if not convo:
        return None
    for n in H.list_notes(b, "activity"):
        if str(n["fm"].get("convo") or "") == convo and str(n["fm"].get("status") or "") in ("running", "awaiting"):
            p = b.abs(n["path"])
            rname = H.unwl(routine)
            upd = {}
            if rname and not H.unwl(n["fm"].get("routine")) and H.find_note(b, "routines", rname):
                upd["routine"] = H.wl(rname)
            if goal and not H.unwl(n["fm"].get("goal")) and H.find_note(b, "goals", goal):
                upd["goal"] = H.wl(H.unwl(goal))
            if upd:
                H.set_fm(p, **upd)
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"\n### {rname or 'The daily'} — {H.now():%H:%M}\n")
            return p
    return None


def cmd_start(a) -> int:
    r = Run(a.agent, a.brain, a.plugin_dir, a.date)
    fails = r.preflight(a.dry)
    if fails:
        for f in fails:
            print("  ! " + f, file=sys.stderr)
        if not a.dry:
            return 3
    routine = a.routine or ""
    goals = r.pace()
    goal_lines = [g["line"] for g in goals]
    pickup = H.handoff_block(r.b, routine, r.agent).strip()
    pickup_body = ""
    if pickup:
        pickup_body = "\n".join("> " + ln if ln.strip() else ">" for ln in pickup.splitlines())
    goal_name = ""
    if routine:
        rp = H.find_note(r.b, "routines", routine)
        if rp:
            goal_name = H.unwl(H.read_note(rp)[0].get("goal"))
    run_p = _chat_run(r.b, routine, goal_name) or H.run_open(r.b, r.agent, routine, goal_name, a.trigger,
                                                             convo=os.environ.get("SBL_RUN_ID", ""))
    run_rel = r.b.rel(run_p)
    note_p = r.brain / r.layer / r.reports / (r.note_name(a.mode, a.city) + ".md")
    res = r.open_note(note_p, routine, run_rel, goal_lines, pickup_body, a.mode)
    note_rel = r.b.rel(note_p)
    H.run_append(run_p, f"[picking-up] opened {note_rel} ({res})")
    st = r.state()
    st.update({"schema": "sbl-daily-state/1", "agent": r.agent, "date": r.today, "mode": a.mode, "routine": routine,
               "run": run_rel, "note": note_rel, "city": a.city or "", "started": H.iso(H.now()), "phase": "picking-up"})
    r.save_state(st)
    render = r.render(force=True)
    H.run_append(run_p, "[rendering] line drawn" if render.get("code") == 0 else f"[rendering] render: {render.get('why') or render.get('out', '')[-120:]}")
    recall = "" if a.dry else r.recall()
    orient = [] if a.dry else r.orient()
    out = {"agent": r.agent, "date": r.today, "mode": a.mode, "note": note_rel, "note_result": res, "run": run_rel,
           "routine": routine, "goals": goals, "goal_lines": goal_lines, "orient": orient, "last_report": pickup,
           "recall": recall, "render": render, "preflight": fails, "sections": r.sections(), "dry": bool(a.dry)}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(f"=== DAILY {r.label} · {r.today} · {a.mode} ===")
    print(f"note: {note_rel} ({res})")
    print(f"run:  {run_rel}")
    for ln in goal_lines:
        print(f"goal: {ln}")
    for ln in orient:
        print(f"orient: {ln}")
    if pickup:
        print(pickup)
    if recall:
        print("=== MEMORY ===")
        print(recall)
    for f in fails:
        print("preflight: " + f)
    print("Next: fill the note's sections as you go; `daily.py status` after each step; `daily.py close` last.")
    return 0


def cmd_status(a) -> int:
    r = Run(a.agent, a.brain, a.plugin_dir, a.date)
    st = r.state()
    note = r.note_path()
    phase = a.phase if a.phase in PHASES else st.get("phase") or "acting"
    line = H.clean_line(a.line)
    if note.is_file():
        txt = note.read_text(encoding="utf-8")
        txt = r._set_section(txt, "Status", f"_{line} · {H.now():%H:%M}_")
        note.write_text(txt, encoding="utf-8")
    if st.get("run"):
        try:
            H.run_append(r.b.abs(st["run"]), f"[{phase}] {line}")
        except SystemExit:
            pass
    st["phase"] = phase
    st["status"] = line
    r.save_state(st)
    render = r.render(force=a.render_now)
    if a.json:
        print(json.dumps({"ok": True, "phase": phase, "render": render}, ensure_ascii=False))
    else:
        print(f"status: {line} [{phase}]" + ("" if render.get("ran") else f" · render {render.get('why')}"))
    return 0


def cmd_section(a) -> int:
    r = Run(a.agent, a.brain, a.plugin_dir, a.date)
    note = r.note_path()
    if not note.is_file():
        print("daily: no daily note yet — run `daily.py start` first", file=sys.stderr)
        return 2
    body = a.text if a.text is not None else (sys.stdin.read() if a.file == "-" else pathlib.Path(a.file).read_text(encoding="utf-8"))
    txt = note.read_text(encoding="utf-8")
    key = H.slug(a.heading)
    if re.search(rf"^## {re.escape(a.heading)}\n", txt, re.M) and not re.search(rf"<!-- {re.escape(key)}:begin -->", txt):
        txt = r._set_section(txt, a.heading, f"<!-- {key}:begin -->\n{body.rstrip()}\n<!-- {key}:end -->")
    else:
        txt = replace_between(txt, key, body, heading=a.heading)
    note.write_text(txt, encoding="utf-8")
    print(f"section '{a.heading}' set in {r.b.rel(note)}")
    return 0


def cmd_explore(a) -> int:
    r = Run(a.agent, a.brain, a.plugin_dir, a.date)
    import explore as X  # noqa: PLC0415
    opt = r.c.get("optimize") if isinstance(r.c.get("optimize"), dict) else {}
    rel = a.sources or opt.get("sources") or "profile/sources.md"
    p = r.brain / r.layer / rel
    data = X.load(p)
    share = opt.get("explore", 0.2)
    picks = X.pick(data, r.today, a.budget, share)
    if a.json:
        print(json.dumps({"sources": r.b.rel(p) if p.exists() else str(rel), "share": share, "explore": picks}, ensure_ascii=False))
    else:
        print("\n".join(picks) if picks else "(no candidates — add some to " + str(rel) + ")")
    return 0


def cmd_pace(a) -> int:
    r = Run(a.agent, a.brain, a.plugin_dir, a.date)
    rows = r.pace()
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        print("\n".join(x["line"] for x in rows) if rows else "no active goal")
    return 0


def cmd_close(a) -> int:
    r = Run(a.agent, a.brain, a.plugin_dir, a.date)
    import report as R  # noqa: PLC0415
    st = r.state()
    txt = sys.stdin.read() if a.report == "-" else pathlib.Path(a.report).read_text(encoding="utf-8")
    data = json.loads(txt) if txt.strip() else {}
    n = R.normalise(data)
    if st.get("note") and st["note"] not in n["wrote"]:
        n["wrote"].append(st["note"])
    goals = r.pace()
    if goals and not n.get("goal"):
        g = goals[0]
        n["goal"] = {"label": g.get("label") or g.get("metric"), "value": g.get("value"), "target": g.get("target"), "pace": g.get("words")}
    status = a.status or ("awaiting" if n["needs_you"] else "done")
    note = r.note_path()
    if note.is_file():
        t = note.read_text(encoding="utf-8")
        t = r._set_section(t, "Status", f"_{status} · {H.now():%H:%M}_")
        if n["needs_you"] and re.search(r"^## Needs you\n", t, re.M):
            t = r._set_section(t, "Needs you", "\n".join(f"- {x}" for x in n["needs_you"]))
        note.write_text(t, encoding="utf-8")
    render = r.render(force=True)
    closed = {}
    if st.get("run"):
        H.run_append(r.b.abs(st["run"]), "[reflecting] closing — report written")
        closed = R.close(r.brain, st["run"], n, status)
    st.update({"closed": H.iso(H.now()), "status": status, "report": closed.get("report") if isinstance(closed, dict) else ""})
    r.save_state(st)
    if a.json:
        print(json.dumps({"status": status, "report": closed, "render": render, "chat": R.chat(n), "fence": R.fence(n)}, ensure_ascii=False, indent=1))
    else:
        print(R.chat(n))
        print()
        print(R.fence(n))
        print("\nReflect: at most 3 inferred lessons → memory.py observe --source agent (flagged as inferred).", file=sys.stderr)
    return 0


def cmd_note(a) -> int:
    r = Run(a.agent, a.brain, a.plugin_dir, a.date)
    print(r.b.rel(r.note_path()))
    return 0


# ------------------------------------------------------------------ selftest
def _selftest() -> int:
    import tempfile  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        brain = t / "brain"
        brain.mkdir()
        (brain / "_STRUCTURE.md").write_text("# built\n", encoding="utf-8")     # what makes a folder a brain
        aw = H.agentwork_folder(brain)                                           # resolved, never spelled
        (brain / aw).mkdir()
        layer = "testlayer"
        pd = t / "plug"
        (pd / "skills" / "core" / "scripts").mkdir(parents=True)
        (pd / "skills" / "core" / "scripts" / "render.py").write_text(
            f"import pathlib,sys\np=pathlib.Path('{layer}/pipeline.json');p.parent.mkdir(exist_ok=True);p.write_text('{{}}')\nprint('ok')\n", encoding="utf-8")
        (pd / "skills" / "core" / "scripts" / "ledger.py").write_text("print(2)\n", encoding="utf-8")
        (pd / "studio.json").write_text(json.dumps({
            "schema": "sbl-agent/1", "id": "test-agent", "label": "Test Agent", "layer": layer,
            "layout": {"dashboard": "Test Dashboard.md", "reports": "reports"}, "pipeline": f"{layer}/pipeline.json",
            "render": {"cmd": "render.py"}, "daily": {"note": "Test today {date}", "weekly": "Test review {date}", "sections": ["New today", "Needs you"]},
            "outcomes": {"wins": {"label": "wins", "cmd": "ledger.py count wins"}}, "requires": {"profile": f"{layer}/profile/p.md"},
            "optimize": {"sources": "profile/sources.md", "explore": 0.5}}), encoding="utf-8")
        (brain / layer / "profile").mkdir(parents=True)
        (brain / layer / "profile" / "p.md").write_text("ok", encoding="utf-8")
        (brain / layer / "profile" / "sources.md").write_text("## Candidates\n\n| Source | Kind | Tries | Found | Converted | Last | Status |\n|---|---|---|---|---|---|---|\n| alpha | b | 0 | 0 | 0 | | active |\n| beta | b | 0 | 0 | 0 | | active |\n", encoding="utf-8")
        env_brain = str(brain)
        day = "2026-01-15"
        common = ["--agent", "test-agent", "--brain", env_brain, "--plugin-dir", str(pd), "--date", day]
        import io, contextlib  # noqa: PLC0415
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["start", *common, "--dry", "--json", "--routine", "Daily test"])
        assert rc == 0
        note = brain / layer / "reports" / f"Test today {day}.md"
        txt = note.read_text(encoding="utf-8")
        assert txt.startswith("---\ntype: daily\nschema: sbl-daily/1\n") and "\n## Status\n" in txt and "## New today" in txt and "## Needs you" in txt
        assert (brain / layer / "pipeline.json").is_file()
        assert list((brain / aw / "Activity").glob("*.md"))
        with contextlib.redirect_stdout(buf):
            rc = main(["status", *common, "found 3 new", "--phase", "discovering"])
        assert rc == 0 and "_found 3 new ·" in note.read_text(encoding="utf-8")
        run_txt = next((brain / aw / "Activity").glob("*.md")).read_text(encoding="utf-8")
        assert "[discovering] found 3 new" in run_txt
        with contextlib.redirect_stdout(buf):
            main(["section", *common, "New today", "--text", "| a | b |"])
        t2 = note.read_text(encoding="utf-8")
        assert "<!-- new-today:begin -->\n| a | b |\n<!-- new-today:end -->" in t2
        with contextlib.redirect_stdout(buf):
            main(["section", *common, "New today", "--text", "| c |"])
        t3 = note.read_text(encoding="utf-8")
        assert "| c |" in t3 and "| a | b |" not in t3 and t3.count("## New today") == 1
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["explore", *common, "--budget", "4"])
        assert buf.getvalue().strip() in ("alpha\nbeta", "beta\nalpha")
        rep = t / "r.json"
        rep.write_text(json.dumps({"done": [{"text": "x", "evidence": "y"}], "needs_you": ["decide"], "news": True}), encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["close", *common, "--report", str(rep)])
        assert rc == 0 and "```report" in buf.getvalue()
        reports = list((brain / aw / "Reports").glob("*.md"))
        assert reports and "decide" in reports[0].read_text(encoding="utf-8")
        assert "_awaiting ·" in note.read_text(encoding="utf-8") and "- decide" in note.read_text(encoding="utf-8")
        # start again the same day keeps the note (R6) and refreshes Status
        with contextlib.redirect_stdout(buf):
            rc = main(["start", *common, "--dry", "--json"])
        assert "| c |" in note.read_text(encoding="utf-8") and "_starting again" in note.read_text(encoding="utf-8")
        # a note a renderer wrote under the daily's name BEFORE the daily opened it is adopted, not lost
        day2 = (_dt.date(2026, 1, 15) + _dt.timedelta(days=1)).isoformat()
        early = brain / layer / "reports" / f"Test today {day2}.md"
        early.write_text("---\ntype: report\n---\n# Test today\n\n| 1 | Acme |\n", encoding="utf-8")
        with contextlib.redirect_stdout(buf):
            main(["start", "--agent", "test-agent", "--brain", env_brain, "--plugin-dir", str(pd), "--date", day2, "--dry", "--json"])
        t4 = early.read_text(encoding="utf-8")
        assert "schema: sbl-daily/1" in t4 and "<!-- new-today:begin -->\n| 1 | Acme |\n<!-- new-today:end -->" in t4, t4
    print("daily: selftest ok")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selftest"]:
        return _selftest()
    ap = argparse.ArgumentParser(prog="daily.py", description="the shared daily runner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(g):
        g.add_argument("--agent", required=True)
        g.add_argument("--brain", default="")
        g.add_argument("--plugin-dir", default="")
        g.add_argument("--date", default="", help="ISO date (tests)")
        g.add_argument("--json", action="store_true")

    g = sub.add_parser("start"); common(g)
    g.add_argument("--routine", default="")
    g.add_argument("--mode", default="daily")
    g.add_argument("--city", default="")
    g.add_argument("--trigger", default="manual", choices=H.TRIGGERS)
    g.add_argument("--dry", action="store_true", help="no memory recall, no orient commands; the note, the run and the render still happen")
    g = sub.add_parser("status"); common(g)
    g.add_argument("line")
    g.add_argument("--phase", default="")
    g.add_argument("--render-now", action="store_true")
    g = sub.add_parser("section"); common(g)
    g.add_argument("heading")
    g.add_argument("--file", default="")
    g.add_argument("--text", default=None)
    g = sub.add_parser("explore"); common(g)
    g.add_argument("--sources", default="")
    g.add_argument("--budget", type=int, default=10)
    g = sub.add_parser("pace"); common(g)
    g = sub.add_parser("close"); common(g)
    g.add_argument("--report", required=True)
    g.add_argument("--status", default="", choices=("", "done", "awaiting", "failed", "stopped", "capped"))
    g = sub.add_parser("note"); common(g)
    a = ap.parse_args(argv)
    if a.cmd == "section" and a.text is None and not a.file:
        ap.error("section needs --file or --text")
    return {"start": cmd_start, "status": cmd_status, "section": cmd_section, "explore": cmd_explore,
            "pace": cmd_pace, "close": cmd_close, "note": cmd_note}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
