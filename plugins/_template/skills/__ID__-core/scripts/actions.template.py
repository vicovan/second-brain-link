#!/usr/bin/env python3
"""actions.py - what "act" means for this agent (STUB). Everything here runs BEHIND the gates of
`level:` (the skill asks; this script never sends, posts, buys or books). It prepares the work in
<layer>/work/<date>/<key>/ and logs an `acted` event so throughput counts it.

    actions.py prepare KEY         write the work folder (a draft, a brief, a plan)
"""
import argparse, datetime, json, os, pathlib, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import render_dir  # noqa: E402
import ledger as LG  # noqa: E402


def prepare(key):
    recs = LG.L.load()
    rec = LG.L.by_key(recs).get(key)
    if not rec:
        sys.exit(f"no item {key}")
    day = datetime.date.today().isoformat()
    d = render_dir() / "work" / day / key
    d.mkdir(parents=True, exist_ok=True)
    (d / "draft.md").write_text(f"# Draft for {rec.get('title', key)}\n\n_Prepared {day}. Nothing was sent._\n", encoding="utf-8")
    rec.setdefault("work", []).append(f"work/{day}/{key}")
    LG.L.save(recs)
    LG.L.event(key, None, None, "agent", f"prepared work/{day}/{key}", kind="acted")
    print(json.dumps({"key": key, "work": f"work/{day}/{key}"}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("prepare"); g.add_argument("key")
    a = ap.parse_args()
    prepare(a.key)


if __name__ == "__main__":
    main()
