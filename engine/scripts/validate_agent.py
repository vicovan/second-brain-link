#!/usr/bin/env python3
"""validate_agent.py - is this plugin a contract-complete Second Brain agent (sbl-agent/1)?

Engine-side (not shipped in plugins). Run by `tests/run.py` on every plugin and by
`packaging/build_plugin.py` before it packages one. The TypeScript twin in Studio
(`discover.ts` / `main/agents.ts`) reads the same contract; the two must agree on these rules.
Reference: engine/references/agent-contract.md.

    python3 validate_agent.py plugins/<name> [--json]        exit 1 and list the problems
    python3 validate_agent.py --selftest
"""
from __future__ import annotations

import argparse
import filecmp
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import pipeline_doc as pdoc  # noqa: E402

SCHEMA = "sbl-agent/1"
CANVASES = ("lines", "map", "none")
INSPECTOR_KINDS = ("job", "account", "target", "trip", "place", "generic")
WEIGHTS = ("heavy", "light")
PREFLIGHTS = ("profile_present", "chrome_connected", "ai_signed_in", "brain_built")
SUGGEST_STAGES = ("setup", "today", "do", "track")
LAYOUT_KEYS = ("dashboard", "kpi", "lessons", "profile", "reports", "items", "work")
# shared libraries every agent ships byte-identical with the engine's copy
SHARED_PY = ("memory.py", "harness.py", "pipeline_doc.py", "daily.py", "ledger_base.py", "kpi.py",
             "optimize.py", "explore.py", "report.py", "stages.py")
SHARED_MD = ("memory-protocol.md", "browser-setup.md")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
BAD_PATH = re.compile(r"(^|/)\.\.?(/|$)")


def _read_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as e:
        return None, str(e)


def _fm(text):
    m = re.match(r"\A﻿?---\n(.*?)\n---", text, re.S)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
            if mm:
                out[mm.group(1)] = mm.group(2).strip().strip('"')
    return out


def validate(root, repo=None):
    """Returns (problems, warnings)."""
    root = pathlib.Path(root)
    P, W = [], []
    meta_p = root / ".claude-plugin" / "plugin.json"
    meta, err = _read_json(meta_p) if meta_p.is_file() else (None, "missing")
    if not meta:
        P.append(f"plugin.json: {err}")
        meta = {}
    sj_p = root / "studio.json"
    c, err = _read_json(sj_p) if sj_p.is_file() else (None, "missing")
    if not c:
        P.append(f"studio.json: {err}")
        return P, W
    if c.get("schema") != SCHEMA:
        P.append(f"studio.json: schema must be {SCHEMA}")
    cid = str(c.get("id") or "")
    if not ID_RE.match(cid):
        P.append("studio.json: id missing or not a slug")
    if meta and meta.get("name") != cid:
        P.append(f"plugin.json name {meta.get('name')!r} != studio.json id {cid!r}")
    for k in ("label", "icon", "blurb", "grounding", "entrySkill"):
        if not str(c.get(k) or "").strip():
            P.append(f"studio.json: {k} missing")
    if c.get("grounding") and not (root / str(c["grounding"])).is_file():
        P.append(f"grounding file missing: {c['grounding']}")
    skills = {p.parent.name for p in root.glob("skills/*/SKILL.md")}
    if c.get("entrySkill") and c["entrySkill"] not in skills:
        P.append(f"entrySkill {c['entrySkill']!r} has no skills/<name>/SKILL.md")
    for k in ("subjects", "providers"):
        v = c.get(k)
        if not isinstance(v, list) or not v:
            P.append(f"studio.json: {k} must be a non-empty list")
    if not isinstance(c.get("network"), dict) or "declared" not in c["network"]:
        P.append("studio.json: network {declared, what} missing")
    elif c["network"].get("declared") and not str(c["network"].get("what") or "").strip():
        P.append("studio.json: network.what must say what the network is used for")
    layer = str(c.get("layer") or "")
    if not layer or BAD_PATH.search(layer) or "/" in layer:
        P.append("studio.json: layer must be one folder name")
    lay = c.get("layout")
    if not isinstance(lay, dict):
        P.append("studio.json: layout block missing")
        lay = {}
    for k in LAYOUT_KEYS:
        if k not in lay:
            P.append(f"layout.{k} missing")
    for k in ("items", "work"):
        if k in lay and not isinstance(lay[k], dict):
            P.append(f"layout.{k} must be an object {{kind: folder}}")
    for k in ("dashboard", "kpi", "lessons"):
        if k in lay and not str(lay[k]).endswith(".md"):
            P.append(f"layout.{k} must be a .md file name")
    home = str(c.get("homeNote") or "")
    if not home.startswith(layer + "/"):
        P.append("homeNote must sit under the layer")
    if "{date}" not in home:
        P.append("homeNote must be the dated daily note ({date})")
    if not str(c.get("homeNoteFallback") or "").startswith(layer + "/"):
        P.append("homeNoteFallback must sit under the layer")
    if c.get("plan") and not str(c["plan"]).startswith(layer + "/"):
        P.append("plan must sit under the layer")
    d = c.get("daily")
    if not isinstance(d, dict):
        P.append("daily block missing")
        d = {}
    if "{date}" not in str(d.get("note") or ""):
        P.append("daily.note must contain {date}")
    if d.get("weekly") and "{date}" not in str(d["weekly"]):
        P.append("daily.weekly must contain {date}")
    if not isinstance(d.get("steps"), list) or not d.get("steps"):
        P.append("daily.steps must list the daily's toggles")
    if home and d.get("note") and pathlib.Path(home).stem != str(d["note"]):
        P.append("homeNote and daily.note must name the same note")
    pipe = str(c.get("pipeline") or "")
    if not pipe.startswith(layer + "/") or not pipe.endswith(".json"):
        P.append("pipeline must be a .json file under the layer")
    r = c.get("render") if isinstance(c.get("render"), dict) else {}
    rcmd = str(r.get("cmd") or "")
    if not rcmd:
        P.append("render.cmd missing")
    else:
        name = rcmd.split()[0]
        if not list(root.glob("skills/*/scripts/" + name)):
            P.append(f"render script not shipped: {name}")
    if c.get("home") and str((c["home"] or {}).get("cmd") or ""):
        name = str(c["home"]["cmd"]).split()[0]
        if not list(root.glob("skills/*/scripts/" + name)):
            P.append(f"home script not shipped: {name}")
    if c.get("canvas") not in CANVASES:
        P.append(f"canvas must be one of {CANVASES}")
    if c.get("canvas") == "map":
        if not str(c.get("canvasData") or "").startswith(layer + "/"):
            P.append("a map agent needs canvasData under the layer")
        for x in c.get("canvasLayers") or []:
            if not str(x).startswith(layer + "/"):
                P.append(f"canvasLayers entry outside the layer: {x}")
    # funnels + floor through pipeline_doc's own rules
    funnels = c.get("funnels")
    if not isinstance(funnels, list) or not funnels:
        P.append("funnels: at least one funnel")
        funnels = []
    doc = pdoc.new(cid or "x", str(c.get("label") or "x"), str(c.get("color") or "#000"))
    norm = []
    for f in funnels:
        if not isinstance(f, dict):
            P.append("funnels: each entry must be an object")
            continue
        stages = []
        for s in f.get("stages") or []:
            if not isinstance(s, dict) or not SID_RE.match(str(s.get("id") or "")):
                P.append(f"funnel {f.get('id')}: stage id {s.get('id') if isinstance(s, dict) else s!r} must be a snake_case id")
                continue
            lab = str(s.get("label") or s["id"].replace("_", " ").title())
            if len(lab.split()) > 3:
                W.append(f"funnel {f.get('id')}: stage label {lab!r} is long (R11 asks one or two words)")
            stages.append(pdoc.stage(s["id"], lab, s.get("role", "open"), next=s.get("next") or [], gate=s.get("gate", "none")))
        if not stages:
            P.append(f"funnel {f.get('id')}: no stages")
        norm.append(pdoc.funnel(str(f.get("id") or ""), str(f.get("label") or ""), str(f.get("item") or ""), str(f.get("success") or ""), stages, f.get("success2")))
    doc["funnels"] = norm
    if isinstance(c.get("floor"), list):
        doc["floor"] = [pdoc.floor_group(str(g.get("id") or ""), str(g.get("label") or ""), list(g.get("stages") or []), g.get("funnel")) for g in c["floor"] if isinstance(g, dict)]
    elif funnels:
        W.append("floor missing: the Floor falls back to the first eight open/positive stages")
    for x in pdoc.check(doc):
        if "schema" not in x:
            P.append("funnels/floor: " + x)
    if isinstance(c.get("floor"), list) and len(c["floor"]) > pdoc.MAX_FLOOR:
        P.append(f"floor has {len(c['floor'])} groups (max {pdoc.MAX_FLOOR})")
    # goals, outcomes, throughput
    outcomes = c.get("outcomes") if isinstance(c.get("outcomes"), dict) else {}
    if not outcomes:
        P.append("outcomes block missing")
    for k, o in outcomes.items():
        if not isinstance(o, dict) or not str(o.get("cmd") or ""):
            P.append(f"outcomes.{k}: needs a cmd")
            continue
        name = str(o["cmd"]).split()[0]
        if not list(root.glob("skills/*/scripts/" + name)):
            P.append(f"outcomes.{k}: script not shipped: {name}")
    goals = c.get("goals")
    if not isinstance(goals, list) or not goals:
        P.append("goals: at least one per funnel")
        goals = []
    for g in goals:
        if not isinstance(g, dict) or not g.get("template") or not g.get("metric"):
            P.append("goals: each needs template + metric")
            continue
        if g["metric"] not in outcomes:
            P.append(f"goal {g['template']!r}: metric {g['metric']!r} is not an outcome counter")
        if not isinstance(g.get("target"), int) or g["target"] <= 0:
            P.append(f"goal {g['template']!r}: target must be a positive integer")
    if len(goals) < len(funnels):
        P.append(f"goals: {len(goals)} for {len(funnels)} funnels (one per funnel)")
    tp = c.get("throughput")
    if not isinstance(tp, dict) or not tp.get("cmd") or not tp.get("label"):
        P.append("throughput {label, cmd} missing")
    elif not list(root.glob("skills/*/scripts/" + str(tp["cmd"]).split()[0])):
        P.append(f"throughput script not shipped: {tp['cmd']}")
    # routines + templates
    tdir = root / str(c.get("templates") or "harness")
    routines = c.get("routines")
    if not isinstance(routines, list) or not routines:
        P.append("routines: declare the daily (and the weekly)")
        routines = []
    kinds = [str(r.get("kind")) for r in routines if isinstance(r, dict)]
    if "daily" not in kinds:
        P.append("routines: no daily routine declared")
    tmpl_routines = {p.stem: _fm(p.read_text(encoding="utf-8")) for p in tdir.glob("routines/*.md")} if tdir.is_dir() else {}
    tmpl_goals = {p.stem: _fm(p.read_text(encoding="utf-8")) for p in tdir.glob("goals/*.md")} if tdir.is_dir() else {}
    for r_ in routines:
        if not isinstance(r_, dict) or not r_.get("template"):
            P.append("routines: each needs a template name")
            continue
        fm = tmpl_routines.get(str(r_["template"]))
        if fm is None:
            P.append(f"routine template missing: {tdir.name}/routines/{r_['template']}.md")
            continue
        if fm.get("schema") != "sbl-routine/1" or not fm.get("schedule") or fm.get("schedule") == "manual":
            P.append(f"routine template {r_['template']!r}: needs schema sbl-routine/1 and a real schedule")
        if fm.get("enabled") not in ("false", "False", ""):
            P.append(f"routine template {r_['template']!r}: ships enabled; templates seed OFF")
        if fm.get("skill") and fm["skill"] not in skills:
            P.append(f"routine template {r_['template']!r}: skill {fm['skill']!r} is not shipped")
        if r_.get("kind") == "daily" and not re.match(r"^(Daily |Today |This weekend)", str(r_["template"])):
            W.append(f"routine {r_['template']!r}: R5 names a daily 'Daily <what>' (Travel's own names are the exception)")
    for g in goals:
        if isinstance(g, dict) and g.get("template") and str(g["template"]) not in tmpl_goals:
            P.append(f"goal template missing: {tdir.name}/goals/{g['template']}.md")
    for name, fm in tmpl_goals.items():
        if fm.get("metric") and fm["metric"] not in outcomes and fm["metric"] != "manual":
            P.append(f"goal template {name!r}: metric {fm['metric']!r} is not an outcome counter")
    for name, fm in tmpl_routines.items():
        g = fm.get("goal") or ""
        if g and g.strip("[]\"") not in tmpl_goals:
            P.append(f"routine template {name!r}: goal {g} has no goal template")
    # optimize, concurrency, inspector, persona, settings, requires, preflight, suggestions
    opt = c.get("optimize")
    if not isinstance(opt, dict):
        P.append("optimize block missing")
    else:
        for k in ("sources", "scoring"):
            if not str(opt.get(k) or "").startswith("profile/"):
                P.append(f"optimize.{k} must be a file under profile/")
        if not isinstance(opt.get("signals"), list):
            P.append("optimize.signals must be a list")
        if not isinstance(opt.get("explore"), (int, float)) or not 0 <= float(opt.get("explore", -1)) <= 1:
            P.append("optimize.explore must be a share between 0 and 1")
    cc = c.get("concurrency")
    if not isinstance(cc, dict) or cc.get("weight") not in WEIGHTS:
        P.append("concurrency {weight: heavy|light, browser, parallel_items} missing")
    insp = c.get("inspector")
    if not isinstance(insp, dict):
        P.append("inspector {item kind: layout} missing")
    else:
        kinds_declared = {str(f.get("item")) for f in funnels if isinstance(f, dict)}
        for k, v in insp.items():
            if v not in INSPECTOR_KINDS:
                P.append(f"inspector.{k}: layout {v!r} not one of {INSPECTOR_KINDS}")
        for k in kinds_declared:
            if k not in insp:
                P.append(f"inspector: no layout for item kind {k!r}")
    if not str(c.get("persona") or ""):
        P.append("persona missing")
    st = c.get("settings")
    if not isinstance(st, dict) or st.get("daily") is not True:
        P.append("settings.daily must be true (the generic Daily tab)")
    req = c.get("requires") if isinstance(c.get("requires"), dict) else {}
    if not str(req.get("profile") or "").startswith(layer + "/"):
        P.append("requires.profile must sit under the layer")
    if req.get("onboardSkill") not in skills:
        P.append(f"requires.onboardSkill {req.get('onboardSkill')!r} is not a shipped skill")
    for x in c.get("preflight") or []:
        if x not in PREFLIGHTS:
            P.append(f"preflight {x!r} unknown")
    sug = c.get("suggestions")
    if not isinstance(sug, list) or not sug:
        P.append("suggestions missing")
    else:
        for s in sug:
            if not isinstance(s, dict) or not s.get("t") or not s.get("q"):
                P.append("suggestions: each needs t + q")
            elif s.get("stage") not in (None, *SUGGEST_STAGES):
                P.append(f"suggestion {s.get('t')!r}: stage {s.get('stage')!r}")
        if not any(isinstance(s, dict) and s.get("stage") == "setup" for s in sug):
            W.append("suggestions: no setup card")
    if c.get("color") and not re.match(r"^#[0-9a-fA-F]{6}$", str(c["color"])):
        P.append("color must be #rrggbb")
    # the shared libraries
    for name in SHARED_PY:
        copies = list(root.glob("skills/*/scripts/" + name)) + list(root.glob("scripts/" + name))
        if not copies:
            P.append(f"shared library not shipped: {name}")
            continue
        if len(copies) > 1:
            P.append(f"shared library shipped twice: {name}")
        eng = HERE / name
        if eng.is_file() and not filecmp.cmp(eng, copies[0], shallow=False):
            P.append(f"{name} differs from the engine's copy")
    for name in SHARED_MD:
        copies = list(root.glob("skills/*/references/" + name)) + list(root.glob("references/" + name))
        if not copies:
            P.append(f"shared reference not shipped: {name}")
        elif repo:
            canon = pathlib.Path(repo) / "plugins" / "job-search" / ("skills/job-apply/references/" + name)
            if canon.is_file() and canon.resolve() != copies[0].resolve() and not filecmp.cmp(canon, copies[0], shallow=False):
                P.append(f"{name} differs from the canonical copy")
    # SKILL.md descriptions (the packager's rule)
    for sk in root.glob("skills/*/SKILL.md"):
        fm = _fm(sk.read_text(encoding="utf-8"))
        desc = fm.get("description") or ""
        if not desc:
            P.append(f"{sk.parent.name}: SKILL.md has no description")
        elif len(desc) >= 1024:
            P.append(f"{sk.parent.name}: description must stay under 1024 characters")
        elif ": " in desc:
            P.append(f"{sk.parent.name}: description has a bare colon")
    if not (root / "README.md").is_file():
        P.append("README.md missing")
    P += check_paths(root)
    if (c.get("network") or {}).get("declared") and not (root / "docs" / "safety.md").is_file():
        W.append("docs/safety.md missing (expected where network is used)")
    return P, W


SCRIPT_REF = re.compile(r"(?:\$S/|\$\{S\}/|python3 \$S/|/scripts/)([a-z][a-z0-9_]*\.py)")
ROOT_REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)")


def check_paths(root):
    """Every script and path a skill, the grounding, a command, a reference or studio.json names
    must exist in the plugin - the installed copy may be a symlink to a checkout, so a dangling
    reference is live in the user's Studio the moment it is saved."""
    root = pathlib.Path(root)
    P = []
    scripts = {p.name for p in root.glob("skills/*/scripts/*.py")} | {p.name for p in root.glob("scripts/*.py")}
    docs = list(root.glob("skills/*/SKILL.md")) + list(root.glob("studio/*.md")) + list(root.glob("commands/*.md")) \
        + list(root.glob("skills/*/references/*.md")) + [root / "README.md"] + list(root.glob("providers/*/SKILL.md"))
    for md in docs:
        if not md.is_file():
            continue
        try:
            txt = md.read_text(encoding="utf-8")
        except OSError:
            continue
        rel_md = md.relative_to(root).as_posix()
        for m in ROOT_REF.finditer(txt):
            rel = m.group(1).rstrip("/").rstrip(".,;:)`'\"")
            if "<" in rel or "…" in rel or "*" in rel:
                continue
            if not (root / rel).exists() and not list(root.glob(rel)):
                P.append(f"{rel_md}: references ${{CLAUDE_PLUGIN_ROOT}}/{rel}, which does not exist")
        for m in SCRIPT_REF.finditer(txt):
            if m.group(1) not in scripts:
                P.append(f"{rel_md}: names script {m.group(1)}, which this plugin does not ship")
    sj = root / "studio.json"
    try:
        c = json.loads(sj.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return P
    cmds = [str((c.get("render") or {}).get("cmd") or ""), str((c.get("home") or {}).get("cmd") or ""), str((c.get("throughput") or {}).get("cmd") or "")]
    cmds += [str(o.get("cmd") or "") for o in (c.get("outcomes") or {}).values() if isinstance(o, dict)]
    cmds += [str(x) for x in ((c.get("daily") or {}).get("orient") or [])]
    for cmd in cmds:
        name = cmd.split()[0] if cmd else ""
        if name and name not in scripts:
            P.append(f"studio.json: command {cmd!r} names a script this plugin does not ship")
    for tp in root.glob("harness/routines/*.md"):
        for m in re.finditer(r"cmd:\s*([a-z][a-z0-9_]*\.py)", tp.read_text(encoding="utf-8")):
            if m.group(1) not in scripts:
                P.append(f"{tp.relative_to(root).as_posix()}: only_when names {m.group(1)}, which this plugin does not ship")
    return sorted(set(P))


def _selftest():
    import tempfile  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as t:
        P, W = validate(t)
        assert any("studio.json" in x for x in P)
        d = pathlib.Path(t) / "skills" / "x"
        (d / "scripts").mkdir(parents=True)
        (d / "scripts" / "ok.py").write_text("", encoding="utf-8")
        (d / "SKILL.md").write_text("python3 ${CLAUDE_PLUGIN_ROOT}/skills/x/scripts/ok.py\npython3 $S/gone.py\n${CLAUDE_PLUGIN_ROOT}/skills/nope/SKILL.md\n", encoding="utf-8")
        probs = check_paths(t)
        assert any("gone.py" in x for x in probs) and any("skills/nope/SKILL.md" in x for x in probs) and not any("ok.py" in x for x in probs), probs
    print("validate_agent: selftest ok")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selftest"]:
        return _selftest()
    ap = argparse.ArgumentParser(prog="validate_agent.py")
    ap.add_argument("plugin")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--repo", default="")
    a = ap.parse_args(argv)
    root = pathlib.Path(a.plugin)
    repo = a.repo or (HERE.parent.parent if (HERE.parent.parent / "plugins").is_dir() else "")
    P, W = validate(root, repo)
    if a.json:
        print(json.dumps({"ok": not P, "problems": P, "warnings": W}, indent=1))
    else:
        for x in P:
            print("  ! " + x)
        for x in W:
            print("  ~ " + x)
        print(f"{root.name}: " + ("ok" if not P else f"{len(P)} problem(s)") + (f", {len(W)} warning(s)" if W else ""))
    return 0 if not P else 1


if __name__ == "__main__":
    sys.exit(main())
