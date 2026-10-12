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
    since-seconds        seconds back to search for time-filtered sources (LinkedIn's f_TPR):
                         since the last completed run plus one day of overlap; 14 days on a
                         first run; never more than 30 days
    merge [filters] F... combine every source's JSON into one list: keep in-lane rows (the
                         profile's own regexes, passed in), collapse the same job found on
                         several sources into ONE row that lists every source and URL (the
                         employer's own date and link win), mark each row new / already seen,
                         and write coverage.json. Filters: --titles --domain --exclude-titles
                         --regions, and --markets "PT=lisbon|porto|portugal;ES=madrid|spain".
    coverage             print coverage.json as a table, with a verdict per market: a market
                         with zero in-lane rows from fewer than 3 sources is a COVERAGE FAILURE
                         (widen the sweep), never "a thin market". Exit 1 on any failure.
    filter-seen          stdin JSON list -> stdout only the rows never seen before
    gate                 stdin JSON list (the FINAL shortlist) -> stdout only the rows the
                         ledger allows; every dropped row and its reason on stderr. Drops
                         the same posting (by job id), the same company + title, and any
                         company applied to in the last 30 days (--days N).
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


# Statuses that mean the user has already acted on a posting — it must not come back.
# `skipped_policy` is absent on purpose: it is the company rule talking, and gate()
# re-applies that rule on its own dates, so the role returns when the company is eligible.
ACTED = {"applied", "filled", "prior_external", "drafted_linkedin", "handoff_portal",
         "skipped_knockout", "skipped_walled", "skipped_review"}
# Statuses that start the one-application-per-company clock.
SENT = {"applied", "filled", "prior_external"}


def ledger():
    f = ROOT / "outcomes.jsonl"
    out = []
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line) if line.strip() else None
        except ValueError:
            d = None
        if isinstance(d, dict):
            out.append(d)
    return out


def posting_id(url):
    """The board's own job id — the same requisition found through two routes (the
    embed form, a mirror, a tracking query) still has one id. None when there is none."""
    u = (url or "").strip()
    if not u:
        return None
    m = re.search(r"[?&](?:gh_jid|jobId|job_id|jid|token)=([A-Za-z0-9-]{6,})", u)
    if m:
        return m.group(1).lower()
    path = u.split("?")[0].split("#")[0].rstrip("/")
    m = re.search(r"(\d{6,})$", path)
    if m:
        return m.group(1)
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", path.lower())
    return m.group(1) if m else None


def blocked(row, recs, days=30, today=None):
    """Why the ledger says this row must not be shortlisted, or None."""
    today = today or datetime.date.today()
    c, ti = norm(row.get("company")), norm(row.get("title") or row.get("role"))
    pid = posting_id(row.get("url") or row.get("apply_url"))
    for d in recs:
        st = str(d.get("status") or "")
        dc, dt = norm(d.get("company")), norm(d.get("title") or d.get("role"))
        when = str(d.get("date") or "")[:10]
        same_post = bool(pid) and pid in {posting_id(d.get("url")), posting_id(d.get("apply_url"))}
        same_role = bool(c and ti and dc and dt) and (c in dc or dc in c) and (ti in dt or dt in ti)
        if (same_post or same_role) and st in ACTED:
            res = f", result {d['result']}" if d.get("result") else ""
            return f"already {st} {when}{res} — {d.get('company')}: {d.get('title') or d.get('role')}"
        if c and dc and (c == dc) and st in SENT and when:
            try:
                age = (today - datetime.date.fromisoformat(when)).days
            except ValueError:
                continue
            if 0 <= age < days:
                back = datetime.date.fromisoformat(when) + datetime.timedelta(days=days)
                return (f"company rule — applied to {d.get('company')} {when} "
                        f"({d.get('title') or d.get('role')}); eligible again {back.isoformat()}")
    return None


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


COVERAGE = ROOT / "coverage.json"
# Sources whose date and link are the employer's own — they win over an aggregator's copy.
EMPLOYER = {"greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "personio",
            "teamtailor", "workday", "careers"}


def _flag(args, name, default=""):
    if name in args:
        i = args.index(name)
        v = args[i + 1] if i + 1 < len(args) else default
        del args[i:i + 2]
        return v
    return default


def _city(loc):
    return norm((loc or "").split(",")[0].split("/")[0])


def merge(args):
    """Combine sources -> in-lane, de-duplicated rows with every source kept, plus coverage."""
    args = list(args)
    titles = _flag(args, "--titles"); domain = _flag(args, "--domain")
    excl = _flag(args, "--exclude-titles"); regions = _flag(args, "--regions")
    markets = [m.split("=", 1) for m in _flag(args, "--markets").split(";") if "=" in m]
    out = _flag(args, "--out")
    rx = lambda p: re.compile(p, re.I) if p else None
    T, D, X, R = rx(titles), rx(domain), rx(excl), rx(regions)
    M = [(name.strip(), re.compile(pat, re.I)) for name, pat in markets]

    def market_of(r):
        blob = f"{r.get('location', '')} {r.get('market', '')}"
        for name, pat in M:
            if pat.search(blob):
                return name
        return r.get("market") or "other"

    rows = []
    for f in args:
        try:
            got = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"! {f}: {e}", file=sys.stderr)
            continue
        for r in got if isinstance(got, list) else []:
            r = dict(r)
            r["source"] = r.get("source") or r.get("ats") or os.path.basename(f)
            r["market"] = market_of(r)
            t = r.get("title", "")
            r["in_lane"] = bool((not T or T.search(t)) and (not D or D.search(t))
                                and not (X and X.search(t))
                                and (not R or R.search(f"{r.get('location', '')} {r.get('market', '')}")))
            rows.append(r)

    cov = {name: {} for name, _ in M}      # every declared market appears, even with no rows
    def bump(r, field):
        c = cov.setdefault(r["market"], {}).setdefault(r["source"], {"raw": 0, "in_lane": 0, "new": 0})
        c[field] += 1
    for r in rows:
        bump(r, "raw")

    # Collapse the same job across sources: same normalised title and company (by containment,
    # since a board slug and a display name differ), and the same city when both give one.
    buckets, merged = {}, []
    for r in rows:
        if not r["in_lane"]:
            continue
        bump(r, "in_lane")
        tk, ck, city = norm(r.get("title")), norm(r.get("company")), _city(r.get("location"))
        hit = None
        for m in buckets.get(tk, []):
            mc = norm(m.get("company"))
            if ck and mc and (ck in mc or mc in ck) and (not city or not m["_city"] or city == m["_city"]):
                hit = m
                break
        if hit is None:
            m = dict(r, sources=[r["source"]], urls=[r.get("url", "")], _city=city)
            buckets.setdefault(tk, []).append(m)
            merged.append(m)
            continue
        if r["source"] not in hit["sources"]:
            hit["sources"].append(r["source"])
        if r.get("url") and r["url"] not in hit["urls"]:
            hit["urls"].append(r["url"])
        if r["source"] in EMPLOYER and hit.get("source") not in EMPLOYER:
            for f in ("url", "posted", "location", "comp", "ats"):     # the employer's own copy wins
                if r.get(f):
                    hit[f] = r[f]
            hit["source"] = r["source"]
        elif r.get("posted") and (not hit.get("posted") or r["posted"] < hit["posted"]) \
                and hit.get("source") not in EMPLOYER:
            hit["posted"] = r["posted"]

    seen, done = load_seen(), applied_pairs()
    ids = {posting_id(d.get("url")) for d in ledger()} - {None}
    for m in merged:
        m.pop("_city", None)
        known = any(key(dict(m, url=u)) in seen for u in m["urls"]) or key(m) in seen
        applied = seen_applied(m, done) or any(posting_id(u) in ids for u in m["urls"])
        m["new"] = not known and not applied
        m["already_applied"] = applied
        if m["new"]:
            bump(dict(m, source=m["sources"][0]), "new")

    COVERAGE.write_text(json.dumps({"date": TODAY, "markets": cov}, indent=2), encoding="utf-8")
    text = json.dumps(merged, indent=2, ensure_ascii=False)
    if out:
        open(out, "w", encoding="utf-8").write(text)
    else:
        print(text)
    new = sum(1 for m in merged if m["new"])
    print(f"{len(rows)} rows from {len(args)} files -> {sum(r['in_lane'] for r in rows)} in lane -> "
          f"{len(merged)} distinct jobs ({new} new since last run, {len(merged) - new} already seen "
          f"or applied); coverage -> {COVERAGE}", file=sys.stderr)


def coverage():
    try:
        cov = json.loads(COVERAGE.read_text(encoding="utf-8"))["markets"]
    except (OSError, ValueError, KeyError):
        print("no coverage.json — run `scout_state.py merge` first")
        return 1
    bad = 0
    print(f"{'market':14} {'source':16} {'raw':>5} {'in lane':>8} {'new':>5}")
    for mk in sorted(cov):
        srcs = cov[mk]
        for s, c in sorted(srcs.items(), key=lambda x: -x[1]["raw"]):
            print(f"{mk:14} {s:16} {c['raw']:>5} {c['in_lane']:>8} {c['new']:>5}")
        lane = sum(c["in_lane"] for c in srcs.values())
        n = sum(1 for c in srcs.values() if c["raw"])
        if mk == "other":
            continue
        if lane and n < 3:
            print(f"  -> {mk}: {lane} in lane, but from only {n} source{'s' if n != 1 else ''} — "
                  f"partial coverage; run the rest of its regional pack before calling the list complete")
        elif lane:
            print(f"  -> {mk}: OK ({lane} in lane from {n} sources)")
        elif n >= 3:
            print(f"  -> {mk}: thin, verified — 0 in lane across {n} sources")
        else:
            bad += 1
            print(f"  -> {mk}: COVERAGE FAILURE — 0 in lane from only {n} source(s). Widen before "
                  f"calling this market thin (next regional source, title synonyms, company boards).")
    return 1 if bad else 0


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

    if cmd == "since-seconds":
        last = read(LAST)
        now = datetime.datetime.now()
        try:
            start = datetime.datetime.combine(datetime.date.fromisoformat(last), datetime.time())
            secs = int((now - start).total_seconds()) + 86400        # one day of overlap
        except ValueError:
            secs = 14 * 86400                                        # first ever run
        print(max(86400, min(30 * 86400, secs))); return

    if cmd == "merge":
        return merge(sys.argv[2:])

    if cmd == "coverage":
        return sys.exit(coverage())

    if cmd == "report-path":
        REPORTS.mkdir(parents=True, exist_ok=True)
        print(REPORTS / f"{TODAY}.md"); return

    if cmd in ("filter-seen", "add-seen"):
        rows = json.load(sys.stdin)
        seen = load_seen()
        if cmd == "filter-seen":
            done = applied_pairs()
            fresh, dup_seen, dup_applied = [], 0, 0
            ids = {posting_id(d.get("url")) for d in ledger()} - {None}
            for r in rows:
                if key(r) in seen:
                    dup_seen += 1
                elif seen_applied(r, done) or posting_id(r.get("url")) in ids:
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

    if cmd == "gate":
        days = 30
        if "--days" in sys.argv:
            days = int(sys.argv[sys.argv.index("--days") + 1])
        rows, recs = json.load(sys.stdin), ledger()
        keep, dropped = [], []
        for r in rows:
            why = blocked(r, recs, days)
            (dropped if why else keep).append((r, why))
        print(json.dumps([r for r, _ in keep], indent=2, ensure_ascii=False))
        for r, why in dropped:
            print(f"DROP {r.get('company')}: {r.get('title') or r.get('role')} — {why}", file=sys.stderr)
        print(f"{len(rows)} in, {len(keep)} allowed, {len(dropped)} dropped by the ledger",
              file=sys.stderr)
        return

    seen = load_seen()
    print(f"seen postings : {len(seen)}")
    print(f"last run      : {read(LAST) or 'never'}")
    print(f"snoozed       : {read(SNOOZE) or '-'}")
    print(f"reports       : {len(list(REPORTS.glob('*.md'))) if REPORTS.exists() else 0}")
    print(f"state root    : {ROOT}")


if __name__ == "__main__":
    main()
