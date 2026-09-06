#!/usr/bin/env python3
"""
scout_state.py - the job scout's memory: daily gate, dedupe, report paths.

State lives OUTSIDE the skill folder (so it never ends up in a zip):
    <state root>/   (default; override with $JOB_SEARCH_HOME)
        last-run.txt        YYYY-MM-DD of the last completed run
        snooze.txt          YYYY-MM-DD the user said "not today"
        seen.json           {key: {first_seen, title, company, url, score}}
        reports/YYYY-MM-DD.md

Subcommands:
    due                  exit 0 + print a nudge if a run is due today, else exit 1 silent
    mark-run             stamp today as run
    snooze               stamp today as skipped
    window               print how many days back to search (since last run, 1..14)
    filter-seen          stdin JSON list -> stdout only the rows never seen before
    add-seen             stdin JSON list -> record them as seen
    report-path          print today's report path (creates reports/)
    stats                print counts
"""
import json, os, sys, datetime, re, pathlib

def _state_root():
    """Delegates to paths.py — the single resolver. Kept as a function so callers
    that already import `_state_root` keep working."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from paths import state_root
    return state_root()


ROOT = _state_root()
SEEN = ROOT / "seen.json"
LAST = ROOT / "last-run.txt"
SNOOZE = ROOT / "snooze.txt"
REPORTS = ROOT / "reports"
TODAY = datetime.date.today().isoformat()


def read(p):
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def load_seen():
    try:
        return json.loads(SEEN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def key(row):
    """Stable identity for a posting: canonical URL, else company+title slug."""
    u = (row.get("url") or "").split("?")[0].rstrip("/")
    if u:
        m = re.search(r"(\d{6,})$", u)                # LinkedIn / Greenhouse numeric id
        return f"id:{m.group(1)}" if m else f"url:{u.lower()}"
    slug = re.sub(r"[^a-z0-9]+", "-",
                  f"{row.get('company','')}-{row.get('title','')}".lower()).strip("-")
    return f"slug:{slug}"


def norm(s):
    """Compress to letters and digits so 'Northwind Ventures / Atlas' and the board slug
    'northwindventures' compare, and a board's '(x/f/m) - Paris' suffix does not block a match."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def applied_pairs():
    """(company, title) of everything already applied to, drafted or skipped.

    The URL key alone is not enough: the same job found through LinkedIn and through the
    company's ATS board produces two different keys, so a role the user applied to yesterday
    reappears as "new" today. Matching on company + title closes that gap.
    """
    out = set()
    f = ROOT / "outcomes.jsonl"
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        c, ti = norm(d.get("company")), norm(d.get("title") or d.get("role"))
        if c and ti:
            out.add((c, ti))
    return out


def seen_applied(row, done):
    """True when this posting is a job already applied to. Company and title are compared
    by containment in both directions: board titles carry suffixes the log does not."""
    c, ti = norm(row.get("company")), norm(row.get("title"))
    if not c or not ti:
        return False
    for dc, dt in done:
        if (c in dc or dc in c) and (ti in dt or dt in ti):
            return True
    return False


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    ROOT.mkdir(parents=True, exist_ok=True)

    if cmd == "due":
        if read(LAST) == TODAY or read(SNOOZE) == TODAY:
            sys.exit(1)
        print("due")
        sys.exit(0)

    if cmd == "mark-run":
        LAST.write_text(TODAY); print(f"run stamped {TODAY}"); return

    if cmd == "snooze":
        SNOOZE.write_text(TODAY); print(f"snoozed for {TODAY}"); return

    if cmd == "window":
        last = read(LAST)
        try:
            d = (datetime.date.today() - datetime.date.fromisoformat(last)).days
        except ValueError:
            d = 14                                    # first ever run: cast wide
        print(max(1, min(14, d or 1))); return

    if cmd == "report-path":
        REPORTS.mkdir(parents=True, exist_ok=True)
        print(REPORTS / f"{TODAY}.md"); return

    if cmd in ("filter-seen", "add-seen"):
        rows = json.load(sys.stdin)
        seen = load_seen()
        if cmd == "filter-seen":
            done = applied_pairs()
            fresh, dup_seen, dup_applied = [], 0, 0
            for r in rows:
                if key(r) in seen:
                    dup_seen += 1
                elif seen_applied(r, done):
                    dup_applied += 1
                else:
                    fresh.append(r)
            print(json.dumps(fresh, indent=2, ensure_ascii=False))
            print(f"{len(rows)} in, {len(fresh)} new, {dup_seen} already seen, "
                  f"{dup_applied} already applied to", file=sys.stderr)
        else:
            for r in rows:
                seen.setdefault(key(r), {
                    "first_seen": TODAY,
                    "title": r.get("title", ""), "company": r.get("company", ""),
                    "url": r.get("url", ""), "score": r.get("score"),
                })
            SEEN.write_text(json.dumps(seen, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"seen.json now holds {len(seen)} postings", file=sys.stderr)
        return

    seen = load_seen()
    print(f"seen postings : {len(seen)}")
    print(f"last run      : {read(LAST) or 'never'}")
    print(f"snoozed       : {read(SNOOZE) or '-'}")
    print(f"reports       : {len(list(REPORTS.glob('*.md'))) if REPORTS.exists() else 0}")
    print(f"state root    : {ROOT}")


if __name__ == "__main__":
    main()
