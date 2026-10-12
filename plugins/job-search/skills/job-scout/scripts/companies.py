#!/usr/bin/env python3
"""
companies.py - the scout's company registry: every employer it has ever seen hiring.

The sweep runs market -> companies -> careers sites. Discovery (LinkedIn's public search,
regional boards, recruiters) names the companies hiring; this registry remembers each one,
its careers site and the ATS behind it, so the next run goes straight to the employer's own
board — where the full list, the real posting date and the real apply link live.

State: <state root>/companies.jsonl, one company per line. Compounds across runs. The old
flat companies.txt ('<provider> <slug>' lines) is imported on first use and left in place.

    companies.py add [--market M] < rows.json     # upsert every company in discovered rows
    companies.py set "<name>" --ats workday --slug acme.wd3/Careers [--careers URL] [--domain D]
    companies.py due [--days 7] [--markets "UAE|Switzerland"]
                                                # JSON: boards to sweep today (known ATS + slug)
    companies.py unresolved [--markets ...]     # companies with hits but no known careers board
    companies.py swept "<name>" ...             # stamp today as swept
    companies.py batch [--days 7]               # '<provider> <slug>' lines for ats_fetch --batch
    companies.py stats

A company is due when it had a new in-lane posting this run, or its board was last swept
more than --days ago. Unresolved companies are the scout's to-do: find the careers page
(WebSearch '<company> careers'), classify it (job-apply/scripts/detect_portal.py), `set` it.
"""
import argparse, datetime, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import state_root  # noqa: E402

ROOT = state_root()
REG = ROOT / "companies.jsonl"
LEGACY = ROOT / "companies.txt"
TODAY = datetime.date.today().isoformat()
# boards ats_fetch.py can read; `auto` = a slug whose provider is unknown (ats_fetch probes them all)
READABLE = {"greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "personio",
            "teamtailor", "workday", "auto"}


def key(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def load():
    reg = {}
    if REG.exists():
        for line in REG.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line) if line.strip() else None
            except ValueError:
                d = None
            if isinstance(d, dict) and d.get("key"):
                reg[d["key"]] = d
    if not reg and LEGACY.exists():                     # one-time import, never deletes the file
        for line in LEGACY.read_text(encoding="utf-8").splitlines():
            parts = line.split("#")[0].split()
            if len(parts) >= 2:
                k = key(parts[1])
                reg[k] = {"key": k, "name": parts[1], "ats": parts[0], "slug": parts[1],
                          "markets": [], "sources": ["companies.txt"], "first_seen": TODAY,
                          "last_seen": "", "last_swept": "", "hits": 0}
    return reg


def save(reg):
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = REG.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n"
                           for v in sorted(reg.values(), key=lambda d: d["key"])), encoding="utf-8")
    tmp.replace(REG)


def find(reg, name):
    k = key(name)
    if k in reg:
        return reg[k]
    for v in reg.values():                               # 'boschgroup' vs 'bosch'
        if k and (k in v["key"] or v["key"] in k) and min(len(k), len(v["key"])) >= 4:
            return v
    return None


def _days_since(day):
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(day)).days
    except (TypeError, ValueError):
        return 10 ** 6


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("add"); g.add_argument("--market", default="")
    g = sub.add_parser("set"); g.add_argument("name"); g.add_argument("--ats", default="")
    g.add_argument("--slug", default=""); g.add_argument("--careers", default="")
    g.add_argument("--domain", default="")
    for name in ("due", "unresolved", "batch"):
        g = sub.add_parser(name); g.add_argument("--days", type=int, default=7)
        g.add_argument("--markets", default="")
    g = sub.add_parser("swept"); g.add_argument("names", nargs="+")
    sub.add_parser("stats")
    a = ap.parse_args()
    reg = load()

    if a.cmd == "add":
        rows, new = json.load(sys.stdin), 0
        for r in rows:
            name = (r.get("company") or "").strip()
            if not name or name.lower() in ("confidential", "stealth", "undisclosed"):
                continue
            c = find(reg, name)
            if c is None:
                k = key(name)
                c = reg[k] = {"key": k, "name": name, "ats": "", "slug": "", "careers": "",
                              "domain": "", "markets": [], "sources": [], "first_seen": TODAY,
                              "last_seen": "", "last_swept": "", "hits": 0}
                new += 1
            ats = r.get("ats") or ""
            if ats in READABLE and not c["ats"] and ats != "linkedin":
                c["ats"], c["slug"] = ats, r.get("board") or r.get("company")
            m = r.get("market") or a.market
            if m and m not in c["markets"]:
                c["markets"].append(m)
            src = r.get("source") or ats
            if src and src not in c["sources"]:
                c["sources"].append(src)
            c["last_seen"] = TODAY
            if r.get("in_lane", True):
                c["hits"] = c.get("hits", 0) + 1
                c["hit_today"] = TODAY
        save(reg)
        print(f"{len(rows)} rows -> {new} new companies; registry holds {len(reg)}", file=sys.stderr)
        return

    if a.cmd == "set":
        c = find(reg, a.name)
        if c is None:
            k = key(a.name)
            c = reg[k] = {"key": k, "name": a.name, "markets": [], "sources": [],
                          "first_seen": TODAY, "last_seen": "", "last_swept": "", "hits": 0}
        for f in ("ats", "slug", "careers", "domain"):
            if getattr(a, f):
                c[f] = getattr(a, f)
        save(reg)
        print(f"{c['name']}: ats={c.get('ats') or '?'} slug={c.get('slug') or '?'}")
        return

    if a.cmd == "swept":
        for n in a.names:
            c = find(reg, n)
            if c:
                c["last_swept"] = TODAY
        save(reg)
        return

    mk = re.compile(a.markets, re.I) if getattr(a, "markets", "") else None
    in_market = (lambda c: True) if mk is None else \
        (lambda c: any(mk.search(m) for m in c.get("markets", [])))

    if a.cmd in ("due", "batch"):
        due = [c for c in reg.values()
               if c.get("ats") in READABLE and c.get("slug") and in_market(c)
               and (c.get("hit_today") == TODAY or _days_since(c.get("last_swept")) > a.days)]
        if a.cmd == "batch":
            print("\n".join(f"{c['ats']} {c['slug']} {c['name']}" for c in due))
        else:
            print(json.dumps([{"name": c["name"], "ats": c["ats"], "slug": c["slug"]} for c in due],
                             indent=2, ensure_ascii=False))
        print(f"{len(due)} boards due", file=sys.stderr)
        return

    if a.cmd == "unresolved":
        todo = sorted((c for c in reg.values()
                       if not c.get("ats") and not c.get("careers") and c.get("hits") and in_market(c)),
                      key=lambda c: -c.get("hits", 0))
        print(json.dumps([{"name": c["name"], "markets": c["markets"], "hits": c["hits"]} for c in todo],
                         indent=2, ensure_ascii=False))
        print(f"{len(todo)} companies with hits and no known careers board", file=sys.stderr)
        return

    by_ats = {}
    for c in reg.values():
        by_ats[c.get("ats") or "unresolved"] = by_ats.get(c.get("ats") or "unresolved", 0) + 1
    print(f"companies : {len(reg)}  ({REG})")
    for k, v in sorted(by_ats.items(), key=lambda x: -x[1]):
        print(f"  {k:16} {v}")


if __name__ == "__main__":
    main()
