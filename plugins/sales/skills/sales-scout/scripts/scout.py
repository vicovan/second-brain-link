#!/usr/bin/env python3
"""
scout.py - the lead sweep's memory: what was searched, what came back, what is new.

The sweep runs market -> companies -> their own sites (the job-scout method). Every source
writes its rows to a JSON file; this script merges them into the account registry, one
account per company across every source, and decides whether each market was actually
searched (the coverage gate).

    scout.py since-seconds              seconds back to search: since the last run + one day,
                                        14 days on a first run, never more than 30
    scout.py merge F [F ...]            normalise every source's rows into signals, keep the
                                        in-lane ones (the profile's own roles and markets), upsert
                                        accounts, mark new vs seen, write coverage
    scout.py coverage [--json]          a verdict per market. Exit 1 on any FAILURE
    scout.py unresolved [--limit 15]    leads with no domain yet - resolve "<company> official site"
    scout.py mark-run                   stamp today as a completed sweep; what today's shortlist
                                        showed is marked reviewed (tomorrow it is "still open")
    scout.py starter                    the first view, with NO network: the leads the brain
                                        already holds, scored and shortlisted, and the layer
                                        rendered - what Studio opens before any sweep has run
    scout.py stats

A source file is either a list of rows or {"source": S, "markets": [M...], "rows": [...]}.
Declare `markets` when a source was searched and returned nothing: an empty search still
counts as a searched source, which is what lets the gate tell "thin" from "never looked".

Row shapes it understands:
    job rows (linkedin_jobs.py, ats_fetch.py)   {title, company, location, posted, url}
                                                -> a `hiring` signal when the title matches
                                                   a buyer or need role in icp.md
    signal rows (written by the agent)          {company, domain?, market?, kind, what, url,
                                                 seen, source, location?}
    account rows (warm_rank.py)                 {name, origin, contacts, signals, ...}

Coverage verdicts (per market):
    ok        3+ sources searched
    partial   fewer than 3 sources searched, but qualified leads came back
    failure   no qualified leads from fewer than 3 sources - widen before going on
    thin      no qualified leads across 3+ sources - only now may a market be called thin
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import sales_profile as prof  # noqa: E402

KINDS = ("hiring", "funding", "exec_hire", "migration", "expansion", "event", "intent",
         "news", "directory", "registry", "brain", "revival", "lookalike")
NOT_A_COMPANY = {"confidential", "stealth", "undisclosed", "anonymous", "a client", "our client"}


def state_file():
    return ledger.root() / "scout_state.json"


def load_state():
    try:
        return json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(s):
    f = state_file()
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(f)


def since_seconds(st, today=None):
    today = today or datetime.date.today()
    last = st.get("last_run")
    try:
        days = (today - datetime.date.fromisoformat(last)).days + 1
    except (TypeError, ValueError):
        days = 14
    return max(1, min(days, 30)) * 86400


def role_regex(icp_s):
    words = prof.as_list(icp_s.get("buyer_roles")) + prof.as_list(icp_s.get("need_roles")) \
        + prof.as_list(icp_s.get("champion_roles"))
    if not words:
        return None
    return re.compile("|".join(re.escape(w) if not re.search(r"[|()\\\[]", w) else w for w in words), re.I)


def market_of(row, mk):
    if row.get("market"):
        return row["market"]
    hay = " ".join(str(row.get(k) or "") for k in ("location", "what", "title", "about", "country", "city"))
    for name, rx in mk.items():
        if rx.search(hay):
            return name
    return ""


def domain_of(url):
    m = re.match(r"^https?://([^/]+)", url or "")
    if not m:
        return ""
    host = re.sub(r"^www\.", "", m.group(1).lower())
    # an aggregator's host is never the company's domain
    if re.search(r"linkedin\.com|greenhouse\.io|lever\.co|ashbyhq\.com|smartrecruiters\.com|"
                 r"recruitee\.com|personio\.|teamtailor\.com|myworkdayjobs\.com|google\.|"
                 r"crunchbase\.com|ycombinator\.com|x\.com|twitter\.com|reddit\.com|"
                 r"news\.ycombinator\.com|medium\.com|substack\.com", host):
        return ""
    return host


def normalise(row, source, mk, roles, today):
    """One source row -> an account record with one signal, or None when out of lane."""
    if row.get("origin") and row.get("name"):           # a warm_rank account row
        rec = dict(row)
        rec.setdefault("sources", [source])
        if not rec.get("markets"):
            m = market_of({"location": " ".join(c.get("location", "") for c in row.get("contacts", []))}, mk)
            rec["markets"] = [m] if m else []
        return rec
    company = (row.get("company") or row.get("name") or "").strip()
    if not company or company.lower() in NOT_A_COMPANY:
        return None
    kind = row.get("kind") or ("hiring" if row.get("title") else "news")
    if kind not in KINDS:
        kind = "news"
    what = row.get("what") or row.get("title") or ""
    if kind == "hiring" and roles is not None and not roles.search(what):
        return None                                      # a job posting, but not one that signals need
    market = market_of(row, mk)
    if mk and not market:
        return None                                      # outside every market the seller sells in
    seen = str(row.get("seen") or row.get("posted") or today)[:10]
    url = row.get("url") or ""
    # a URL names the company's domain only when the row says it is the company's own page
    # (a press article's host is the publisher, a job board's host is the board)
    domain = row.get("domain") or (domain_of(url) if row.get("own_site") else "")
    rec = {"name": company, "domain": domain, "sources": [source],
           "markets": [market] if market else [], "origin": "cold",
           "signals": [{"kind": kind, "what": what, "url": url, "seen": seen, "source": source}]}
    for f in ("industry", "size", "about", "tz", "region", "location"):
        if row.get(f):
            rec[f] = row[f]
    if row.get("form_url"):
        rec["form"] = {"url": row["form_url"], "platform": row.get("form_platform", "")}
    if row.get("contacts"):
        rec["contacts"] = row["contacts"]
    return rec


def merge(files, today=None):
    today = today or datetime.date.today().isoformat()
    icp_s = prof.icp()
    mk, roles = prof.markets(icp_s), role_regex(icp_s)
    acc = ledger.load_accounts()
    cov = {m: {"sources": {}, "qualified": 0} for m in mk}
    n_rows = n_kept = n_new = 0
    new_keys, touched = set(), set()
    for f in files:
        try:
            data = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"  ! {f}: {e}", file=sys.stderr)
            continue
        if isinstance(data, dict):
            source = data.get("source") or pathlib.Path(f).stem.replace("scout-", "")
            declared, rows = data.get("markets") or [], data.get("rows") or []
        else:
            source = pathlib.Path(f).stem.replace("scout-", "")
            declared, rows = [], data
        for m in declared:
            cov.setdefault(m, {"sources": {}, "qualified": 0})["sources"].setdefault(source, 0)
        for r in rows:
            if not isinstance(r, dict):
                continue
            n_rows += 1
            src = r.get("source") or source
            rec = normalise(r, src, mk, roles, today)
            if rec is None:
                continue
            n_kept += 1
            cur, is_new = ledger.upsert(acc, rec, today)
            if cur is None:
                continue
            touched.add(cur["key"])
            if is_new:
                new_keys.add(cur["key"])
                n_new += 1
            for m in rec.get("markets") or [""]:
                if not m:
                    continue
                c = cov.setdefault(m, {"sources": {}, "qualified": 0})
                c["sources"][src] = c["sources"].get(src, 0) + 1
    for a in acc.values():                        # "new" means new in THIS merge, nothing older
        a["new"] = a["key"] in new_keys
    for k in touched:
        a = acc[k]
        for m in a.get("markets") or []:
            if m in cov:
                cov[m]["qualified"] += 1
    ledger.save_accounts(acc)
    for m, c in cov.items():
        c["verdict"] = verdict(c)
    st = load_state()
    st.update({"merged_at": today, "coverage": cov, "rows": n_rows, "kept": n_kept,
               "new": n_new, "accounts": len(touched),
               "sources": sorted({s for c in cov.values() for s in c["sources"]})})
    save_state(st)
    for k in new_keys:
        ledger.log("sourced", account=k, sources=acc[k].get("sources"))
    return st


def verdict(c):
    n = len(c["sources"])
    if n >= 3:
        return "ok" if c["qualified"] else "thin"
    return "partial" if c["qualified"] else "failure"


def coverage_table(st):
    cov = st.get("coverage") or {}
    lines = ["| Market | Sources searched | Qualified accounts | Verdict |", "|---|---|---|---|"]
    glyph = {"ok": "✓ ok", "partial": "⚠ partial", "failure": "✗ FAILURE — widen", "thin": "thin (3+ sources)"}
    for m in sorted(cov):
        c = cov[m]
        srcs = ", ".join(f"{s} ({n})" for s, n in sorted(c["sources"].items())) or "—"
        lines.append(f"| {m} | {len(c['sources'])}: {srcs} | {c['qualified']} | {glyph.get(c.get('verdict'), c.get('verdict'))} |")
    return "\n".join(lines)


def summary_line(st):
    cov = st.get("coverage") or {}
    return (f"Swept {st.get('accounts', 0)} companies from {len(st.get('sources') or [])} sources "
            f"across {len(cov)} markets — {st.get('new', 0)} new since the last run")


def starter(n=10):
    """Brain leads only (warm_rank), merged, scored, shortlisted, rendered. Zero network.

    Before onboarding there is no floor worth applying, so the starter shows the best reachable
    brain leads (up to n) and says that it is a preview; after onboarding it is the normal floor."""
    import warm_rank  # noqa: PLC0415
    import lead_score  # noqa: PLC0415
    import render_sales  # noqa: PLC0415
    from paths import brain_at_cwd  # noqa: PLC0415
    b = brain_at_cwd()
    rows = warm_rank.rank(b) if b else []
    f = ledger.root() / "scout-brain.json"
    f.write_text(json.dumps({"source": "brain", "markets": [], "rows": rows}, ensure_ascii=False), encoding="utf-8")
    st = merge([str(f)])
    acc, _ = lead_score.score_all()
    onboarded = not prof.missing()
    s = lead_score.shortlist(acc, None if onboarded else n, include_seen=True)
    if not onboarded:
        live = [a for a in acc.values() if a.get("stage", "lead") == "lead" and not a.get("knocked_out")
                and a.get("reach") != "handoff"]
        live.sort(key=lambda a: (-(a.get("score") or 0), a["name"].lower()))
        s["shortlist"] = live[:n]
    out = {"floor": s["floor"], "target": s["target"], "below_floor": s["below_floor"], "starter": True,
           "onboarded": onboarded,
           "shortlist": [lead_score._brief(x) for x in s["shortlist"]],
           "knocked_out": [lead_score._brief(x) for x in s["knocked_out"]],
           "unreachable": [lead_score._brief(x) for x in s["unreachable"]], "still_open": []}
    (ledger.root() / "last_shortlist.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    w = render_sales.render()
    return len(rows), len(out["shortlist"]), w


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("since-seconds")
    g = sub.add_parser("merge"); g.add_argument("files", nargs="+")
    g = sub.add_parser("coverage"); g.add_argument("--json", action="store_true")
    g = sub.add_parser("unresolved"); g.add_argument("--limit", type=int, default=15)
    sub.add_parser("mark-run")
    g = sub.add_parser("starter"); g.add_argument("--n", type=int, default=10)
    sub.add_parser("stats")
    a = ap.parse_args(argv)
    st = load_state()
    if a.cmd == "since-seconds":
        print(since_seconds(st))
        return 0
    if a.cmd == "merge":
        st = merge(a.files)
        print(summary_line(st) + ".", file=sys.stderr)
        print(coverage_table(st))
        return 0
    if a.cmd == "coverage":
        if a.json:
            print(json.dumps(st.get("coverage") or {}, indent=2, ensure_ascii=False))
        else:
            print(summary_line(st) + ".")
            print(coverage_table(st))
        bad = [m for m, c in (st.get("coverage") or {}).items() if c.get("verdict") == "failure"]
        if bad:
            print(f"COVERAGE FAILURE in {', '.join(sorted(bad))}: fewer than 3 sources and no "
                  f"qualified leads. Widen (the next source in the market's pack, a role-synonym "
                  f"pass, lookalikes) and merge again before calling it thin.", file=sys.stderr)
            return 1
        return 0
    if a.cmd == "unresolved":
        acc = ledger.load_accounts()
        todo = [v for v in acc.values() if v.get("stage") == "lead" and not v.get("domain")]
        todo.sort(key=lambda v: (-len(v.get("signals") or []), v["name"].lower()))
        print(json.dumps([{"key": v["key"], "name": v["name"], "markets": v.get("markets"),
                           "signals": len(v.get("signals") or [])} for v in todo[:a.limit]],
                         indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "starter":
        n_rows, n_short, w = starter(a.n)
        print(f"starter: {n_rows} accounts from your brain, {n_short} on the first list; "
              f"rendered {w.written} files")
        return 0
    if a.cmd == "mark-run":
        today = datetime.date.today().isoformat()
        st["last_run"] = today
        save_state(st)
        # what today's report showed is now "reviewed": tomorrow it is still open, not news
        try:
            shown = json.loads((ledger.root() / "last_shortlist.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            shown = {}
        keys = {x.get("key") for x in shown.get("shortlist") or []}
        if keys:
            acc = ledger.load_accounts()
            for k in keys:
                if k in acc and not acc[k].get("reviewed"):
                    acc[k]["reviewed"] = today
            ledger.save_accounts(acc)
        return 0
    acc = ledger.load_accounts()
    by = {}
    for v in acc.values():
        by[v.get("stage", "lead")] = by.get(v.get("stage", "lead"), 0) + 1
    print(f"last run: {st.get('last_run') or 'never'} · accounts {len(acc)} · " +
          " · ".join(f"{k} {n}" for k, n in sorted(by.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
