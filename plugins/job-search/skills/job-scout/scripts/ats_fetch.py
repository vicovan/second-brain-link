#!/usr/bin/env python3
"""
ats_fetch.py - pull open roles straight from a company's ATS public JSON API.

Use this to drill into a specific target company (they post to their own board
days before aggregators pick it up, and the JSON is exact - no scraping).

Usage:
    python3 ats_fetch.py greenhouse <company-slug>
    python3 ats_fetch.py lever <company-slug>
    python3 ats_fetch.py ashby <company-slug>
    python3 ats_fetch.py auto acmecorp          # try all three providers
    python3 ats_fetch.py --batch companies.txt  # 'provider slug' or 'auto slug' lines

    [--filter "cto|vp eng|architect"] [--out jobs.json]

The slug is the last path segment of the company's board URL, e.g.
job-boards.greenhouse.io/<slug>, jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>.
"""
import argparse, json, os, re, ssl, sys, urllib.request

UA = "SecondBrainLink-JobSearch/1.0 (+https://secondbrainlink.com; public job-board APIs only)"

API = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{s}/jobs?content=true",
    "lever":      "https://api.lever.co/v0/postings/{s}?mode=json",
    "ashby":      "https://api.ashbyhq.com/posting-api/job-board/{s}",
}


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


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


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
    for r in out:
        r["source"] = provider
        r["company"] = slug
        r["remote"] = bool(re.search(r"remote", r["location"], re.I))
    return out


def board(provider, slug):
    if provider == "auto":
        for p in ("greenhouse", "lever", "ashby"):
            try:
                rows = norm(p, slug, get(API[p].format(s=slug)))
            except Exception:                                    # noqa: BLE001
                continue
            if rows:
                return rows
        return []
    return norm(provider, slug, get(API[provider].format(s=slug)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("provider", nargs="?", choices=list(API) + ["auto"])
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--batch", help="file of '<provider> <slug>' lines")
    ap.add_argument("--filter", default="", help="regex the title must match (case-insensitive)")
    ap.add_argument("--out")
    a = ap.parse_args()

    targets = []
    if a.batch:
        for line in open(a.batch, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split()
                targets.append((parts[0], parts[1]) if len(parts) > 1 else ("auto", parts[0]))
    if a.provider and a.slug:
        targets.append((a.provider, a.slug))
    if not targets:
        sys.exit("need '<provider> <slug>' or --batch")

    rows = []
    for p, s in targets:
        try:
            got = board(p, s)
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
