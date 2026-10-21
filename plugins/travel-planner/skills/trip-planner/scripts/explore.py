#!/usr/bin/env python3
"""explore.py - explore / exploit over an agent's discovery sources: profile/sources.md.

SHIPPED BYTE-IDENTICAL in the engine and every plugin (build_plugin.SHARED_FILES). Stdlib only,
deterministic: the slice a run explores depends only on the file and the date.

`profile/sources.md` is the user's file (onboarding seeds it; the optimizer may promote or drop
rows; the user edits it freely). Two tables, the same columns:

    ## Proven            sources that produced results - swept every run
    ## Candidates        new sources / queries / segments - a 20 % slice is tried each run

    | Source | Kind | Tries | Found | Converted | Last | Status |

A settings fence at the top may set `explore: 0.2` (the share) and `drop_after: 5` (tries with
nothing found before a candidate is dropped). A candidate that converts is PROMOTED to Proven;
one that never finds anything is DROPPED after N tries (status `dropped`, row kept - nothing is
deleted). Found sources are remembered through memory.py by the caller (`observe --source agent`).

    explore.py pick   --sources F [--date D] [--budget N] [--share X]    today's slice (names)
    explore.py record --sources F --source NAME --found N [--converted N] [--date D]
    explore.py add    --sources F --source NAME [--kind K] [--proven]
    explore.py table  --sources F [--json]
    python3 explore.py --selftest
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import sys

COLS = ["Source", "Kind", "Tries", "Found", "Converted", "Last", "Status"]
DEFAULTS = {"explore": 0.2, "drop_after": 5}
HEADER = "# Sources\n\nWhich sources, boards, queries and segments to sweep. **Proven** rows run every day; a slice of **Candidates** (the `explore` share) is tried each run. A candidate that converts is promoted; one that never finds anything is dropped after `drop_after` tries. Edit freely — the optimizer only moves rows.\n\n```settings\nexplore: 0.2\ndrop_after: 5\n```\n"


def parse(text):
    data = {"settings": dict(DEFAULTS), "proven": [], "candidates": [], "head": ""}
    m = re.search(r"```settings\n(.*?)\n```", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"^\s*([a-z_]+)\s*:\s*(.+?)\s*$", line)
            if mm:
                try:
                    data["settings"][mm.group(1)] = float(mm.group(2)) if "." in mm.group(2) else int(mm.group(2))
                except ValueError:
                    data["settings"][mm.group(1)] = mm.group(2)
    sec = None
    for line in text.splitlines():
        h = re.match(r"^##\s+(Proven|Candidates)\b", line, re.I)
        if h:
            sec = h.group(1).lower()
            continue
        if sec and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not cells or cells[0].lower() == "source" or set(cells[0]) <= {"-", ":", " "}:
                continue
            row = dict(zip([c.lower() for c in COLS], cells + [""] * (len(COLS) - len(cells))))
            for k in ("tries", "found", "converted"):
                try:
                    row[k] = int(row.get(k) or 0)
                except ValueError:
                    row[k] = 0
            row["status"] = row.get("status") or "active"
            data[sec].append(row)
    hm = re.match(r"\A(.*?)(?=^##\s+(?:Proven|Candidates)\b)", text, re.S | re.M)
    data["head"] = hm.group(1) if hm else (text if "## Proven" not in text and "## Candidates" not in text else "")
    return data


def render(data):
    def tbl(rows):
        out = ["| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS)]
        for r in rows:
            out.append("| " + " | ".join(str(r.get(c.lower(), "")) for c in COLS) + " |")
        return "\n".join(out) + "\n"
    head = (data.get("head") or HEADER).rstrip("\n") + "\n\n"
    if not re.search(r"```settings", head):
        head += "```settings\n" + "".join(f"{k}: {v}\n" for k, v in data["settings"].items()) + "```\n\n"
    else:
        head = re.sub(r"```settings\n.*?\n```", "```settings\n" + "".join(f"{k}: {v}" + "\n" for k, v in data["settings"].items()).rstrip("\n") + "\n```", head, count=1, flags=re.S)
    return head + "## Proven\n\n" + tbl(data["proven"]) + "\n## Candidates\n\n" + tbl(data["candidates"])


def load(path):
    p = pathlib.Path(path)
    return parse(p.read_text(encoding="utf-8")) if p.is_file() else parse(HEADER)


def save(path, data):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(render(data), encoding="utf-8")
    os.replace(tmp, p)


def pick(data, date=None, budget=10, share=None):
    """Today's explore slice: a deterministic rotation over the active candidates (least-tried
    first, then by name), offset by the date, of size round(budget * share) (at least 1)."""
    share = data["settings"].get("explore", DEFAULTS["explore"]) if share is None else share
    try:
        share = float(share)
    except (TypeError, ValueError):
        share = DEFAULTS["explore"]
    cands = [r for r in data["candidates"] if r.get("status", "active") == "active"]
    if not cands:
        return []
    cands.sort(key=lambda r: (int(r.get("tries") or 0), r["source"].lower()))
    k = max(1, min(len(cands), int(round(budget * share))))
    d = _dt.date.fromisoformat(date) if isinstance(date, str) else (date or _dt.date.today())
    off = d.toordinal() % len(cands)
    rot = cands[off:] + cands[:off]
    return [r["source"] for r in rot[:k]]


def record(data, source, found=0, converted=0, date=None, kind=""):
    """Note a try. Promotion: a candidate that converted moves to Proven. Demotion: a candidate with
    nothing found in `drop_after` tries is marked dropped (the row stays)."""
    d = (date or _dt.date.today().isoformat())[:10]
    drop_after = int(data["settings"].get("drop_after", DEFAULTS["drop_after"]) or DEFAULTS["drop_after"])
    row = next((r for r in data["proven"] + data["candidates"] if r["source"].lower() == source.lower()), None)
    where = "proven" if row in data["proven"] else "candidates"
    if row is None:
        row = {"source": source, "kind": kind, "tries": 0, "found": 0, "converted": 0, "last": "", "status": "active"}
        data["candidates"].append(row)
        where = "candidates"
    row["tries"] = int(row.get("tries") or 0) + 1
    row["found"] = int(row.get("found") or 0) + int(found or 0)
    row["converted"] = int(row.get("converted") or 0) + int(converted or 0)
    row["last"] = d
    if kind and not row.get("kind"):
        row["kind"] = kind
    change = ""
    if where == "candidates":
        if row["converted"] > 0:
            data["candidates"].remove(row)
            row["status"] = "active"
            data["proven"].append(row)
            change = "promoted"
        elif row["found"] == 0 and row["tries"] >= drop_after:
            row["status"] = "dropped"
            change = "dropped"
    return row, change


def add(data, source, kind="", proven=False):
    if any(r["source"].lower() == source.lower() for r in data["proven"] + data["candidates"]):
        return False
    (data["proven"] if proven else data["candidates"]).append(
        {"source": source, "kind": kind, "tries": 0, "found": 0, "converted": 0, "last": "", "status": "active"})
    return True


def _selftest():
    import tempfile  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as t:
        p = pathlib.Path(t) / "sources.md"
        d = load(p)
        for n in ("alpha", "beta", "gamma", "delta", "epsilon"):
            add(d, n, kind="board")
        add(d, "proven-one", kind="board", proven=True)
        save(p, d)
        d = load(p)
        assert [r["source"] for r in d["proven"]] == ["proven-one"] and len(d["candidates"]) == 5
        T = _dt.date(2026, 1, 15)
        a = pick(d, T.isoformat(), budget=10)
        b = pick(d, T.isoformat(), budget=10)
        c = pick(d, (T + _dt.timedelta(days=1)).isoformat(), budget=10)
        assert a == b and len(a) == 2 and a != c, (a, c)
        assert pick(d, T.isoformat(), budget=10, share=0.0) == [a[0]] or len(pick(d, T.isoformat(), budget=10, share=0.0)) == 1
        row, ch = record(d, "alpha", found=3, converted=1, date=T.isoformat())
        assert ch == "promoted" and row in d["proven"]
        ch = ""
        for i in range(5):
            row, ch = record(d, "beta", found=0, date=T.isoformat())
        assert ch == "dropped" and row["status"] == "dropped" and row in d["candidates"]
        assert "beta" not in pick(d, T.isoformat(), budget=20, share=1.0)
        save(p, d)
        d2 = load(p)
        assert d2["proven"][1]["converted"] == 1 and d2["settings"]["drop_after"] == 5
        assert render(d2) == render(load(p))
        head_kept = "# Sources\n\nmy own words\n\n```settings\nexplore: 0.3\n```\n\n## Proven\n\n| Source | Kind | Tries | Found | Converted | Last | Status |\n|---|---|---|---|---|---|---|\n| x | b | 0 | 0 | 0 |  | active |\n\n## Candidates\n\n"
        d3 = parse(head_kept)
        assert d3["settings"]["explore"] == 0.3 and "my own words" in render(d3)
    print("explore: selftest ok")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--selftest"]:
        return _selftest()
    ap = argparse.ArgumentParser(prog="explore.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("pick"); g.add_argument("--sources", required=True); g.add_argument("--date"); g.add_argument("--budget", type=int, default=10); g.add_argument("--share", type=float)
    g = sub.add_parser("record"); g.add_argument("--sources", required=True); g.add_argument("--source", required=True)
    g.add_argument("--found", type=int, default=0); g.add_argument("--converted", type=int, default=0); g.add_argument("--date"); g.add_argument("--kind", default="")
    g = sub.add_parser("add"); g.add_argument("--sources", required=True); g.add_argument("--source", required=True); g.add_argument("--kind", default=""); g.add_argument("--proven", action="store_true")
    g = sub.add_parser("table"); g.add_argument("--sources", required=True); g.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    d = load(a.sources)
    if a.cmd == "pick":
        for s in pick(d, a.date, a.budget, a.share):
            print(s)
    elif a.cmd == "record":
        row, ch = record(d, a.source, a.found, a.converted, a.date, a.kind)
        save(a.sources, d)
        print(json.dumps({"source": row["source"], "tries": row["tries"], "found": row["found"], "converted": row["converted"], "change": ch}))
    elif a.cmd == "add":
        added = add(d, a.source, a.kind, a.proven)
        save(a.sources, d)
        print("added" if added else "already there")
    elif a.cmd == "table":
        print(json.dumps({"proven": d["proven"], "candidates": d["candidates"], "settings": d["settings"]}, indent=1) if a.json else render(d), end="" if not a.json else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
