#!/usr/bin/env python3
"""sources.py - discover candidates (STUB). Replace `discover()` with the real discovery for this
agent: the brain first (ties, notes, correlations), then the proven sources in profile/sources.md,
then today's explore slice (`daily.py explore`). Any network read must be declared in
.claude-plugin/plugin.json. Prints one JSON object per candidate for the skill to score.

    sources.py discover [--date D]
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import profile_dir  # noqa: E402
import explore  # noqa: E402


def discover(date=None):
    data = explore.load(profile_dir() / "sources.md")
    today = [r["source"] for r in data["proven"] if r.get("status", "active") == "active"]
    today += explore.pick(data, date)
    # STUB: no network here. Yield what the user's own profile names, so the loop runs end to end.
    for s in today:
        yield {"key": f"sample-{s.lower().replace(' ', '-')}", "title": f"Sample from {s}", "source": s, "kind": "__ITEM__",
               "why": "stub candidate - replace sources.py with the real discovery"}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("discover"); g.add_argument("--date")
    a = ap.parse_args()
    for c in discover(a.date):
        print(json.dumps(c, ensure_ascii=False))


if __name__ == "__main__":
    main()
