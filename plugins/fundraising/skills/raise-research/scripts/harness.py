#!/usr/bin/env python3
"""harness.py - the Second Brain Harness: goals, routines, reports and activity. Stdlib only,
no network, no model calls.

SHIPPED BYTE-IDENTICAL in the engine and every plugin (job-search, fundraising, travel-planner);
the plugin build fails if the copies differ. Design + user model:
second-brain-link-docs/docs-harness/SBL-HARNESS-USER-MODEL.md.

Everything lives in the user's brain, as plain notes they own, under ONE layer (key `agentwork`,
folder resolved per subject - never hardcoded here):

    <brain>/<agentwork>/
      Goals/<Title>.md        sbl-goal/1     an outcome with a finish line, counted from real results
      Routines/<Title>.md     sbl-routine/1  work that repeats (schedule + "only when" conditions)
      Reports/<Title>.md      sbl-report/1   the handoff a run leaves: Done / Not done yet / Next / Needs you
      Activity/<Title>.md     sbl-run/1      what exactly happened, step by step (the replay)
    <brain>/.plugins/harness/ state.json (last fired per routine), inbox.json (read/dismissed),
                              _HARNESS_GENERATED.json (seeded templates, so user edits survive)
    <brain>/_REVIEW.json      sbl-review/1   suggestions for people/orgs, waiting for a human

The five steps every run follows (the harness-engineering subsystems, made visible):
  1 check before starting  -> `preflight` (zero tokens; a failure becomes an Inbox item)
  2 pick up where it left  -> `last-report` (the handoff block injected into the next run)
  3 work within limits     -> caps + `only_when` + the caller's tool ceiling
  4 independent check      -> `verify` (pass-gate: a Done item needs evidence)
  5 clean handoff          -> `run-close` writes the report; news decides Inbox vs quiet

    harness.py where                                   harness.py list KIND [--agent A] [--limit N]
    harness.py show NOTE                               harness.py inbox [--dismiss ID] [--read ID]
    harness.py seed --from DIR --agent ID              harness.py routine-new --agent A --title T ...
    harness.py goal-new --agent A --title T ...        harness.py set NOTE KEY VALUE
    harness.py preflight ROUTINE                       harness.py when ROUTINE
    harness.py due [--max-per-day N]                   harness.py fired ROUTINE [--status S]
    harness.py run-open --agent A [--routine R] [--trigger T] [--convo C]
    harness.py run-append RUN --line TEXT              harness.py run-close RUN --status S [...]
    harness.py last-report ROUTINE|AGENT               harness.py verify RUN
    harness.py goal-progress GOAL                      harness.py run ROUTINE --provider none
    harness.py review add|list|resolve ...
Global: --brain PATH (else $SBL_BRAIN, else walk up from the cwd), --json, --now ISO (tests).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys

# Windows consoles default to the ANSI code page (cp1252); never let output crash a run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SCHEMA_GOAL, SCHEMA_ROUTINE = "sbl-goal/1", "sbl-routine/1"
SCHEMA_REPORT, SCHEMA_RUN, SCHEMA_REVIEW = "sbl-report/1", "sbl-run/1", "sbl-review/1"
SUBDIRS = {"goals": "Goals", "routines": "Routines", "reports": "Reports", "activity": "Activity"}
KINDS = tuple(SUBDIRS)
RUN_STATUSES = ("queued", "preflight-failed", "running", "awaiting", "interrupted", "capped",
                "failed", "denied", "done", "skipped", "stopped")
TERMINAL = ("preflight-failed", "interrupted", "capped", "failed", "denied", "done", "skipped", "stopped")
GOAL_STATUSES = ("active", "met", "stopped", "archived")
ROUTINE_STATUSES = ("draft", "validated", "retired")
NOTIFY = ("news", "always", "never")
TRIGGERS = ("manual", "schedule", "chat", "goal")
DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
STATE_DIR = (".plugins", "harness")
MANIFEST = "_HARNESS_GENERATED.json"
REVIEW_FILE = "_REVIEW.json"
MAX_LINE = 2000
DEFAULT_MAX_PER_DAY = 1
DEFAULT_MAX_MINUTES = 30

# ------------------------------------------------------------------ time (overridable for tests)
_NOW: _dt.datetime | None = None


def now() -> _dt.datetime:
    if _NOW is not None:
        return _NOW
    env = os.environ.get("SBL_NOW")
    if env:
        try:
            return _dt.datetime.fromisoformat(env)
        except ValueError:
            pass
    return _dt.datetime.now().replace(microsecond=0)


def iso(t: _dt.datetime) -> str:
    return t.replace(microsecond=0).isoformat()


def human_dt(t: _dt.datetime) -> str:
    """'2 Oct 2026, 07:00' - built by hand: the no-padding day directive is not portable
    (Windows strftime rejects it)."""
    return f"{t.day} {t:%b %Y}, {t:%H:%M}"


def _parse_dt(s) -> _dt.datetime | None:
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(str(s).strip().strip('"').replace("Z", ""))
    except ValueError:
        return None


# ------------------------------------------------------------------ where the brain is
BRAIN_MARKERS = ("_STRUCTURE.md", "_GENERATED.json", "graph.json")


def _is_brain(d: pathlib.Path) -> bool:
    return (d / "_memory").is_dir() or any((d / m).is_file() for m in BRAIN_MARKERS)


def find_brain(explicit: str | None = None) -> pathlib.Path | None:
    for cand in (explicit, os.environ.get("SBL_BRAIN")):
        if cand:
            p = pathlib.Path(cand).expanduser()
            if p.is_dir():
                return p.resolve()
    here = pathlib.Path.cwd().resolve()
    for d in [here, *here.parents]:
        if _is_brain(d):
            return d
        if d.name == ".plugins" and _is_brain(d.parent):
            return d.parent
    return None


def agentwork_folder(brain: pathlib.Path) -> str:
    """The folder of the `agentwork` layer in this brain. Resolved through the engine's layout
    (engine copy) or the plugin's paths.py (plugin copies) - never a literal here, because a
    company brain may name it differently (the same rule tests/run.py enforces for plugins)."""
    here = pathlib.Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    try:  # engine: analyze.brain_layout reads layout.json variants for this brain's subject
        import analyze  # noqa: PLC0415

        folder = analyze._L(brain, "agentwork")
        if folder:
            return folder
    except Exception:
        pass
    try:  # plugin: paths.layer(brain, key) mirrors the same variants
        import paths  # noqa: PLC0415

        return paths.layer(brain, "agentwork")
    except Exception:
        pass
    raise SystemExit("harness: cannot resolve the agentwork layer (no engine layout, no paths.py)")


class Brain:
    def __init__(self, explicit: str | None = None, must: bool = True):
        b = find_brain(explicit)
        if not b and must:
            raise SystemExit("harness: no brain found (pass --brain or run inside a brain)")
        self.root = b
        self.folder = agentwork_folder(b) if b else ""

    def dir(self, kind: str | None = None) -> pathlib.Path:
        base = self.root / self.folder
        return base / SUBDIRS[kind] if kind else base

    def rel(self, p: pathlib.Path) -> str:
        return p.resolve().relative_to(self.root.resolve()).as_posix()

    def abs(self, rel: str) -> pathlib.Path:
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root.resolve()) + os.sep):
            raise SystemExit(f"harness: path outside the brain: {rel}")
        return p

    def state_dir(self) -> pathlib.Path:
        return self.root.joinpath(*STATE_DIR)


# The layers a ROUTINE run may never write: the builder's knowledge layers and every OTHER agent's
# layer. Resolved per subject through the same layout (keys, never folder literals here).
PROTECTED_KEYS = ("root", "people", "orgs", "reputation", "voice", "shopping", "career", "mirror",
                  "learning", "services", "search", "places", "synthesis")
AGENT_LAYER_KEYS = {"job-search": "jobs", "fundraising": "fundraising", "travel-planner": "travel"}


def layer_folder(b: "Brain", key: str) -> str:
    here = pathlib.Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    try:
        import analyze  # noqa: PLC0415

        return analyze._L(b.root, key) or ""
    except Exception:
        pass
    try:
        import paths  # noqa: PLC0415

        return paths.layer(b.root, key)
    except Exception:
        return ""


def protected_folders(b: "Brain", agent: str = "") -> list[str]:
    own = AGENT_LAYER_KEYS.get(agent, "")
    keys = list(PROTECTED_KEYS) + [k for a, k in AGENT_LAYER_KEYS.items() if k != own]
    out = []
    for k in keys:
        f = layer_folder(b, k)
        if f and f not in out and not f.startswith("_"):
            out.append(f)
    return out


def changed_since(b: "Brain", folders: list[str], since: _dt.datetime | None) -> list[str]:
    """Files in these folders modified at or after `since` (a run's start) — the double-check on
    a run's write block: Bash can write where Write/Edit are denied, so look at the disk."""
    if not since:
        return []
    # the start is stored to the second, so only count what changed AFTER that second — a write
    # in the same second as the start (the build that just finished, say) is not the run's doing
    cut = since.timestamp() + 1
    hits = []
    for f in folders:
        d = b.root / f
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            try:
                if p.is_file() and p.stat().st_mtime >= cut:
                    hits.append(b.rel(p))
            except OSError:
                continue
            if len(hits) >= 50:
                return hits
    return hits


# ------------------------------------------------------------------ tiny YAML (flat frontmatter)
# Flat on purpose: Obsidian Properties and the engine's own frontmatter reader only handle
# `key: scalar` and `key:` + `  - item` lists, so nested maps would not round-trip.
def ys(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s == "":
        return ""
    needs = (re.search(r'[:#\[\]{}>|*&!%@`"\n]', s) or s != s.strip()
             or s.lower() in ("true", "false", "null", "yes", "no", "~")
             or re.match(r"^[-?,]", s) or re.match(r"^-?\d+(\.\d+)?$", s))
    if needs:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'
    return s


def render_fm(d: dict) -> str:
    out = ["---"]
    for k, v in d.items():
        if isinstance(v, (list, tuple)):
            if v:
                out.append(f"{k}:")
                out.extend(f"  - {ys(x)}" for x in v)
            else:
                out.append(f"{k}: []")
        else:
            s = ys(v)
            out.append(f"{k}:" if s == "" else f"{k}: {s}")
    out.append("---")
    return "\n".join(out)


def _unscalar(s: str):
    s = s.strip()
    if s == "" or s in ("~", "null"):
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        inner = s[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if s[0] == '"' else inner.replace("''", "'")
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if re.match(r"^-?\d+$", s):
        return int(s)
    if re.match(r"^-?\d+\.\d+$", s):
        return float(s)
    if re.fullmatch(r"\[\[[^\[\]]+\]\]", s):
        return s  # a bare wikilink ([[Goal]]) is a link, not a nested list
    if s.startswith("[") and s.endswith("]"):
        body = s[1:-1].strip()
        return [_unscalar(x) for x in _split_inline(body)] if body else []
    return s


def _split_inline(body: str) -> list[str]:
    out, cur, q = [], "", ""
    for ch in body:
        if q:
            cur += ch
            if ch == q:
                q = ""
        elif ch in "\"'":
            q = ch
            cur += ch
        elif ch == ",":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def parse_note(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm: dict = {}
    key = None
    for ln in text[3:end].strip("\n").splitlines():
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s*-\s+(.*)$", ln)
        if m and key is not None:
            if not isinstance(fm.get(key), list):
                fm[key] = []
            fm[key].append(_unscalar(m.group(1)))
            continue
        m = re.match(r"^([A-Za-z0-9_]+):(.*)$", ln)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        fm[key] = _unscalar(val) if val else None
    body = text[end + 4:]
    return fm, body[1:] if body.startswith("\n") else body


def read_note(p: pathlib.Path) -> tuple[dict, str]:
    return parse_note(p.read_text(encoding="utf-8", errors="replace"))


def write_note(p: pathlib.Path, fm: dict, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(render_fm(fm) + "\n" + body.lstrip("\n"), encoding="utf-8")
    os.replace(tmp, p)


def set_fm(p: pathlib.Path, **changes) -> dict:
    fm, body = read_note(p)
    fm.update(changes)
    write_note(p, fm, body)
    return fm


def safe_name(s: str) -> str:
    """Obsidian-safe title == filename (the engine's obsidian_name rule)."""
    s = re.sub(r'[\[\]#^|:\\/<>*?"]', "", s or "")
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    return s[:100] or "Untitled"


def wl(name: str) -> str:
    return f"[[{name}]]" if name else ""


def unwl(v) -> str:
    s = str(v or "").strip().strip('"')
    m = re.match(r"^\[\[([^\]|#]+)", s)
    return m.group(1).strip() if m else s


# ------------------------------------------------------------------ notes
def list_notes(b: Brain, kind: str) -> list[dict]:
    d = b.dir(kind)
    out = []
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.md")):
        if p.name.endswith(".new.md"):
            continue
        fm, body = read_note(p)
        out.append({"name": p.stem, "path": b.rel(p), "fm": fm, "body": body})
    return out


def find_note(b: Brain, kind: str, ref: str) -> pathlib.Path | None:
    """A note by title, wikilink or vault-relative path."""
    ref = unwl(ref)
    if not ref:
        return None
    if ref.endswith(".md") or "/" in ref:
        try:
            p = b.abs(ref if ref.endswith(".md") else ref + ".md")
        except SystemExit:
            return None
        return p if p.is_file() else None
    p = b.dir(kind) / (safe_name(ref) + ".md")
    if p.is_file():
        return p
    for n in list_notes(b, kind):  # fall back to the note's id
        if str(n["fm"].get("id") or "") == ref:
            return b.abs(n["path"])
    return None


def unique_path(d: pathlib.Path, stem: str) -> pathlib.Path:
    p = d / f"{stem}.md"
    i = 2
    while p.exists():
        p = d / f"{stem} ({i}).md"
        i += 1
    return p


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:60] or "x"


# ------------------------------------------------------------------ state (+ lock)
class State:
    def __init__(self, b: Brain):
        self.dir = b.state_dir()
        self.path = self.dir / "state.json"

    def __enter__(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lf = open(self.dir / ".lock", "a+")
        try:
            import fcntl  # noqa: PLC0415  (absent on Windows: single writer assumed)

            fcntl.flock(self._lf, fcntl.LOCK_EX)
        except ImportError:
            pass
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.data = {}
        self.data.setdefault("schema", "sbl-harness-state/1")
        self.data.setdefault("routines", {})
        self.data.setdefault("inbox", {})
        return self

    def save(self):
        tmp = self.path.with_name("state.json.tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def __exit__(self, *exc):
        try:
            import fcntl  # noqa: PLC0415

            fcntl.flock(self._lf, fcntl.LOCK_UN)
        except ImportError:
            pass
        self._lf.close()


def read_state(b: Brain) -> dict:
    try:
        return json.loads((b.state_dir() / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"routines": {}, "inbox": {}}


# ------------------------------------------------------------------ schedules
def parse_schedule(s) -> dict | None:
    """'manual' | 'DAILY 07:00' | 'WEEKDAYS 07:00' | 'MON 08:00' | 'MON,THU 08:00' |
    'MONTHLY 1 07:00' | 'EVERY 6h'. None = invalid."""
    s = str(s or "manual").strip().upper()
    if s in ("", "MANUAL", "NONE", "OFF"):
        return {"kind": "manual"}
    m = re.match(r"^EVERY\s+(\d{1,2})\s*H$", s)
    if m and 1 <= int(m.group(1)) <= 24:
        return {"kind": "every", "hours": int(m.group(1))}
    m = re.match(r"^(DAILY|WEEKDAYS|WEEKENDS|MONTHLY\s+(\d{1,2})|([A-Z]{3}(?:,[A-Z]{3})*))\s+(\d{1,2}):(\d{2})$", s)
    if not m:
        return None
    hh, mm = int(m.group(4)), int(m.group(5))
    if hh > 23 or mm > 59:
        return None
    head = m.group(1)
    if head == "DAILY":
        return {"kind": "days", "days": list(range(7)), "at": (hh, mm)}
    if head == "WEEKDAYS":
        return {"kind": "days", "days": [0, 1, 2, 3, 4], "at": (hh, mm)}
    if head == "WEEKENDS":
        return {"kind": "days", "days": [5, 6], "at": (hh, mm)}
    if head.startswith("MONTHLY"):
        day = int(m.group(2))
        return {"kind": "monthly", "day": day, "at": (hh, mm)} if 1 <= day <= 28 else None
    days = head.split(",")
    if any(d not in DAYS for d in days):
        return None
    return {"kind": "days", "days": sorted({DAYS.index(d) for d in days}), "at": (hh, mm)}


def describe_schedule(s) -> str:
    spec = parse_schedule(s)
    if not spec:
        return "invalid schedule"
    if spec["kind"] == "manual":
        return "Manual — run it when you want"
    if spec["kind"] == "every":
        return f"Every {spec['hours']} hours"
    at = "%02d:%02d" % spec["at"]
    if spec["kind"] == "monthly":
        return f"Monthly on day {spec['day']} at {at}"
    days = spec["days"]
    if days == list(range(7)):
        return f"Every day at {at}"
    if days == [0, 1, 2, 3, 4]:
        return f"Weekdays at {at}"
    if days == [5, 6]:
        return f"Weekends at {at}"
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return ", ".join(names[d] for d in days) + f" at {at}"


def last_slot(spec: dict, t: _dt.datetime) -> _dt.datetime | None:
    """The most recent scheduled moment <= t (None for manual)."""
    if not spec or spec["kind"] == "manual":
        return None
    if spec["kind"] == "every":
        h = spec["hours"]
        base = t.replace(minute=0, second=0, microsecond=0)
        return base.replace(hour=(base.hour // h) * h)
    hh, mm = spec["at"]
    for back in range(0, 62):
        day = (t - _dt.timedelta(days=back)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        if day > t:
            continue
        if spec["kind"] == "days" and day.weekday() in spec["days"]:
            return day
        if spec["kind"] == "monthly" and day.day == spec["day"]:
            return day
    return None


def next_slot(spec: dict, t: _dt.datetime) -> _dt.datetime | None:
    if not spec or spec["kind"] == "manual":
        return None
    for step in range(1, 24 * 62):
        cand = t + _dt.timedelta(hours=step)
        ls = last_slot(spec, cand)
        if ls and ls > t:
            return ls
    return None


# ------------------------------------------------------------------ plugins (installed agents)
def _plugin_roots() -> list[pathlib.Path]:
    roots = []
    env = os.environ.get("SBL_PLUGINS_DIR")
    if env:
        roots += [pathlib.Path(p).expanduser() for p in env.split(os.pathsep) if p]
    roots.append(pathlib.Path.home() / ".claude" / "skills")
    here = pathlib.Path(__file__).resolve()
    for d in here.parents:  # running from the repo: <repo>/plugins
        if (d / "plugins").is_dir() and (d / "engine").is_dir():
            roots.append(d / "plugins")
            break
        if (d / ".claude-plugin").is_dir():  # running from inside an installed plugin
            roots.append(d.parent)
            break
    return roots


def plugin_dir(agent: str) -> pathlib.Path | None:
    if not agent or not re.match(r"^[a-z0-9][a-z0-9._-]{0,63}$", agent):
        return None
    for r in _plugin_roots():
        for cand in (r / agent, r):
            sj = cand / "studio.json"
            if sj.is_file():
                try:
                    if json.loads(sj.read_text(encoding="utf-8")).get("id") == agent:
                        return cand.resolve()
                except (OSError, json.JSONDecodeError):
                    continue
    return None


def studio_json(agent: str) -> dict:
    d = plugin_dir(agent)
    if not d:
        return {}
    try:
        return json.loads((d / "studio.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def plugin_script(agent: str, name: str) -> pathlib.Path | None:
    """Only a script INSIDE the agent's own plugin may be run by a condition or a counter."""
    if not re.match(r"^[A-Za-z0-9_.-]+\.py$", name or ""):
        return None
    d = plugin_dir(agent)
    if not d:
        return None
    for p in sorted(d.glob("skills/*/scripts/" + name)) + sorted(d.glob(name)):
        rp = p.resolve()
        if str(rp).startswith(str(d) + os.sep) and rp.is_file():
            return rp
    return None


def run_plugin_cmd(b: Brain, agent: str, cmd: str, timeout: int = 60) -> tuple[int, str]:
    parts = shlex.split(cmd or "")
    if not parts:
        return 2, "empty command"
    script = plugin_script(agent, parts[0])
    if not script:
        return 2, f"not a script of the {agent} agent: {parts[0]}"
    env = dict(os.environ, SBL_BRAIN=str(b.root), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run([sys.executable, str(script), *parts[1:]], cwd=str(b.root), env=env,
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 2, str(e)
    return r.returncode, (r.stdout or "").strip()


# ------------------------------------------------------------------ conditions ("only when")
def eval_condition(b: Brain, agent: str, cond: str, routine: str = "") -> tuple[bool, str]:
    """One deterministic, zero-token condition. Forms:
       stamp_not_today: a.txt, b.txt     (files in the agent's .plugins/<agent>/ state)
       cmd: script.py args | exit 0      (or | gt 0, | eq N) - the agent's own scripts only
       stale_days: N                     (the brain was not rebuilt in N days)
       changed: <glob>                   (a note matching glob changed since this routine's last run)
    """
    c = str(cond or "").strip()
    m = re.match(r"^([a-z_]+)\s*:\s*(.*)$", c)
    if not m:
        return False, f"unknown condition: {c}"
    kind, arg = m.group(1), m.group(2).strip()
    if kind == "stamp_not_today":
        today = now().date().isoformat()
        sd = b.root / ".plugins" / agent
        for f in [x.strip() for x in arg.split(",") if x.strip()]:
            if not re.match(r"^[A-Za-z0-9_.-]+$", f):
                return False, f"bad stamp name {f}"
            p = sd / f
            if p.is_file() and p.read_text(encoding="utf-8", errors="replace").strip() == today:
                return False, f"{f} says it already ran or was snoozed today"
        return True, "has not run today"
    if kind == "cmd":
        cmdpart, _, test = arg.partition("|")
        rc, out = run_plugin_cmd(b, agent, cmdpart.strip())
        test = test.strip() or "exit 0"
        tm = re.match(r"^(exit|gt|eq|ge)\s+(-?\d+)$", test)
        if not tm:
            return False, f"bad test {test}"
        op, n = tm.group(1), int(tm.group(2))
        if op == "exit":
            return rc == n, f"{cmdpart.strip()} exited {rc}"
        try:
            v = int(float(out.splitlines()[-1].strip())) if out else 0
        except ValueError:
            return False, f"{cmdpart.strip()} printed no number"
        ok = {"gt": v > n, "eq": v == n, "ge": v >= n}[op]
        return ok, f"{cmdpart.strip()} = {v}"
    if kind == "stale_days":
        try:
            n = int(arg)
        except ValueError:
            return False, "bad stale_days"
        g = b.root / "_GENERATED.json"
        if not g.is_file():
            return True, "never built"
        age = (now() - _dt.datetime.fromtimestamp(g.stat().st_mtime)).days
        return age >= n, f"brain is {age} days old"
    if kind == "changed":
        pat = arg.strip().strip("/")
        if not pat or ".." in pathlib.PurePosixPath(pat).parts or pathlib.PurePosixPath(pat).is_absolute():
            return False, f"bad changed pattern {arg}"
        prev = runs_for(b, routine=routine) if routine else []
        since = None
        for r in prev:
            if str(r["fm"].get("status") or "") not in ("skipped", "preflight-failed", "running"):
                since = _parse_dt(r["fm"].get("started"))
                break
        if since is None:
            return True, "first run — nothing to compare with"
        cut = since.timestamp()
        for f in b.root.glob(pat):
            if f.is_file() and f.stat().st_mtime > cut:
                return True, f"{b.rel(f)} changed since the last run"
        return False, f"nothing matching {pat} changed since the last run"
    return False, f"unknown condition: {kind}"


def eval_when(b: Brain, rfm: dict, routine: str = "") -> tuple[bool, list[str]]:
    agent = str(rfm.get("agent") or "")
    conds = rfm.get("only_when") or []
    if isinstance(conds, str):
        conds = [conds]
    reasons = []
    for c in conds:
        ok, why = eval_condition(b, agent, c, routine)
        reasons.append(("✓ " if ok else "✗ ") + why)
        if not ok:
            return False, reasons
    return True, reasons or ["no conditions"]


# ------------------------------------------------------------------ preflight (check before starting)
def preflight(b: Brain, rfm: dict) -> list[dict]:
    """File-level checks only (no network, no model). Studio adds the ones it can see itself
    (AI signed in, Chrome connected). Each failure: {check, why, fix}."""
    fails = []
    agent = str(rfm.get("agent") or "brain")
    if not (b.root / "_STRUCTURE.md").is_file() and not (b.root / "graph.json").is_file():
        fails.append({"check": "brain_present", "why": "This brain hasn't been built yet.",
                      "fix": "Open Sources and Reseed it."})
    if agent != "brain":
        sj = studio_json(agent)
        if not sj:
            fails.append({"check": "agent_installed", "why": f"The {agent} agent isn't installed.",
                          "fix": "Open Agents and install it."})
        else:
            prof = str((sj.get("requires") or {}).get("profile") or "")
            if prof and not (b.root / prof).is_file():
                onboard = (sj.get("requires") or {}).get("onboardSkill") or "onboarding"
                fails.append({"check": "profile_present",
                              "why": f"{sj.get('label') or agent} isn't set up yet.",
                              "fix": f"Open the agent and run its setup ({onboard})."})
    skill = str(rfm.get("skill") or "")
    if skill and not re.match(r"^[a-z0-9][a-z0-9._:-]{0,80}$", skill):
        fails.append({"check": "skill_name", "why": f"Bad skill name: {skill}", "fix": "Edit the routine."})
    if parse_schedule(rfm.get("schedule")) is None:
        fails.append({"check": "schedule", "why": f"I can't read the schedule '{rfm.get('schedule')}'.",
                      "fix": "Edit the routine and pick a schedule."})
    return fails


# ------------------------------------------------------------------ runs (Activity notes)
def runs_for(b: Brain, routine: str = "", agent: str = "", day: _dt.date | None = None,
             trigger: str | None = None) -> list[dict]:
    out = []
    for n in list_notes(b, "activity"):
        fm = n["fm"]
        if routine and unwl(fm.get("routine")) != routine:
            continue
        if agent and str(fm.get("agent") or "") != agent:
            continue
        if trigger and str(fm.get("trigger") or "") != trigger:
            continue
        st = _parse_dt(fm.get("started"))
        if day and (not st or st.date() != day):
            continue
        out.append(n)
    out.sort(key=lambda n: str(n["fm"].get("started") or ""), reverse=True)
    return out


def run_open(b: Brain, agent: str, routine: str = "", goal: str = "", trigger: str = "manual",
             convo: str = "", title: str = "", reuse: bool = False) -> pathlib.Path:
    t = now()
    if reuse and convo:
        # one chat = one Activity note: a later message in the same conversation continues it
        for n in list_notes(b, "activity"):
            if str(n["fm"].get("convo") or "") == convo:
                p = b.abs(n["path"])
                set_fm(p, status="running", ended=None)
                with open(p, "a", encoding="utf-8") as f:
                    f.write(f"\n### New message — {t:%H:%M}\n")
                return p
    rname = unwl(routine)
    label = title or rname or (studio_json(agent).get("label") or agent or "Brain") + " chat"
    d = b.dir("activity")
    d.mkdir(parents=True, exist_ok=True)
    # "YYYY-MM-DD at HHhMM …": never a long run of digits, which privacy sweeps read as a phone number
    p = unique_path(d, safe_name(f"{t:%Y-%m-%d} at {t:%Hh%M} {label}"))
    fm = {
        "schema": SCHEMA_RUN, "type": "run",
        "tags": ["run", f"agent/{slug(agent or 'brain')}", f"trigger/{trigger if trigger in TRIGGERS else 'manual'}"],
        "id": f"run-{t:%Y%m%d}T{t:%H%M%S}-{slug(label)[:24]}",
        "agent": agent or "brain",
        "routine": wl(rname) if rname and find_note(b, "routines", rname) else "",
        "goal": wl(unwl(goal)) if goal and find_note(b, "goals", goal) else "",
        "trigger": trigger if trigger in TRIGGERS else "manual",
        "status": "running", "convo": convo, "started": iso(t), "ended": None,
        "report": "", "verified": None,
    }
    body = (f"# {label} — {human_dt(t)}\n\n"
            "> What exactly happened on this run, step by step. Written as it goes, so a half-finished\n"
            "> run is still readable — and resumable.\n\n## Steps\n")
    write_note(p, fm, body)
    return p


def clean_line(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s[:MAX_LINE]


def run_append(p: pathlib.Path, line: str) -> None:
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"- {now():%H:%M:%S} · {clean_line(line)}\n")


REPORT_FENCE = re.compile(r"```report\s*\n(.*?)\n```", re.S)


def parse_handoff(final_text: str) -> dict | None:
    """The run's own handoff: a ```report fence with JSON {done, not_done, next, needs_you, news}."""
    m = None
    for m in REPORT_FENCE.finditer(final_text or ""):
        pass
    if not m:
        return None
    try:
        d = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    out = {}
    for k in ("done", "not_done", "next", "needs_you"):
        v = d.get(k) or []
        if isinstance(v, str):
            v = [v]
        items = []
        for it in v[:30]:
            if isinstance(it, dict):
                items.append({"text": clean_line(it.get("text") or ""), "evidence": clean_line(it.get("evidence") or "")})
            else:
                items.append({"text": clean_line(it), "evidence": ""})
        out[k] = [x for x in items if x["text"]]
    out["news"] = bool(d.get("news", bool(out.get("done") or out.get("needs_you"))))
    return out


def _bullets(items: list[dict], empty: str, show_ev: bool = False) -> str:
    if not items:
        return f"- {empty}\n"
    lines = []
    for it in items:
        ev = f" — _evidence: {it['evidence']}_" if show_ev and it.get("evidence") else ""
        mark = " ✓" if it.get("verified") else (" (couldn't verify)" if it.get("verified") is False else "")
        lines.append(f"- {it['text']}{mark}{ev}")
    return "\n".join(lines) + "\n"


STOP_REASON_TEXT = {
    "done": "", "capped": "Stopped at its limit (time or runs per day).",
    "denied": "You said no at an approval, so it stopped there.",
    "interrupted": "Interrupted (the app quit, the Mac slept or the session ended) — it will pick up from here.",
    "failed": "It hit an error.", "preflight-failed": "It didn't start — something needs setting up first.",
    "skipped": "Nothing to do — its conditions weren't met.",
    "stopped": "You stopped it.",
}


def run_close(b: Brain, p: pathlib.Path, status: str, final_text: str = "", wrote: list[str] | None = None,
              asks: list[dict] | None = None, stop_reason: str = "", fails: list[dict] | None = None) -> dict:
    """Close a run: stamp the Activity note and write the handoff report (routine/goal runs and
    any run that needs you). Returns {report, news}."""
    status = status if status in RUN_STATUSES else "failed"
    fm, body = read_note(p)
    t = now()
    agent = str(fm.get("agent") or "brain")
    routine = unwl(fm.get("routine"))
    trigger = str(fm.get("trigger") or "manual")
    hand = parse_handoff(final_text) or {}
    asks = asks or []
    open_asks = [a for a in asks if not a.get("answered")]
    needs = list(hand.get("needs_you") or [])
    for a in open_asks:
        needs.append({"text": clean_line(a.get("question") or "A question is waiting for you."), "evidence": ""})
    for f in fails or []:
        needs.append({"text": f"{f.get('why')} {f.get('fix') or ''}".strip(), "evidence": ""})
    if status == "awaiting" and not needs:
        needs.append({"text": "A question is waiting for you.", "evidence": ""})
    # step 4, the independent check: a Done item counts only with evidence that exists (the
    # pass-gate). Checked here, in code — the agent's own word is not enough.
    done_items = verify_items(b, list(hand.get("done") or []))
    n_ok = sum(1 for it in done_items if it.get("verified"))
    news = bool(hand.get("news")) if hand else bool(final_text.strip())
    if needs or status in ("failed", "preflight-failed", "denied"):
        news = True
    if status == "skipped":
        news = False
    # the write block's double-check — only for routine runs, which may write their own folder only
    strays: list[str] = []
    if routine or trigger in ("schedule", "goal"):
        strays = changed_since(b, protected_folders(b, agent), _parse_dt(fm.get("started")))
        if strays:
            needs.append({"text": f"It changed {len(strays)} file(s) outside its own folder — check them: "
                                  + ", ".join(strays[:5]), "evidence": ""})
            news = True
            review_add(b, "unexpected", f"{routine or agent} changed notes outside its folder",
                       strays[:10], "A routine run is only allowed to write its own folder. Check these "
                       "changes and keep or undo them.", source=b.rel(p))
    write_report = bool(routine or trigger in ("schedule", "goal") or needs or status in ("failed", "preflight-failed"))
    rep_rel = ""
    if write_report:
        label = routine or (studio_json(agent).get("label") or agent)
        rd = b.dir("reports")
        rd.mkdir(parents=True, exist_ok=True)
        rp = unique_path(rd, safe_name(f"{label} — {t.day} {t:%b %Y} at {t:%Hh%M}"))
        summary = ""
        if not hand and final_text.strip():
            # no structured handoff: keep the agent's last words (trimmed) so nothing is lost
            summary = REPORT_FENCE.sub("", final_text).strip()[:4000]
        rfm = {
            "schema": SCHEMA_REPORT, "type": "report",
            "tags": ["report", f"agent/{slug(agent)}", "news" if news else "quiet"],
            "agent": agent, "routine": wl(routine) if routine else "",
            "goal": fm.get("goal") or "", "run": wl(p.stem), "status": status,
            "news": news, "date": t.date().isoformat(), "at": iso(t), "provisional": None,
            "verified": f"{n_ok} of {len(done_items)}" if done_items else None,
        }
        if routine:
            rn = find_note(b, "routines", routine)
            if rn and str(read_note(rn)[0].get("status") or "") == "draft":
                rfm["provisional"] = True
        text = [f"# {label} — {human_dt(t)}\n"]
        reason = stop_reason or STOP_REASON_TEXT.get(status, "")
        if reason:
            text.append(f"> {reason}\n")
        if rfm["provisional"]:
            text.append("> **Provisional** — this routine is still a draft. Validate it once you trust it.\n")
        text.append("## Done\n" + _bullets(done_items, "Nothing finished this run.", show_ev=True))
        if done_items and n_ok < len(done_items):
            text.append("> Items marked *couldn't verify* had no evidence the harness could find — treat them as "
                        "not done until you check.\n")
        text.append("## Not done yet\n" + _bullets(hand.get("not_done") or [], "Nothing left open."))
        text.append("## Next step\n" + _bullets(hand.get("next") or [], "Nothing planned."))
        text.append("## Needs you\n" + _bullets(needs, "Nothing — you're clear."))
        if summary:
            text.append("## In its own words\n" + summary + "\n")
        text.append(f"\n---\nFull step-by-step: {wl(p.stem)}\n")
        write_note(rp, rfm, "\n".join(text))
        rep_rel = b.rel(rp)
    fm.update({"status": status, "ended": iso(t), "report": wl(pathlib.Path(rep_rel).stem) if rep_rel else "",
               "verified": f"{n_ok} of {len(done_items)}" if done_items else None})
    qa = []
    for a in asks:
        q = clean_line(a.get("question") or "")
        if a.get("answered"):
            qa.append(f"- asked: {q} → you answered: {clean_line(a.get('answer')) or '(no answer)'}"
                      + (f" — reason: {clean_line(a.get('reason'))}" if a.get("reason") else ""))
        else:
            qa.append(f"- asked: {q} → still waiting for you")
    if qa:
        body = body.rstrip("\n") + "\n\n## Questions and answers\n" + "\n".join(qa) + "\n"
    if wrote:
        body = body.rstrip("\n") + "\n\n## Wrote\n" + "\n".join(f"- `{clean_line(w)}`" for w in wrote[:200]) + "\n"
    body = body.rstrip("\n") + f"\n\n**Ended:** {status} at {t:%H:%M}" + (f" — {stop_reason}" if stop_reason else "") + "\n"
    write_note(p, fm, body)
    out = {"run": b.rel(p), "report": rep_rel, "news": news, "status": status}
    goal = unwl(fm.get("goal"))
    if not goal and routine:
        rn = find_note(b, "routines", routine)
        goal = unwl(read_note(rn)[0].get("goal")) if rn else ""
    gp = find_note(b, "goals", goal) if goal else None
    if gp:
        g = goal_check(b, gp)
        if g.get("changed"):
            out["goal"] = {"goal": gp.stem, "status": g.get("status"), "report": g.get("report", "")}
    return out


def last_report(b: Brain, routine: str = "", agent: str = "") -> dict | None:
    cands = []
    for n in list_notes(b, "reports"):
        fm = n["fm"]
        if routine and unwl(fm.get("routine")) != routine:
            continue
        if not routine and agent and str(fm.get("agent") or "") != agent:
            continue
        cands.append(n)
    cands.sort(key=lambda n: (str(n["fm"].get("at") or n["fm"].get("date") or ""), n["name"]))
    return cands[-1] if cands else None


def handoff_block(b: Brain, routine: str = "", agent: str = "") -> str:
    """The `=== LAST REPORT ===` block a new run starts from (step 2: pick up where it left off)."""
    r = last_report(b, routine, agent)
    if not r:
        return ""
    body = r["body"]
    keep = []
    for sec in ("Not done yet", "Next step", "Needs you", "Done"):
        m = re.search(r"^## " + re.escape(sec) + r"\n(.*?)(?=^## |\n---|\Z)", body, re.S | re.M)
        txt = m.group(1).strip() if m else ""
        if txt and not txt.startswith("- Nothing"):
            keep.append(f"{sec}:\n{txt}")
    if not keep:
        # it HAS run before (so this is no rehearsal) — it just left nothing open
        return ("=== LAST REPORT (" + str(r["fm"].get("date") or "") + ", " + r["path"] + ") ===\n"
                "Nothing was left open last time. Start fresh, but don't redo what is already done.\n"
                "=== END LAST REPORT ===")
    return ("=== LAST REPORT (" + str(r["fm"].get("date") or "") + ", " + r["path"] + ") ===\n"
            "Pick up from here: finish what is not done, follow the next step, don't redo what is done.\n"
            + "\n\n".join(keep)[:3000] + "\n=== END LAST REPORT ===")


# ------------------------------------------------------------------ independent check (pass-gate)
def verify_items(b: Brain, items: list[dict]) -> list[dict]:
    """Deterministic part of the check: an item with evidence pointing at a vault file must find
    that file. Items without evidence are 'couldn't verify'. (Studio's checker subagent adds the
    judgement on top; this is the floor nothing can talk its way past.)"""
    out = []
    for it in items:
        ev = str(it.get("evidence") or "").strip()
        ok = None
        if ev:
            paths = re.findall(r"`([^`]+)`", ev) or re.findall(r"([\w./ -]+\.(?:md|pdf|json|jsonl|geojson|docx))", ev)
            if paths:
                ok = True
                for rel in paths:
                    try:
                        if not b.abs(rel.strip()).exists():
                            ok = False
                    except SystemExit:
                        ok = False
            else:
                ok = True  # a non-file evidence (a ledger key, a quoted reply) - kept, judged by the checker
        else:
            ok = False
        it = dict(it)
        it["verified"] = ok
        out.append(it)
    return out


# ------------------------------------------------------------------ due (the scheduler's question)
def due(b: Brain, max_per_day: int = 3) -> list[dict]:
    """Every routine with what the scheduler should do now: run | wait | skip | blocked.
    Deterministic and free: no model call decides whether to act."""
    t = now()
    st = read_state(b)
    sched_today = sum(1 for n in runs_for(b, day=t.date(), trigger="schedule")
                      if str(n["fm"].get("status")) not in ("skipped", "preflight-failed"))
    out = []
    for n in list_notes(b, "routines"):
        fm = n["fm"]
        name = n["name"]
        rec = {"routine": name, "path": n["path"], "agent": fm.get("agent") or "brain",
               "schedule": fm.get("schedule") or "manual", "describe": describe_schedule(fm.get("schedule"))}
        spec = parse_schedule(fm.get("schedule"))
        if fm.get("enabled") is not True:
            rec.update(action="off", why="Off")
        elif str(fm.get("status") or "") == "retired":
            rec.update(action="off", why="Retired")
        elif not spec:
            rec.update(action="blocked", why="Unreadable schedule")
        elif spec["kind"] == "manual":
            rec.update(action="manual", why="Runs only when you start it")
        else:
            slot = last_slot(spec, t)
            last = _parse_dt((st.get("routines") or {}).get(name, {}).get("last_slot"))
            nxt = next_slot(spec, t)
            rec["next"] = iso(nxt) if nxt else None
            if not slot or (last and last >= slot):
                rec.update(action="wait", why="Not due yet")
            else:
                rec["slot"] = iso(slot)
                rec["late_minutes"] = int((t - slot).total_seconds() // 60)
                cap = int(fm.get("max_per_day") or DEFAULT_MAX_PER_DAY)
                done_today = len([r for r in runs_for(b, routine=name, day=t.date(), trigger="schedule")
                                  if str(r["fm"].get("status")) not in ("skipped",)])
                fails = preflight(b, fm)
                if done_today >= cap:
                    rec.update(action="skip", why=f"Already ran {done_today}× today (limit {cap})")
                elif sched_today >= max_per_day:
                    rec.update(action="skip", why=f"Daily limit of {max_per_day} scheduled runs reached")
                elif fails:
                    rec.update(action="blocked", why=fails[0]["why"], fails=fails)
                else:
                    ok, reasons = eval_when(b, fm, name)
                    rec["conditions"] = reasons
                    rec.update(action="run" if ok else "skip", why="Due" if ok else reasons[-1].lstrip("✗ "))
        goal = unwl(fm.get("goal"))
        if goal:
            g = find_note(b, "goals", goal)
            if g and rec.get("action") == "run":
                goal_check(b, g)  # a goal met since the last run stops its routine before it spends anything
            if g and str(read_note(g)[0].get("status") or "active") != "active" and rec.get("action") == "run":
                rec.update(action="skip", why=f"Its goal '{goal}' is no longer active")
        out.append(rec)
    return out


def mark_fired(b: Brain, routine: str, slot: str = "", status: str = "") -> None:
    with State(b) as s:
        r = s.data["routines"].setdefault(routine, {})
        r["last_slot"] = slot or iso(now())
        r["last_fired"] = iso(now())
        if status:
            r["last_status"] = status
        s.save()


# ------------------------------------------------------------------ goals
def goal_progress(b: Brain, gp: pathlib.Path) -> dict:
    fm, _ = read_note(gp)
    agent = str(fm.get("agent") or "")
    metric = str(fm.get("metric") or "")
    target = fm.get("target")
    res = {"goal": gp.stem, "path": b.rel(gp), "agent": agent, "metric": metric,
           "target": target, "by": fm.get("by"), "status": fm.get("status") or "active", "value": None,
           "pace": "", "label": ""}
    counters = (studio_json(agent).get("outcomes") or {}) if agent else {}
    c = counters.get(metric) if isinstance(counters, dict) else None
    if isinstance(c, dict):
        res["label"] = c.get("label") or metric
        rc, out = run_plugin_cmd(b, agent, str(c.get("cmd") or ""))
        if rc == 0:
            try:
                res["value"] = int(float(out.splitlines()[-1]))
            except (ValueError, IndexError):
                res["value"] = None
    elif metric == "manual":
        res["label"] = str(fm.get("metric_label") or "done")
        res["value"] = int(fm.get("progress") or 0)
    try:
        tgt = int(target)
    except (TypeError, ValueError):
        tgt = None
    v = res["value"]
    by = None
    try:
        by = _dt.date.fromisoformat(str(fm.get("by") or ""))
    except ValueError:
        pass
    if tgt and v is not None and v >= tgt:
        res["pace"] = "met"
    elif by and now().date() > by:
        res["pace"] = "overdue"
    elif tgt and v is not None and by:
        created = None
        try:
            created = _dt.date.fromisoformat(str(fm.get("created") or ""))
        except ValueError:
            pass
        start = created or now().date()
        span = max(1, (by - start).days)
        elapsed = max(0, (now().date() - start).days)
        expected = tgt * elapsed / span
        res["pace"] = "on-track" if v >= expected - 0.5 else "behind"
    else:
        res["pace"] = "unknown"
    return res


def goal_check(b: Brain, gp: pathlib.Path) -> dict:
    """Met only from the counter (an anchor in the real world), never from an agent's claim.
    Also stops a goal whose deadline passed (when asked to) or whose routines ran N times
    without the counter moving (`stop_after_runs`). Either change pauses its routines and
    writes one report, which lands in the Inbox."""
    pr = goal_progress(b, gp)
    fm, _ = read_note(gp)
    if str(fm.get("status") or "active") != "active":
        return pr
    key = gp.stem
    why = ""
    new = ""
    if pr["pace"] == "met":
        new = "met"
    elif pr["pace"] == "overdue" and fm.get("stop_when_overdue") is True:
        new, why = "stopped", "Deadline passed"
    else:
        try:
            limit = int(fm.get("stop_after_runs") or 0)
        except (TypeError, ValueError):
            limit = 0
        with State(b) as s:
            g = s.data.setdefault("goals", {}).setdefault(key, {})
            if pr["value"] is not None and g.get("value") != pr["value"]:
                g["value"] = pr["value"]
                g["since"] = iso(now())
                s.save()
            since = _parse_dt(g.get("since")) or _parse_dt(str(fm.get("created") or ""))
        if limit > 0 and since is not None:
            quiet = [r for r in list_notes(b, "activity")
                     if unwl(r["fm"].get("goal")) == key or unwl(r["fm"].get("routine")) in
                     [unwl(x) for x in (fm.get("routines") or [])]]
            quiet = [r for r in quiet if (_parse_dt(r["fm"].get("started")) or since) >= since
                     and str(r["fm"].get("status") or "") not in ("skipped", "preflight-failed", "running")]
            if len(quiet) >= limit:
                new, why = "stopped", f"No progress in {len(quiet)} runs"
    if not new:
        return pr
    if new == "met":
        set_fm(gp, status="met", met_on=now().date().isoformat())
    else:
        set_fm(gp, status="stopped", stopped_why=why)
    paused = []
    for r in fm.get("routines") or []:
        rp = find_note(b, "routines", unwl(r))
        if rp and read_note(rp)[0].get("enabled") is True:
            set_fm(rp, enabled=False)
            paused.append(rp.stem)
    pr["status"] = new
    pr["changed"] = True
    pr["report"] = _goal_report(b, gp, fm, pr, new, why, paused)
    return pr


def _goal_report(b: Brain, gp: pathlib.Path, fm: dict, pr: dict, new: str, why: str, paused: list[str]) -> str:
    t = now()
    agent = str(fm.get("agent") or "brain")
    rd = b.dir("reports")
    rd.mkdir(parents=True, exist_ok=True)
    head = "Goal met" if new == "met" else "Goal stopped"
    rp = unique_path(rd, safe_name(f"{head} — {gp.stem} — {t.day} {t:%b %Y} at {t:%Hh%M}"))
    rfm = {"schema": SCHEMA_REPORT, "type": "report", "tags": ["report", f"agent/{slug(agent)}", "news", "goal"],
           "agent": agent, "routine": "", "goal": wl(gp.stem), "run": "", "status": new, "news": True,
           "date": t.date().isoformat(), "at": iso(t), "provisional": None, "verified": None}
    count = f"{pr.get('value')} of {pr.get('target')} {pr.get('label') or pr.get('metric') or ''}".strip()
    lines = [f"# {head}: {gp.stem}\n"]
    if new == "met":
        lines.append(f"> Reached {count} — counted from the record, not from an agent's claim.\n")
    else:
        lines.append(f"> {why}. At {count}.\n")
    lines.append("## Done\n" + (f"- {count}\n" if pr.get("value") is not None else "- Nothing counted.\n"))
    lines.append("## Not done yet\n" + ("- Nothing left open.\n" if new == "met" else f"- The goal: {count}.\n"))
    lines.append("## Next step\n" + (("- Paused: " + ", ".join(wl(x) for x in paused) + "\n") if paused
                                      else "- Nothing planned.\n"))
    lines.append("## Needs you\n" + ("- Nothing — you're clear. Set a new goal when you're ready.\n" if new == "met"
                                      else "- Change the goal or its routines, then set it back to active.\n"))
    lines.append(f"\n---\nGoal: {wl(gp.stem)}\n")
    write_note(rp, rfm, "\n".join(lines))
    return b.rel(rp)


# ------------------------------------------------------------------ creating notes
def routine_note(agent: str, title: str, skill: str = "", schedule: str = "manual", goal: str = "",
                 only_when: list[str] | None = None, max_per_day: int = DEFAULT_MAX_PER_DAY,
                 max_minutes: int = DEFAULT_MAX_MINUTES, notify: str = "news", enabled: bool = False,
                 status: str = "draft", body: str = "") -> tuple[dict, str]:
    fm = {
        "schema": SCHEMA_ROUTINE, "type": "routine", "tags": ["routine", f"agent/{slug(agent or 'brain')}"],
        "id": "routine-" + slug(title), "agent": agent or "brain", "skill": skill,
        "goal": wl(unwl(goal)) if goal else "", "schedule": schedule or "manual",
        "only_when": list(only_when or []), "max_per_day": int(max_per_day),
        "max_minutes": int(max_minutes), "notify": notify if notify in NOTIFY else "news",
        "enabled": bool(enabled), "status": status if status in ROUTINE_STATUSES else "draft",
        "created": now().date().isoformat(),
    }
    text = body.strip() or "Describe, in plain English, what this routine should do each time it runs."
    return fm, f"# {safe_name(title)}\n\n{text}\n"


def goal_note(agent: str, title: str, metric: str, target: int, by: str = "", routines: list[str] | None = None,
              body: str = "", metric_label: str = "") -> tuple[dict, str]:
    fm = {
        "schema": SCHEMA_GOAL, "type": "goal", "tags": ["goal", f"agent/{slug(agent or 'brain')}"],
        "id": "goal-" + slug(title), "agent": agent or "brain", "metric": metric,
        "metric_label": metric_label, "target": int(target), "by": by,
        "status": "active", "routines": [wl(unwl(r)) for r in (routines or [])],
        "stop_when_overdue": False, "stop_after_runs": 0, "created": now().date().isoformat(),
    }
    return fm, f"# {safe_name(title)}\n\n{body.strip() or 'Why this matters to me, in a sentence.'}\n"


# ------------------------------------------------------------------ seeding agent templates
def _manifest(b: Brain) -> tuple[pathlib.Path, dict]:
    p = b.state_dir() / MANIFEST
    try:
        return p, json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return p, {"schema": 1, "files": {}}


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def seed_text(b: Brain, kind: str, name: str, text: str) -> str:
    """Write a template note the user then owns: created if missing; refreshed only while the
    user hasn't edited it; an edited note gets the new version beside it as <name>.new.md."""
    d = b.dir(kind)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{safe_name(name)}.md"
    mp, man = _manifest(b)
    rel = b.rel(p) if p.exists() else f"{b.folder}/{SUBDIRS[kind]}/{p.name}"
    old = man["files"].get(rel)
    if not p.exists():
        p.write_text(text, encoding="utf-8")
        result = "created"
    else:
        live = _sha(p.read_text(encoding="utf-8", errors="replace"))
        if live == _sha(text):
            result = "same"
        elif old and live == old:
            p.write_text(text, encoding="utf-8")
            result = "updated"
        else:
            (d / f"{safe_name(name)}.new.md").write_text(text, encoding="utf-8")
            result = "kept-yours"
    if result != "kept-yours":
        man["files"][rel] = _sha(text)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    return result


def seed_from(b: Brain, src: pathlib.Path, agent: str) -> list[dict]:
    """Copy an agent's routine/goal templates (<src>/routines/*.md, <src>/goals/*.md) into the
    brain. Templates are written with enabled: false - turning a routine on is the user's call."""
    out = []
    for kind, sub in (("routines", "routines"), ("goals", "goals")):
        for t in sorted((src / sub).glob("*.md")) if (src / sub).is_dir() else []:
            fm, body = read_note(t)
            fm.setdefault("agent", agent)
            fm["agent"] = fm.get("agent") or agent
            if kind == "routines":
                fm["enabled"] = False
                fm.setdefault("schema", SCHEMA_ROUTINE)
                fm.setdefault("type", "routine")
            else:
                fm.setdefault("schema", SCHEMA_GOAL)
                fm.setdefault("type", "goal")
            res = seed_text(b, kind, t.stem, render_fm(fm) + "\n" + body.lstrip("\n"))
            out.append({"kind": kind, "name": t.stem, "result": res})
    return out


# ------------------------------------------------------------------ review queue (suggestions)
def _review(b: Brain) -> tuple[pathlib.Path, dict]:
    p = b.root / REVIEW_FILE
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    d.setdefault("schema", SCHEMA_REVIEW)
    d.setdefault("items", [])
    return p, d


def review_add(b: Brain, kind: str, title: str, notes: list[str], detail: str = "", source: str = "run") -> dict:
    p, d = _review(b)
    key = _sha(kind + "|" + "|".join(sorted(notes)))[:12]
    for it in d["items"]:
        # open, or already decided by the user: never ask the same question twice
        if it.get("key") == key:
            return it
    it = {"id": f"r-{now():%Y%m%d}-{key[:6]}", "key": key, "kind": kind, "title": clean_line(title),
          "notes": notes[:10], "detail": clean_line(detail), "source": source, "status": "open",
          "created": iso(now())}
    d["items"].append(it)
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    return it


def review_resolve(b: Brain, rid: str, resolution: str) -> dict | None:
    p, d = _review(b)
    for it in d["items"]:
        if it.get("id") == rid:
            it["status"] = "resolved"
            it["resolution"] = clean_line(resolution)
            it["resolved"] = iso(now())
            p.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
            return it
    return None


# ------------------------------------------------------------------ inbox (derived, never stored)
def inbox(b: Brain) -> list[dict]:
    """Everything that needs you, newest first: needs-you runs, reports with news, suggestions,
    memories to review, goals that changed. Read/dismiss marks live in state.json."""
    st = read_state(b).get("inbox") or {}
    items = []
    # A run that is parked (needs you / couldn't start / interrupted) and its report are ONE item:
    # the report's "Needs you" text rides on the run, so the inbox never says the same thing twice.
    reports = {}
    for n in list_notes(b, "reports"):
        fm = n["fm"]
        if fm.get("news") is not True:
            continue
        needs = re.search(r"^## Needs you\n(.*?)(?=^## |\n---|\Z)", n["body"], re.S | re.M)
        needs_txt = needs.group(1).strip() if needs else ""
        reports[n["name"]] = {"id": "report:" + n["name"], "kind": "report", "title": n["name"], "path": n["path"],
                              "agent": fm.get("agent"), "at": fm.get("date"), "status": fm.get("status"),
                              "run": unwl(fm.get("run")),
                              "needs_you": "" if needs_txt.startswith("- Nothing") else needs_txt[:400]}
    by_run = {r["run"]: r for r in reports.values() if r["run"]}
    parked = set()
    for n in list_notes(b, "activity"):
        fm = n["fm"]
        s = str(fm.get("status") or "")
        if s in ("awaiting", "preflight-failed", "interrupted"):
            kind = {"awaiting": "needs-you", "preflight-failed": "cant-run", "interrupted": "interrupted"}[s]
            it = {"id": "run:" + n["name"], "kind": kind, "title": n["name"], "path": n["path"],
                  "agent": fm.get("agent"), "at": fm.get("started"), "convo": fm.get("convo") or ""}
            rep = by_run.get(n["name"])
            if rep:
                parked.add(rep["title"])
                it["report"] = rep["path"]
                it["needs_you"] = rep["needs_you"]
            items.append(it)
    items.extend(r for name, r in reports.items() if name not in parked)
    _, rv = _review(b)
    for it in rv["items"]:
        if it.get("status") == "open":
            items.append({"id": "review:" + it["id"], "kind": "suggestion", "title": it["title"],
                          "notes": it.get("notes"), "detail": it.get("detail"), "at": it.get("created"),
                          "review_id": it["id"], "review_kind": it.get("kind")})
    pend = _pending_memories(b)
    if pend:
        items.append({"id": "memory:pending", "kind": "memory", "title": f"{pend} memor{'y' if pend == 1 else 'ies'} to review",
                      "count": pend, "at": None})
    out = []
    for it in items:
        mark = st.get(it["id"]) or {}
        if mark.get("dismissed"):
            continue
        it["read"] = bool(mark.get("read"))
        out.append(it)
    out.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    return out


def _pending_memories(b: Brain) -> int:
    store = b.root / "_memory" / ".store"
    if not store.is_dir():
        return 0
    status: dict[str, str] = {}
    for f in store.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            iid = ev.get("id")
            if not iid:
                continue
            if ev.get("op") == "add":
                status[iid] = str((ev.get("item") or {}).get("status") or "")
            elif ev.get("op") in ("approve", "reject", "retire", "forget", "status"):
                status[iid] = str(ev.get("status") or ev.get("op"))
    return sum(1 for s in status.values() if s == "pending")


def inbox_mark(b: Brain, iid: str, read: bool = False, dismiss: bool = False) -> None:
    with State(b) as s:
        m = s.data["inbox"].setdefault(iid, {})
        if read:
            m["read"] = True
        if dismiss:
            m["dismissed"] = True
        s.save()


# ------------------------------------------------------------------ dry run (--provider none)
def dry_run(b: Brain, routine: str) -> dict:
    """The whole lifecycle with no model: check -> conditions -> open -> steps -> handoff -> close.
    Deterministic and offline, which is what the tests and `sbl eval --harness` exercise."""
    rp = find_note(b, "routines", routine)
    if not rp:
        raise SystemExit(f"harness: no routine '{routine}'")
    fm, body = read_note(rp)
    fails = preflight(b, fm)
    run = run_open(b, str(fm.get("agent") or "brain"), routine=rp.stem, goal=unwl(fm.get("goal")),
                   trigger="manual", title=rp.stem)
    run_append(run, "dry run (--provider none): no model is called")
    if fails:
        for f in fails:
            run_append(run, f"check failed: {f['check']} — {f['why']}")
        return run_close(b, run, "preflight-failed", fails=fails)
    ok, reasons = eval_when(b, fm, rp.stem)
    for r in reasons:
        run_append(run, "condition " + r)
    if not ok:
        return run_close(b, run, "skipped", stop_reason="Its conditions weren't met: " + reasons[-1].lstrip("✗ "))
    hb = handoff_block(b, routine=rp.stem)
    run_append(run, "picked up the last report" if hb else "no previous report — starting fresh")
    run_append(run, f"would run skill `{fm.get('skill') or '(the agent’s entry skill)'}`")
    final = ("Dry run complete.\n```report\n" + json.dumps({
        "done": [{"text": "Checked the routine end to end without calling a model",
                  "evidence": f"`{b.rel(rp)}`"}],
        "not_done": [], "next": [{"text": "Turn the routine on to run it for real"}],
        "needs_you": [], "news": False}) + "\n```")
    return run_close(b, run, "done", final_text=final)


# ------------------------------------------------------------------ CLI
def _out(obj, as_json: bool):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
    elif isinstance(obj, list):
        for x in obj:
            print(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            print(f"{k}: {v}")
    else:
        print(obj)


def main(argv=None) -> int:
    global _NOW
    ap = argparse.ArgumentParser(prog="harness.py", description="Second Brain Harness (goals, routines, reports, activity)")
    ap.add_argument("--brain")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--now", help="ISO datetime (tests)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("where")
    g.add_argument("--agent", default="", help="also list the folders a routine of this agent may not write")
    g = sub.add_parser("list")
    g.add_argument("kind", choices=KINDS)
    g.add_argument("--agent", default="")
    g.add_argument("--limit", type=int, default=0)
    g = sub.add_parser("show")
    g.add_argument("note")
    g = sub.add_parser("set")
    g.add_argument("note")
    g.add_argument("key")
    g.add_argument("value")
    g = sub.add_parser("seed")
    g.add_argument("--from", dest="src", required=True)
    g.add_argument("--agent", required=True)
    g = sub.add_parser("routine-new")
    for a in ("--agent", "--title"):
        g.add_argument(a, required=True)
    g.add_argument("--skill", default="")
    g.add_argument("--schedule", default="manual")
    g.add_argument("--goal", default="")
    g.add_argument("--only-when", action="append", default=[])
    g.add_argument("--max-per-day", type=int, default=DEFAULT_MAX_PER_DAY)
    g.add_argument("--max-minutes", type=int, default=DEFAULT_MAX_MINUTES)
    g.add_argument("--notify", default="news", choices=NOTIFY)
    g.add_argument("--enabled", action="store_true")
    g.add_argument("--body", default="")
    g = sub.add_parser("goal-new")
    for a in ("--agent", "--title", "--metric"):
        g.add_argument(a, required=True)
    g.add_argument("--target", type=int, required=True)
    g.add_argument("--by", default="")
    g.add_argument("--routine", action="append", default=[])
    g.add_argument("--metric-label", default="")
    g.add_argument("--body", default="")
    for name in ("preflight", "when", "verify"):
        g = sub.add_parser(name)
        g.add_argument("note")
    g = sub.add_parser("due")
    g.add_argument("--max-per-day", type=int, default=3)
    g = sub.add_parser("fired")
    g.add_argument("routine")
    g.add_argument("--slot", default="")
    g.add_argument("--status", default="")
    g = sub.add_parser("run-open")
    g.add_argument("--agent", default="brain")
    g.add_argument("--routine", default="")
    g.add_argument("--goal", default="")
    g.add_argument("--trigger", default="manual", choices=TRIGGERS)
    g.add_argument("--convo", default="")
    g.add_argument("--title", default="")
    g.add_argument("--reuse", action="store_true", help="continue this conversation's Activity note")
    g = sub.add_parser("run-append")
    g.add_argument("run")
    g.add_argument("--line", required=True)
    g = sub.add_parser("run-close")
    g.add_argument("run")
    g.add_argument("--status", required=True, choices=RUN_STATUSES)
    g.add_argument("--final-file", default="")
    g.add_argument("--asks-file", default="")
    g.add_argument("--wrote", default="")
    g.add_argument("--stop-reason", default="")
    g.add_argument("--fails-json", default="")
    g = sub.add_parser("last-report")
    g.add_argument("--routine", default="")
    g.add_argument("--agent", default="")
    g.add_argument("--block", action="store_true")
    g = sub.add_parser("goal-progress")
    g.add_argument("goal", nargs="?", default="")
    g.add_argument("--check", action="store_true")
    g = sub.add_parser("inbox")
    g.add_argument("--read", default="")
    g.add_argument("--dismiss", default="")
    g = sub.add_parser("review")
    rs = g.add_subparsers(dest="rcmd", required=True)
    x = rs.add_parser("add")
    x.add_argument("--kind", required=True, choices=("duplicate", "conflict", "orphan", "promote", "unexpected"))
    x.add_argument("--title", required=True)
    x.add_argument("--note", action="append", default=[])
    x.add_argument("--detail", default="")
    x.add_argument("--source", default="run")
    rs.add_parser("list")
    x = rs.add_parser("resolve")
    x.add_argument("id")
    x.add_argument("--resolution", required=True)
    g = sub.add_parser("run")
    g.add_argument("routine")
    g.add_argument("--provider", default="none", choices=("none",))
    g = sub.add_parser("describe-schedule")
    g.add_argument("schedule")
    # global flags may come before OR after the subcommand (`harness.py due --json`)
    argv = list(sys.argv[1:] if argv is None else argv)
    glob: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(argv):
        t = argv[i]
        if t == "--json":
            glob.append(t)
        elif t in ("--brain", "--now") and i + 1 < len(argv):
            glob += [t, argv[i + 1]]
            i += 1
        elif t.startswith("--brain=") or t.startswith("--now="):
            glob.append(t)
        else:
            rest.append(t)
        i += 1
    a = ap.parse_args(glob + rest)
    if a.now:
        _NOW = _parse_dt(a.now)
    j = a.json

    if a.cmd == "describe-schedule":
        spec = parse_schedule(a.schedule)
        _out({"valid": spec is not None, "describe": describe_schedule(a.schedule),
              "next": iso(next_slot(spec, now())) if spec and next_slot(spec, now()) else None}, j)
        return 0 if spec is not None else 2
    b = Brain(a.brain)

    if a.cmd == "where":
        _out({"brain": str(b.root), "folder": b.folder,
              **{k: b.rel(b.dir(k)) if b.dir(k).exists() else f"{b.folder}/{v}" for k, v in SUBDIRS.items()},
              **({"protected": protected_folders(b, a.agent)} if a.agent else {})}, j)
    elif a.cmd == "list":
        notes = list_notes(b, a.kind)
        if a.agent:
            notes = [n for n in notes if str(n["fm"].get("agent") or "") == a.agent]
        if a.kind in ("activity", "reports"):
            notes.sort(key=lambda n: n["name"], reverse=True)
        if a.limit:
            notes = notes[:a.limit]
        for n in notes:
            n.pop("body", None)
            if a.kind == "routines":
                n["describe"] = describe_schedule(n["fm"].get("schedule"))
        _out(notes, j)
    elif a.cmd == "show":
        p = find_note(b, "routines", a.note) or find_note(b, "goals", a.note) or find_note(b, "reports", a.note) \
            or find_note(b, "activity", a.note)
        if not p:
            print(f"harness: no note '{a.note}'", file=sys.stderr)
            return 2
        fm, body = read_note(p)
        _out({"path": b.rel(p), "fm": fm, "body": body}, j)
    elif a.cmd == "set":
        p = find_note(b, "routines", a.note) or find_note(b, "goals", a.note)
        if not p:
            print(f"harness: no routine or goal '{a.note}'", file=sys.stderr)
            return 2
        allowed = {"enabled", "schedule", "status", "max_per_day", "max_minutes", "notify", "goal", "target",
                   "by", "skill", "validated_by", "validated_on", "stop_when_overdue", "stop_after_runs", "progress"}
        if a.key not in allowed:
            print(f"harness: '{a.key}' can't be set here", file=sys.stderr)
            return 2
        val = _unscalar(a.value)
        if a.key == "schedule" and parse_schedule(a.value) is None:
            print("harness: unreadable schedule", file=sys.stderr)
            return 2
        _out({"path": b.rel(p), "fm": set_fm(p, **{a.key: val})}, j)
    elif a.cmd == "seed":
        _out(seed_from(b, pathlib.Path(a.src).expanduser(), a.agent), j)
    elif a.cmd == "routine-new":
        if parse_schedule(a.schedule) is None:
            print("harness: unreadable schedule", file=sys.stderr)
            return 2
        fm, body = routine_note(a.agent, a.title, a.skill, a.schedule, a.goal, a.only_when, a.max_per_day,
                                a.max_minutes, a.notify, a.enabled, body=a.body)
        p = unique_path(b.dir("routines"), safe_name(a.title))
        write_note(p, fm, body)
        if a.goal:
            gp = find_note(b, "goals", a.goal)
            if gp:
                gfm, _ = read_note(gp)
                rl = list(gfm.get("routines") or [])
                if wl(p.stem) not in rl:
                    set_fm(gp, routines=rl + [wl(p.stem)])
        _out({"path": b.rel(p), "name": p.stem}, j)
    elif a.cmd == "goal-new":
        fm, body = goal_note(a.agent, a.title, a.metric, a.target, a.by, a.routine, a.body, a.metric_label)
        p = unique_path(b.dir("goals"), safe_name(a.title))
        write_note(p, fm, body)
        _out({"path": b.rel(p), "name": p.stem}, j)
    elif a.cmd == "preflight":
        p = find_note(b, "routines", a.note)
        fm = read_note(p)[0] if p else {"agent": a.note}
        fails = preflight(b, fm)
        _out({"ok": not fails, "fails": fails}, j)
        return 0 if not fails else 3
    elif a.cmd == "when":
        p = find_note(b, "routines", a.note)
        if not p:
            return 2
        ok, reasons = eval_when(b, read_note(p)[0], p.stem)
        _out({"ok": ok, "reasons": reasons}, j)
        return 0 if ok else 1
    elif a.cmd == "due":
        _out(due(b, a.max_per_day), j)
    elif a.cmd == "fired":
        mark_fired(b, a.routine, a.slot, a.status)
        _out({"ok": True}, j)
    elif a.cmd == "run-open":
        p = run_open(b, a.agent, a.routine, a.goal, a.trigger, a.convo, a.title, a.reuse)
        _out({"run": b.rel(p), "name": p.stem}, j)
    elif a.cmd == "run-append":
        run_append(b.abs(a.run), a.line)
        _out({"ok": True}, j)
    elif a.cmd == "run-close":
        final = pathlib.Path(a.final_file).read_text(encoding="utf-8", errors="replace") if a.final_file else ""
        asks = json.loads(pathlib.Path(a.asks_file).read_text(encoding="utf-8")) if a.asks_file else []
        fails = json.loads(a.fails_json) if a.fails_json else []
        wrote = [w for w in a.wrote.split("\n") if w.strip()] if a.wrote else []
        _out(run_close(b, b.abs(a.run), a.status, final, wrote, asks, a.stop_reason, fails), j)
    elif a.cmd == "last-report":
        if a.block:
            print(handoff_block(b, a.routine, a.agent))
        else:
            r = last_report(b, a.routine, a.agent)
            _out(r or {}, j)
    elif a.cmd == "verify":
        p = b.abs(a.note) if a.note.endswith(".md") else find_note(b, "reports", a.note)
        if not p:
            return 2
        fm, body = read_note(p)
        m = re.search(r"^## Done\n(.*?)(?=^## |\Z)", body, re.S | re.M)
        items = []
        for ln in (m.group(1) if m else "").splitlines():
            mm = re.match(r"^- (.*?)(?: — _evidence: (.*)_)?$", ln.strip())
            if mm and not mm.group(1).startswith("Nothing"):
                txt = re.sub(r"( ✓| \(couldn't verify\))$", "", mm.group(1))
                items.append({"text": txt, "evidence": mm.group(2) or ""})
        _out(verify_items(b, items), j)
    elif a.cmd == "goal-progress":
        goals = [find_note(b, "goals", a.goal)] if a.goal else [b.abs(n["path"]) for n in list_notes(b, "goals")]
        res = [goal_check(b, g) if a.check else goal_progress(b, g) for g in goals if g]
        _out(res if not a.goal else (res[0] if res else {}), j)
    elif a.cmd == "inbox":
        if a.read or a.dismiss:
            inbox_mark(b, a.read or a.dismiss, read=bool(a.read), dismiss=bool(a.dismiss))
        _out(inbox(b), j)
    elif a.cmd == "review":
        if a.rcmd == "add":
            _out(review_add(b, a.kind, a.title, a.note, a.detail, a.source), j)
        elif a.rcmd == "list":
            _out([x for x in _review(b)[1]["items"] if x.get("status") == "open"], j)
        else:
            r = review_resolve(b, a.id, a.resolution)
            if not r:
                return 2
            _out(r, j)
    elif a.cmd == "run":
        _out(dry_run(b, a.routine), j)
    return 0


if __name__ == "__main__":
    sys.exit(main())
