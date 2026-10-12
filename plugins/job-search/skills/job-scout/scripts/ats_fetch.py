#!/usr/bin/env python3
"""
ats_fetch.py - pull open roles straight from a company's ATS public JSON API.

Use this to drill into a specific target company (they post to their own board
days before aggregators pick it up, and the JSON is exact - no scraping).

Usage:
    python3 ats_fetch.py greenhouse <company-slug>
    python3 ats_fetch.py lever <company-slug>
    python3 ats_fetch.py ashby <company-slug>
    python3 ats_fetch.py smartrecruiters <CompanyId>
    python3 ats_fetch.py recruitee <subdomain>
    python3 ats_fetch.py personio <subdomain>
    python3 ats_fetch.py teamtailor <subdomain>          # career.<x>.com boards: pass the host
    python3 ats_fetch.py workday <tenant>.<wdN>/<site>    # e.g. acme.wd3/AcmeCareers
    python3 ats_fetch.py auto acmecorp          # try every slug-addressable provider
    python3 ats_fetch.py --batch companies.txt  # 'provider slug' or 'auto slug' lines

    [--filter "cto|vp eng|architect"] [--out jobs.json]

The slug is the last path segment of the company's board URL, e.g.
job-boards.greenhouse.io/<slug>, jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>,
jobs.smartrecruiters.com/<CompanyId>, <slug>.recruitee.com, <slug>.jobs.personio.de,
<slug>.teamtailor.com, and for Workday <tenant>.<wdN>.myworkdayjobs.com/<site>.

Reading a board's job LIST needs no account on any of these, including the ones whose
application form is walled (Workday). Only applying does — the scout surfaces those rows
with the portal named for the user to apply.
"""
import argparse, datetime, html, json, os, re, ssl, sys, urllib.request

UA = "SecondBrainLink-JobSearch/1.0 (+https://secondbrainlink.com; public job-board APIs only)"

API = {
    "greenhouse":      "https://boards-api.greenhouse.io/v1/boards/{s}/jobs?content=true",
    "lever":           "https://api.lever.co/v0/postings/{s}?mode=json",
    "ashby":           "https://api.ashbyhq.com/posting-api/job-board/{s}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=100&offset={o}",
    "recruitee":       "https://{s}.recruitee.com/api/offers/",
    "personio":        "https://{s}.jobs.personio.de/xml",
    "teamtailor":      "https://{s}.teamtailor.com/jobs.rss",
    # verified against the published contract; Workday was in maintenance when this was written
    "workday":         "https://{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
}
# providers `auto` may try from a bare slug (Workday needs tenant + site, so it is never guessed)
AUTO = ("greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "personio", "teamtailor")
PAGE_CAP = 10        # pages per board, so one enormous employer cannot eat a run


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


def get(url, raw=False, body=None):
    headers = {"User-Agent": UA}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        text = r.read().decode("utf-8", "replace")
    return text if raw else json.loads(text)


def _tag(block, name):
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S)
    if not m:
        return ""
    v = m.group(1).strip()
    v = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", v, flags=re.S)
    return html.unescape(v).strip()


def _workday_posted(text, today=None):
    """'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago' / 'Posted 30+ Days Ago' -> date."""
    today = today or datetime.date.today()
    t = (text or "").lower()
    if "today" in t:
        return today.isoformat()
    if "yesterday" in t:
        return (today - datetime.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*day", t)
    return (today - datetime.timedelta(days=int(m.group(1)))).isoformat() if m else ""


def norm(provider, slug, raw):
    out = []
    if provider == "greenhouse":
        for j in raw.get("jobs", []):
            out.append({"title": j.get("title", ""),
                        "location": (j.get("location") or {}).get("name", ""),
                        "url": j.get("absolute_url", ""),
                        "posted": (j.get("updated_at") or "")[:10],
                        "id": str(j.get("id", ""))})
    elif provider == "lever":
        for j in raw if isinstance(raw, list) else []:
            cat = j.get("categories") or {}
            out.append({"title": j.get("text", ""),
                        "location": cat.get("location", ""),
                        "url": j.get("hostedUrl", ""),
                        "posted": "",
                        "id": str(j.get("id", ""))})
    elif provider == "ashby":
        for j in raw.get("jobs", []):
            out.append({"title": j.get("title", ""),
                        "location": j.get("location", ""),
                        "url": j.get("jobUrl") or j.get("applyUrl", ""),
                        "posted": (j.get("publishedAt") or "")[:10],
                        "id": str(j.get("id", ""))})
    elif provider == "smartrecruiters":
        for j in raw:
            loc = j.get("location") or {}
            place = ", ".join(x for x in (loc.get("city"), loc.get("country", "").upper()) if x)
            if loc.get("remote"):
                place = (place + " (remote)").strip()
            out.append({"title": j.get("name", ""), "location": place,
                        "url": f"https://jobs.smartrecruiters.com/{slug}/{j.get('id', '')}",
                        "posted": (j.get("releasedDate") or "")[:10],
                        "id": str(j.get("id", ""))})
    elif provider == "recruitee":
        for j in raw.get("offers", []):
            out.append({"title": j.get("title", ""),
                        "location": j.get("location") or ", ".join(
                            x for x in (j.get("city"), j.get("country")) if x),
                        "url": j.get("careers_url", ""),
                        "posted": (j.get("published_at") or "")[:10],
                        "id": str(j.get("id", ""))})
    elif provider == "personio":
        for b in re.findall(r"<position>(.*?)</position>", raw, re.S):
            jid = _tag(b, "id")
            out.append({"title": _tag(b, "name"), "location": _tag(b, "office"),
                        "url": f"https://{slug}.jobs.personio.de/job/{jid}",
                        "posted": _tag(b, "createdAt")[:10], "id": jid})
    elif provider == "teamtailor":
        for b in re.findall(r"<item>(.*?)</item>", raw, re.S):
            when = _tag(b, "pubDate")
            try:
                posted = datetime.datetime.strptime(when[:16], "%a, %d %b %Y").date().isoformat()
            except ValueError:
                posted = ""
            link = _tag(b, "link")
            out.append({"title": _tag(b, "title"),
                        "location": ", ".join(x for x in (_tag(b, "tt:city"), _tag(b, "tt:country")) if x),
                        "url": link, "posted": posted,
                        "id": (re.search(r"/jobs/(\d+)", link) or [None, ""])[1]})
    elif provider == "workday":
        host, site = slug.split("/", 1)
        for j in raw:
            path = j.get("externalPath", "")
            out.append({"title": j.get("title", ""), "location": j.get("locationsText", ""),
                        "url": f"https://{host}.myworkdayjobs.com/{site}{path}",
                        "posted": _workday_posted(j.get("postedOn", "")),
                        "id": (j.get("bulletFields") or [""])[0] or path.rsplit("_", 1)[-1]})
    for r in out:
        r["source"] = provider
        r["ats"] = provider
        r["board"] = slug
        r["company"] = slug
        r["remote"] = bool(re.search(r"remote", r["location"], re.I))
    return out


def raw_board(provider, slug, search=""):
    """Fetch one board in the provider's own shape (paginated where the API pages)."""
    if provider == "smartrecruiters":
        items = []
        for page in range(PAGE_CAP):
            d = get(API[provider].format(s=slug, o=page * 100))
            items += d.get("content", [])
            if len(items) >= d.get("totalFound", 0) or not d.get("content"):
                break
        return items
    if provider in ("personio", "teamtailor"):
        return get(API[provider].format(s=slug), raw=True)
    if provider == "workday":
        host, site = slug.split("/", 1)
        tenant = host.split(".", 1)[0]
        url = API[provider].format(host=host, tenant=tenant, site=site)
        items = []
        for page in range(PAGE_CAP):
            d = get(url, body={"appliedFacets": {}, "limit": 20, "offset": page * 20,
                               "searchText": search})
            items += d.get("jobPostings", [])
            if len(items) >= d.get("total", 0) or not d.get("jobPostings"):
                break
        return items
    return get(API[provider].format(s=slug))


def board(provider, slug, search=""):
    if provider == "auto":
        for p in AUTO:
            try:
                rows = norm(p, slug, raw_board(p, slug))
            except Exception:                                    # noqa: BLE001
                continue
            if rows:
                return rows
        return []
    return norm(provider, slug, raw_board(provider, slug, search))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("provider", nargs="?", choices=list(API) + ["auto"])
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--batch", help="file of '<provider> <slug> [display name]' lines "
                                    "(companies.py batch writes them)")
    ap.add_argument("--filter", default="", help="regex the title must match (case-insensitive)")
    ap.add_argument("--search", default="",
                    help="free text passed to boards that search server-side (Workday)")
    ap.add_argument("--out")
    a = ap.parse_args()

    targets = []
    if a.batch:
        for line in open(a.batch, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split()
                if len(parts) > 1:
                    targets.append((parts[0], parts[1], " ".join(parts[2:])))
                else:
                    targets.append(("auto", parts[0], ""))
    if a.provider and a.slug:
        targets.append((a.provider, a.slug, ""))
    if not targets:
        sys.exit("need '<provider> <slug>' or --batch")

    rows = []
    for p, s, name in targets:
        try:
            got = board(p, s, a.search)
            for r in got:
                if name:
                    r["company"] = name             # the registry's display name, for merging
        except Exception as e:                                   # noqa: BLE001
            print(f"  ! {p}/{s}: {e}", file=sys.stderr)
            continue
        print(f"  {p}/{s}: {len(got)}", file=sys.stderr)
        rows += got

    if a.filter:
        rx = re.compile(a.filter, re.I)
        rows = [r for r in rows if rx.search(r["title"])]
        print(f"  after --filter: {len(rows)}", file=sys.stderr)

    js = json.dumps(rows, indent=2, ensure_ascii=False)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(js)
        print(f"{len(rows)} -> {a.out}", file=sys.stderr)
    else:
        print(js)


if __name__ == "__main__":
    main()
