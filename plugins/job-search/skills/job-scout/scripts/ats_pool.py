#!/usr/bin/env python3
"""
ats_pool.py - Tier 0 of the daily sweep: bulk-probe company boards on the OPEN ATS
APIs (Ashby, Greenhouse, Lever, plus SmartRecruiters, Recruitee and Personio, which carry
much of DACH and Benelux) and keep only the roles matching the criteria passed in.
Everything it returns is applyable by construction - no account walls.

    python3 ats_pool.py --out <state root>/scratch/ats_pool.json
    python3 ats_pool.py --diagnose          # which slugs resolve at all - NO title filter

Diagnose before concluding a pool is dead: run with a restrictive --titles and most boards
"return nothing" because nothing matched, not because the slug is wrong. And an empty open-ATS
sweep never proves a market is empty - see references/search-method.md.

Slugs come from the built-in list PLUS <state root>/companies.txt, so the pool compounds
as the scout learns new boards. companies.txt lines look like "ashby northwindventures".
"""
import argparse, json, os, pathlib, sys, urllib.request, ssl, re, concurrent.futures as cf

# Identify honestly: these are public job-board APIs, not a browser session.
UA = "SecondBrainLink-JobSearch/1.0 (+https://secondbrainlink.com; public job-board APIs only)"
def ctx():
    try:
        import certifi; return ssl.create_default_context(cafile=certifi.where())
    except Exception: return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
CTX=ctx()
def get(u,t=15):
    r=urllib.request.Request(u,headers={"User-Agent":UA})
    return json.loads(urllib.request.urlopen(r,timeout=t,context=CTX).read().decode())
BOARDS=[("airbyte","ashby"),("alan","ashby"),("algolia","greenhouse"),("anyscale","ashby"),("atlan","ashby"),
("celonis","greenhouse"),("clickhouse","ashby"),("cohere","ashby"),("collibra","greenhouse"),("commercetools","greenhouse"),
("confluent","ashby"),("cresta","greenhouse"),("databricks","greenhouse"),("dataiku","greenhouse"),("decagon","ashby"),
("deepl","ashby"),("doctolib","ashby"),("elastic","greenhouse"),("elevenlabs","ashby"),("fireworks","ashby"),
("fivetran","greenhouse"),("gitlab","greenhouse"),("gocardless","greenhouse"),("grafanalabs","greenhouse"),("jetbrains","greenhouse"),
("langchain","ashby"),("miro","ashby"),("modal","ashby"),("monzo","greenhouse"),("paddle","ashby"),("pinecone","ashby"),
("pleo","ashby"),("prefect","ashby"),("qonto","ashby"),("semgrep","ashby"),("sierra","ashby"),("sonarsource","lever"),
("sumup","greenhouse"),("supabase","ashby"),("synthesia","ashby"),("tailscale","greenhouse"),("tide","greenhouse"),
("typeform","greenhouse"),("vercel","greenhouse"),("weaviate","ashby"),("wise","greenhouse"),("wolt","greenhouse"),("writer","ashby")]
# --- filters. NEUTRAL DEFAULTS ONLY -----------------------------------------
# Every pattern here is a broad starting point, never a statement about what any
# particular person wants. WHAT TO SEARCH FOR AND WHAT TO EXCLUDE BELONGS IN THE
# USER'S OWN PROFILE (`45-jobs/profile/search-criteria.md` §1/§3/§5), which the
# scout passes in with the flags below. Anything domain- or geography-specific
# hardcoded here would silently override the profile for every user of the plugin.
#
#   --titles          regex of role titles to KEEP   (seniority band)
#   --domain          regex of role titles to KEEP   (discipline)
#   --exclude-titles  regex of role titles to DROP
#   --regions         regex of locations to KEEP
#   --exclude-regions regex of locations to DROP unless they also match --regions
SENIOR = re.compile(r'\b(cto|chief|vp\b|vice president|head of|principal|staff|director|lead|architect|distinguished)\b', re.I)
# Broad by design: narrowing to a discipline is the profile's job, via --domain.
DOMAIN = re.compile(r'.', re.I)
REGIONS = re.compile(r'.', re.I)
EXCLUDE_REGIONS = re.compile(r'(?!x)x', re.I)   # matches nothing until asked
# Job-TYPE noise only — never an industry or a domain. A user who wants to exclude a
# sector says so in their profile; encoding one person's sector exclusions here would
# apply them to everybody.
BAD = re.compile(r'\b(intern|internship|apprentice|graduate|working student|assistant|recruiter|contractor)\b', re.I)
# Pre-sales and delivery-consulting titles wearing an architect's hat. Large vendors flood the
# boards with these; they are field roles, not engineering leadership, and they can easily be
# the majority of what a Tier 0 sweep returns. Drop them unless the profile asks for field work.
PRESALES = re.compile(r'solutions? architect|deployment architect|delivery (solutions?|architect)|forward deployed|value engineer|pre-?sales|customer success|technical account|specialist solutions|field engineer|consultant', re.I)


def pull(pair):
    s,ats=pair; out=[]
    try:
        if ats=="ashby":
            d=get(f"https://api.ashbyhq.com/posting-api/job-board/{s}?includeCompensation=true")
            rows=[(j.get("title",""),j.get("location") or "",(j.get("compensation") or {}).get("compensationTierSummary") or "",j.get("jobUrl",""),(j.get("publishedAt") or "")[:10]) for j in d.get("jobs",[])]
        elif ats=="greenhouse":
            d=get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs")
            rows=[(j.get("title",""),(j.get("location") or {}).get("name",""),"",j.get("absolute_url",""),(j.get("first_published") or j.get("updated_at") or "")[:10]) for j in d.get("jobs",[])]
        elif ats=="lever":
            d=get(f"https://api.lever.co/v0/postings/{s}?mode=json")
            rows=[(j.get("text",""),(j.get("categories") or {}).get("location","") or "","",j.get("hostedUrl",""),_ms_date(j.get("createdAt"))) for j in d]
        else:
            # The other open providers share ats_fetch.py's fetchers - one implementation.
            from ats_fetch import board
            rows=[(r["title"],r["location"],"",r["url"],r["posted"]) for r in board(ats,s)]
    except Exception: return out
    if DIAGNOSE:
        return [{"ats":ats,"company":s,"title":"(board resolved)","location":"","comp":"","url":"","posted":"","jobs":len(rows)}]
    for t,loc,comp,u,dt in rows:
        blob=t+" "+loc
        if not SENIOR.search(t) or not DOMAIN.search(t): continue
        if BAD.search(blob) or PRESALES.search(t): continue
        if not REGIONS.search(loc): continue
        if EXCLUDE_REGIONS.pattern != '(?!x)x' and EXCLUDE_REGIONS.search(loc) \
           and not REGIONS.search(loc): continue
        out.append({"ats":ats,"company":s,"title":t,"location":loc,"comp":comp,"url":u,"posted":dt})
    return out
DIAGNOSE = False
PROVIDERS = ("ashby", "greenhouse", "lever", "smartrecruiters", "recruitee", "personio")


def _ms_date(ms):
    import datetime
    try:
        return datetime.datetime.utcfromtimestamp(int(ms) / 1000).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def state_root():
    """Delegates to paths.py — the single resolver. Kept as a function so callers
    that already import `state_root` keep working."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from paths import state_root
    return state_root()


def extra_boards(path):
    """Read '<provider> <slug>' lines from companies.txt so the pool grows over time."""
    out = []
    if not path or not os.path.isfile(path):
        return out
    for line in open(path, encoding="utf-8"):
        line = line.split("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] in PROVIDERS:
            out.append((parts[1], parts[0]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="write JSON here (default: <state>/ats_pool.json)")
    ap.add_argument("--companies", default=None, help="companies.txt (default: <state>/companies.txt)")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--regions", default=None,
                    help="regex of locations to KEEP — defaults to everywhere. "
                         "Set it from the user's profile/search-criteria.md §3.")
    ap.add_argument("--exclude-regions", default=None,
                    help="regex of locations to DROP unless they also match --regions")
    ap.add_argument("--titles", default=None,
                    help="regex of role titles to KEEP (seniority band) — from profile/search-criteria.md §1")
    ap.add_argument("--domain", default=None,
                    help="regex of role titles to KEEP (discipline) — from profile/search-criteria.md §1. "
                         "USE WORD BOUNDARIES: a bare 'ai' matches 'Retail' and lets the whole "
                         "sales board through. Write '\\bai\\b|machine learning' instead.")
    ap.add_argument("--exclude-titles", default=None,
                    help="regex of role titles to DROP — from profile/search-criteria.md §5 exclusions")
    ap.add_argument("--diagnose", action="store_true",
                    help="report which boards resolve and how many jobs each lists, ignoring every "
                         "title/region filter - use it before declaring slugs dead")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    global REGIONS, DIAGNOSE, EXCLUDE_REGIONS, SENIOR, DOMAIN, BAD
    DIAGNOSE = a.diagnose
    if a.regions:
        REGIONS = re.compile(a.regions, re.I)
    if a.exclude_regions:
        EXCLUDE_REGIONS = re.compile(a.exclude_regions, re.I)
    if a.titles:
        SENIOR = re.compile(a.titles, re.I)
    if a.domain:
        DOMAIN = re.compile(a.domain, re.I)
    if a.exclude_titles:
        # ADD to the neutral noise filter rather than replacing it.
        BAD = re.compile(BAD.pattern + '|' + a.exclude_titles, re.I)

    root = state_root()
    out_path = a.out or str(root / "ats_pool.json")
    comp_file = a.companies or str(root / "companies.txt")

    boards, seen = [], set()
    for pair in BOARDS + extra_boards(comp_file):
        if pair not in seen:
            seen.add(pair); boards.append(pair)

    raw, hit = [], 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for rows in ex.map(pull, boards):
            if rows:
                hit += 1
            raw.extend(rows)

    if DIAGNOSE:
        print(f"{hit} of {len(boards)} boards resolved (no filters applied):")
        for r in sorted(raw, key=lambda x: -x["jobs"]):
            print(f"  {r['ats']:16} {r['company']:28} {r['jobs']:4} jobs")
        dead = sorted(set(b for b, _ in boards) - {r["company"] for r in raw})
        if dead:
            print(f"\n{len(dead)} did not resolve - try slug variants (hyphenated, -bank, -io, -ltd, "
                  f"-hq, the product name, the legal name) before dropping them:\n  " + " ".join(dead))
        return

    # One row per (company, title). Celonis alone posts "Principal Enterprise Architect" in nine
    # cities; nine identical rows is noise, one row listing the cities is a decision.
    merged = {}
    for r in raw:
        k = (r["company"], r["title"].strip().lower())
        if k in merged:
            locs = merged[k]["location"].split(" / ")
            if r["location"] and r["location"] not in locs:
                merged[k]["location"] = " / ".join(locs + [r["location"]])
                # Each city is often its own req with its own band, language and visa questions.
                # The merged string is a summary - read the req for the city you score.
                merged[k]["multi_city"] = True
        else:
            merged[k] = r
    res = list(merged.values())

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    json.dump(res, open(out_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"{len(boards)} boards probed, {hit} returned matches -> {out_path}", file=sys.stderr)
    print(f"{len(res)} roles matched your criteria, on OPEN ATS forms:\n")
    if not a.quiet:
        for r in sorted(res, key=lambda x: (x["company"], x["title"])):
            print(f"  [{r['ats'][:2]}] {r['company'][:14]:16}| {r['title'][:48]:50}| "
                  f"{r['location'][:28]:30}| {r['comp'][:20]}")


if __name__ == "__main__":
    main()
