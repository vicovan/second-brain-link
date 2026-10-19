#!/usr/bin/env python3
"""
linkedin_jobs.py - read LinkedIn's PUBLIC job search: the list anyone sees logged out.

Discovery only. It reads result cards (title, company, location, posting date, job id) from
the public, no-login search, for every keyword x location in the query grid, limited to what
was posted since the last run. It never logs in, never sends cookies, never opens a job's
apply flow, and never messages anyone. An application is always made at the employer's own
site (job-apply step 1b resolves a LinkedIn posting to it).

Whether to use it is the user's decision, recorded in their search criteria (§3b Sources):
LinkedIn's terms discourage automated access even to public pages, so it runs slowly, with a
request cap, and stops at the first sign of throttling rather than pushing through it.

    python3 linkedin_jobs.py --keywords "Head of Engineering" --keywords "CTO" \
            --location "United Arab Emirates" --location "Switzerland" \
            --since-seconds 259200 --out $SCRATCH/scout-linkedin.json

    --since-seconds N   only postings from the last N seconds (scout_state.py since-seconds)
    --days D            the same, in days (ignored when --since-seconds is given)
    --remote            only roles LinkedIn marks as remote
    --pages P           pages per query, 10 cards each (default 10)
    --delay S           seconds between requests (default 2.5; never below 1.5)
    --max-requests R    hard cap per run (default 150)
    --fixture FILE      parse a saved results page instead of fetching (tests)

Rows use the same shape as ats_pool.py, plus `source`, `market` and `query`.

This reads result LISTS only. A job's own guest page (jobs-guest/jobs/api/jobPosting/<id>)
throttles much sooner - HTTP 429 after roughly 15-20 reads per IP even with a few seconds
between them - so budget about 15 full-posting reads a run, never retry a 429, and read the
rest of each description from the employer's own board (job-apply step 1b).
Zero network outside linkedin.com; stdlib only.
"""
import argparse, html, json, os, re, ssl, sys, time, urllib.error, urllib.parse, urllib.request

UA = "SecondBrainLink-SalesScout/1.0 (+https://secondbrainlink.com; public job listings)"
BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
THROTTLED = {429, 999}


def ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:                                            # noqa: BLE001
        pass
    for ca in ("/etc/ssl/cert.pem", "/usr/local/etc/openssl/cert.pem"):
        if os.path.exists(ca):
            try:
                return ssl.create_default_context(cafile=ca)
            except Exception:                                    # noqa: BLE001
                pass
    return ssl.create_default_context()


CTX = ssl_ctx()


def _text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")).split() and \
        " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split()) or ""


def parse(page):
    """Result cards -> rows. Tolerant: a card missing a field still yields what it has."""
    rows = []
    for chunk in page.split('data-entity-urn="urn:li:jobPosting:')[1:]:
        m = re.match(r"(\d+)", chunk)
        if not m:
            continue
        jid = m.group(1)
        title = re.search(r'class="base-search-card__title"[^>]*>(.*?)</h3>', chunk, re.S)
        comp = re.search(r'class="base-search-card__subtitle"[^>]*>(.*?)</h4>', chunk, re.S)
        loc = re.search(r'class="job-search-card__location"[^>]*>(.*?)</span>', chunk, re.S)
        when = re.search(r'<time[^>]*datetime="([0-9-]{10})"', chunk)
        rows.append({
            "source": "linkedin", "ats": "linkedin", "id": jid,
            "title": _text(title.group(1)) if title else "",
            "company": _text(comp.group(1)) if comp else "",
            "location": _text(loc.group(1)) if loc else "",
            "posted": when.group(1) if when else "",
            "url": f"https://www.linkedin.com/jobs/view/{jid}",
            "comp": "",
        })
    return rows


def fetch(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--keywords", action="append", default=[], help="a title to search (repeatable)")
    ap.add_argument("--location", action="append", default=[], help="a market to search (repeatable)")
    ap.add_argument("--since-seconds", type=int)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--remote", action="store_true")
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument("--max-requests", type=int, default=150)
    ap.add_argument("--fixture")
    ap.add_argument("--out")
    a = ap.parse_args()

    if a.fixture:
        rows = parse(open(a.fixture, encoding="utf-8").read())
        out = json.dumps(rows, indent=2, ensure_ascii=False)
        (open(a.out, "w", encoding="utf-8").write(out) if a.out else print(out))
        print(f"{len(rows)} cards parsed from {a.fixture}", file=sys.stderr)
        return 0
    if not a.keywords or not a.location:
        ap.error("need at least one --keywords and one --location (from the user's criteria)")

    since = a.since_seconds or a.days * 86400
    delay = max(1.5, a.delay)
    seen, rows, requests, throttled = set(), [], 0, False
    for loc in a.location:
        for kw in a.keywords:
            for page in range(max(1, a.pages)):
                if requests >= a.max_requests:
                    print(f"! request cap {a.max_requests} reached — rest of the grid not searched",
                          file=sys.stderr)
                    throttled = True
                    break
                params = {"keywords": kw, "location": loc, "f_TPR": f"r{since}",
                          "sortBy": "DD", "start": page * 10}
                if a.remote:
                    params["f_WT"] = "2"
                if requests:
                    time.sleep(delay)
                status, body = fetch(params)
                requests += 1
                if status in THROTTLED:
                    print(f"! LinkedIn throttled the search (HTTP {status}) — stopped; "
                          f"report it and lean on the other sources today", file=sys.stderr)
                    throttled = True
                    break
                if status != 200:
                    print(f"  {kw} @ {loc} p{page}: HTTP {status}", file=sys.stderr)
                    break
                got = parse(body)
                if not got:
                    break
                for r in got:
                    if r["id"] in seen:
                        continue
                    seen.add(r["id"])
                    r["market"], r["query"] = loc, kw
                    rows.append(r)
            if throttled:
                break
        if throttled:
            break

    out = json.dumps(rows, indent=2, ensure_ascii=False)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(out)
    else:
        print(out)
    print(f"linkedin: {len(rows)} postings from {requests} requests"
          f"{' (stopped early)' if throttled else ''}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
