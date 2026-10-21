#!/usr/bin/env python3
"""new_agent.py - scaffold a contract-complete Second Brain agent from plugins/_template/.

    python3 packaging/new_agent.py --id briefing --label "Briefing Agent" --layer 49-briefs \
        --funnel "meetings=upcoming>briefed>held*;cancelled~" --what briefing \
        [--goal "Walk in prepared" --target 10] [--icon calendar] [--color "#1f6feb"] \
        [--network "reads the user's own calendar export; no web"] [--browser] [--out plugins/]

The result passes `validate_agent.py` and the daily dry-run with STUB domain logic
(sources.py / score.py / actions.py print what they would do and never reach the network).
What a new agent then supplies: its discovery, its rubric, its actions, the words of its
skills, the profile its onboarding writes. The loop, the contract, the renderer, the ledger,
the shared libraries (copied byte-identical from engine/scripts/) are done.

Funnel grammar (repeat --funnel for a second item kind):
    <id>[:<Label>:<item>]=<open>[>open...][*success]... ;<closed>[-|~]...
    `*` after a stage = positive (the first one is the success stage), `-` = negative,
    `~` = parked, `>` chains the open stages, `;` separates the side stages.
    "meetings=upcoming>briefed>held*;cancelled~"  → open upcoming → briefed → held (success); cancelled parked
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
TEMPLATE = REPO / "plugins" / "_template"
ENGINE = REPO / "engine" / "scripts"
SHARED_PY = ("memory.py", "harness.py", "pipeline_doc.py", "daily.py", "ledger_base.py", "kpi.py",
             "optimize.py", "explore.py", "report.py", "stages.py")
SHARED_MD = {"memory-protocol.md": "plugins/job-search/skills/job-apply/references/memory-protocol.md",
             "browser-setup.md": "plugins/job-search/skills/job-apply/references/browser-setup.md"}
ROLE_MARK = {"*": "positive", "-": "negative", "~": "parked"}


def parse_funnel(spec: str) -> dict:
    m = re.match(r"^([a-z][a-z0-9_]*)(?::([^:=]+))?(?::([a-z][a-z0-9_]*))?=(.+)$", spec.strip())
    if not m:
        raise SystemExit(f"bad --funnel: {spec!r}")
    fid, label, item, rest = m.group(1), m.group(2), m.group(3), m.group(4)
    label = label or fid.replace("_", " ").title()
    item = item or (fid[:-1] if fid.endswith("s") else fid)
    chain_part, _, side_part = rest.partition(";")
    stages, success = [], ""
    chain = [x.strip() for x in chain_part.split(">") if x.strip()]
    ids = []
    for x in chain:
        role = ROLE_MARK.get(x[-1], "open")
        sid = x.rstrip("*-~")
        if not re.match(r"^[a-z][a-z0-9_]{0,31}$", sid):
            raise SystemExit(f"bad stage id {sid!r}")
        ids.append((sid, role, "confirm" if role == "positive" else "none"))
    for x in [y.strip() for y in side_part.split(";") if y.strip()]:
        role = ROLE_MARK.get(x[-1], "parked")
        sid = x.rstrip("*-~")
        ids.append((sid, role, "reason" if role == "negative" else "none"))
    for i, (sid, role, gate) in enumerate(ids):
        nxt = []
        if role == "open":
            nxt = [s for s, r, _ in ids[i + 1:i + 2]] + [s for s, r, _ in ids if r != "open" and s != sid]
        st = {"id": sid, "label": sid.replace("_", " ").title(), "role": role, "next": nxt}
        if gate != "none":
            st["gate"] = gate
        stages.append(st)
        if role == "positive" and not success:
            success = sid
    if not success:
        raise SystemExit(f"--funnel {fid}: mark the success stage with * (e.g. held*)")
    return {"id": fid, "label": label, "item": item, "success": success, "stages": stages}


def floor_for(funnels: list[dict]) -> list[dict]:
    groups = []
    for f in funnels:
        for s in f["stages"]:
            if s["role"] in ("open", "positive") and len(groups) < 8:
                groups.append({"id": f"{f['id']}-{s['id']}" if len(funnels) > 1 else s["id"], "label": s["label"],
                               "stages": [s["id"]], "funnel": f["id"]})
    return groups


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="new_agent.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--id", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--layer", required=True, help="e.g. 49-briefs (same name in both subjects)")
    ap.add_argument("--funnel", action="append", required=True)
    ap.add_argument("--what", default="", help="the daily's wording: 'Daily <what>' (default: the id)")
    ap.add_argument("--goal", default="")
    ap.add_argument("--target", type=int, default=5)
    ap.add_argument("--icon", default="sparkles")
    ap.add_argument("--color", default="")
    ap.add_argument("--blurb", default="")
    ap.add_argument("--network", default="No network: it reads only this brain.")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--persona", default="")
    ap.add_argument("--out", default=str(REPO / "plugins"))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", a.id):
        raise SystemExit("--id must be a slug (a-z, 0-9, -)")
    if not re.match(r"^\d{2}-[a-z][a-z0-9-]*$", a.layer):
        raise SystemExit("--layer looks like NN-name (e.g. 49-briefs)")
    out = pathlib.Path(a.out).expanduser() / a.id
    if out.exists() and not a.force:
        raise SystemExit(f"{out} exists (use --force to overwrite the scaffold files)")
    funnels = [parse_funnel(f) for f in a.funnel]
    short = re.sub(r"\s+Agent$", "", a.label).strip()
    what = a.what or a.id.replace("-", " ")
    goal = a.goal or f"{short} outcomes"
    metric = funnels[0]["success"]
    net_required = not a.network.lower().startswith("no network")
    outcomes = {f["success"]: {"label": f["success"].replace("_", " "), "cmd": f"ledger.py count {f['success']}"} for f in funnels}
    goals = [{"template": goal if i == 0 else f"{f['label']} {f['success'].replace('_', ' ')}", "metric": f["success"], "target": a.target}
             for i, f in enumerate(funnels)]
    subs = {
        "__ID__": a.id, "__LABEL__": a.label, "__SHORT__": short, "__LAYER__": a.layer, "__WHAT__": what,
        "__ENV__": re.sub(r"[^A-Z0-9]", "_", a.id.upper()), "__ICON__": a.icon,
        "__COLOR__": a.color or "#3e6ae1", "__BLURB__": a.blurb or f"{a.label}: runs the {what} day from your Second Brain — discover, screen, act within your settings, report.",
        "__NETWORK__": a.network, "__NETWORK_REQUIRED__": "true" if net_required else "false",
        "__DAILY__": f"{short} today", "__WEEKLY__": f"{short} review",
        "__ITEMS_JSON__": json.dumps({f["item"]: f["item"] + "s" for f in funnels}),
        "__ITEMS__": ", ".join(f["item"] + "s" for f in funnels),
        "__ITEM__": funnels[0]["item"],
        "__FUNNELS_JSON__": json.dumps(funnels, indent=2).replace("\n", "\n  "),
        "__FLOOR_JSON__": json.dumps(floor_for(funnels)),
        "__GOALS_JSON__": json.dumps(goals), "__OUTCOMES_JSON__": json.dumps(outcomes),
        "__INSPECTOR_JSON__": json.dumps({f["item"]: "generic" for f in funnels}),
        "__WEIGHT__": "heavy" if a.browser else "light", "__BROWSER__": "true" if a.browser else "false",
        "__PREFLIGHT_EXTRA__": ', "chrome_connected"' if a.browser else "",
        "__TOOLS_EXTRA__": ', "mcp__claude-in-chrome__*"' if a.browser else "",
        "__PERSONA__": a.persona or f"{a.id}-advisor",
        "__GOAL__": goal, "__GOAL_SLUG__": re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-"),
        "__METRIC__": metric, "__METRIC_LABEL__": metric.replace("_", " "), "__TARGET__": str(a.target),
        "__SUCCESS__": metric, "__MANIFEST__": re.sub(r"[^A-Z0-9]", "", a.id.upper()),
    }

    def fill(text: str) -> str:
        for k, v in subs.items():
            text = text.replace(k, v)
        return text

    written = []
    for src in sorted(TEMPLATE.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(TEMPLATE).as_posix().replace(".template", "")
        rel = fill(rel)
        if rel == "plugin.json":
            rel = ".claude-plugin/plugin.json"
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(fill(src.read_text(encoding="utf-8")), encoding="utf-8")
        written.append(rel)
    core = out / "skills" / f"{a.id}-core"
    for name in SHARED_PY:
        shutil.copyfile(ENGINE / name, core / "scripts" / name)
        written.append(f"skills/{a.id}-core/scripts/{name}")
    (core / "references").mkdir(parents=True, exist_ok=True)
    for name, rel in SHARED_MD.items():
        shutil.copyfile(REPO / rel, core / "references" / name)
        written.append(f"skills/{a.id}-core/references/{name}")
    lic = REPO / "plugins" / "job-search" / "LICENSE"
    if lic.is_file():
        shutil.copyfile(lic, out / "LICENSE")
    sys.path.insert(0, str(ENGINE))
    import validate_agent  # noqa: PLC0415
    probs, warns = validate_agent.validate(out, REPO)
    print(f"scaffolded plugins/{a.id}: {len(written)} files")
    for p in probs:
        print("  ! " + p)
    for w_ in warns:
        print("  ~ " + w_)
    print("validate_agent: " + ("ok" if not probs else f"{len(probs)} problem(s)"))
    print(f"next: python3 engine/scripts/validate_agent.py {out} · fill sources.py / score.py / actions.py · "
          f"python3 packaging/build_plugin.py {a.id}")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
