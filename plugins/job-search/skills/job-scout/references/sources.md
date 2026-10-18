# Sources — where to look, in order, and what actually works

**The sweep runs market → companies → careers sites.** Discovery finds who is hiring in every
target market, from several independent sources; the company registry remembers each employer
and its careers board; the careers-site sweep pulls the full list at the source, where the real
posting date and apply link live. **Which sources serve which market is in
`regional-sources.md`** — read it for every market in the user's criteria §3. A market that
comes back empty from one source has not been searched (`scout_state.py coverage`).

Everything here reads **public listings**. Nothing logs in to a job board, creates an account,
or applies through an aggregator — the application is always made at the employer's own site.
Sources that were tried and do not work are listed at the bottom.

> **On LinkedIn — the user's choice, recorded in criteria §3b Sources.**
> - **Public search (`linkedin_jobs.py`)** reads LinkedIn's no-login job search: the list anyone
>   sees logged out. No account is used, so nothing can land on the user's account. LinkedIn's
>   terms still discourage automated access even to public pages, so the script is slow on
>   purpose (≥1.5 s between requests), capped per run, identifies itself honestly, and stops at
>   the first throttle (HTTP 429/999) instead of pushing through it. Onboarding asks before
>   turning it on.
> - **Signed-in browser read** — only when the user asks for a deep look, only if criteria §3b
>   allows it, and only read-only result pages in their own Chrome: never apply, message, connect
>   or "Easy Apply". Any enforcement here would land on the user's own account; say so when asked.
>   **Pace and stop rules — no exceptions:** read at a human pace (a few seconds per page), page
>   through the result list with the page's own controls (about 10 pages per search is plenty), and
>   keep to a handful of searches a day. No scripted fetches against the signed-in session, no hidden
>   iframes, no parallel tabs paging the same search, no profile edits. **A warning banner, a CAPTCHA
>   or an HTTP 429 ends LinkedIn for the day.** Anything beyond reading — an Easy Apply submit,
>   revealing a hidden apply link, a message — is handed to the user as exact steps ("in the tab
>   *LinkedIn — <title>*, click *Apply*, then …"); the agent never does it.
> - **Easy Apply vs external apply.** A row whose apply button leads off LinkedIn is resolved to
>   the employer's form and applied to there. An *Easy Apply*-only row (often an agency repost with
>   the client unnamed) gets the tailored CV and answers prepared, and the user submits it on
>   LinkedIn. Job alerts the user forwards are resolved to the employer first, too: alerts often
>   carry agency and aggregator reposts rather than the employer itself.
> - **Full postings throttle sooner than lists.** The public per-job page returns HTTP 429 after
>   roughly 15–20 reads per IP. Budget about 15 a run and read the rest at the employer's board.
> - Either way, a LinkedIn posting is **resolved to the employer's own careers site**
>   (`job-apply` step 1b) before it is scored for applyability.

---

## Tier 0 — discovery: who is hiring, in every target market

Run the query grid — every lane title and its synonyms (criteria §1) × every market (criteria §3)
— against every source in that market's pack (`regional-sources.md`), time-limited to what was
posted since the last run:

```bash
SINCE=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py since-seconds)
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/linkedin_jobs.py --since-seconds "$SINCE" \
        --keywords "<lane title>" --keywords "<synonym>" ... \
        --location "<market>" ... --out $SCRATCH/scout-linkedin.json
```
Regional boards that block automated reading (`chrome` / `search` routes) are read in the user's
browser when criteria §3b allows it, otherwise through `site:` searches; write what they give into
`$SCRATCH/scout-<board>.json` in the same row shape (`company`, `title`, `location`, `posted`, `url`,
`source`, `market`).

## Tier 1 — the company registry: every employer's own board

Every company discovery names goes into the registry, which remembers its careers board:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/companies.py add < $SCRATCH/scout-merged.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/companies.py unresolved   # find + `set` their boards
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/companies.py batch > $SCRATCH/boards.txt
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/ats_fetch.py --batch $SCRATCH/boards.txt \
        --filter "<lane regex>" --out $SCRATCH/scout-careers.json
```
For an unresolved company: `WebSearch "<company> careers"`, classify the page with
`job-apply/scripts/detect_portal.py`, then `companies.py set "<company>" --ats <type> --slug <slug>`
(or `--careers <url>` for a board no adapter reads — then `WebFetch` / Chrome it). The registry
compounds: by the second week most hiring companies in a market are one API call away.

**Walled boards are read, not skipped.** Reading a Workday or SuccessFactors job list needs no
account; only applying does. With criteria `walled: surface` (the default) such rows stay on the
shortlist with the portal named, for the user to apply there.

## Tier 1b — the open ATS pool (US and EU tech)

**The problem this solves:** a broad job-board sweep finds good roles and *then* discovers
half of them sit behind Workday / Eightfold / Phenom account walls the user cannot use. That
wastes shortlist slots. **Invert it — start from boards that are open by construction.**

Two ways, use both:

**(a) Site-restricted search** — finds roles at companies you would not have thought of:
```
site:jobs.lever.co "<lane A title>" OR "<lane B title>" <region> remote
site:job-boards.greenhouse.io "<lane A title>" OR "<lane B title>" <city> OR <city>
site:jobs.ashbyhq.com "<lane A title>" OR "<lane B title>" <region> remote
site:jobs.smartrecruiters.com "<lane A title>" OR "<lane B title>"
```
Build the titles from `profile/search-criteria.md` §1 and the geographies from §3 — never
from a list hardcoded here. Search indexes go stale: **always confirm the role is still on
the live board** before it reaches a shortlist. Expect a meaningful share of the best-looking
hits to be already closed.

**(b) Bulk-probe company boards via the public APIs** — the reliable one. Run a list of
company slugs against all three APIs concurrently, then filter by title, geography and the
user's exclusions. `scripts/ats_pool.py` does this and typically resolves roughly two thirds
of a slug list into live roles on open forms in a single pass. Add every good slug found to
`<state root>/companies.txt` so the list compounds across runs.

A starter slug list ships in `ats_pool.py` (well-known companies that publish to Greenhouse,
Lever or Ashby). It is a seed, not a recommendation — replace it with the companies in the
user's own target market as `companies.txt` grows.

**Filter out the noise this produces:** large vendors post dozens of near-identical
*Solutions Architect* / *Delivery Architect* roles — these are **pre-sales**, not engineering
leadership. Exclude `solutions architect`, `delivery architect`, `customer architect`,
`partner architect` unless the user specifically wants field work.

## Tier 1 — a named company's ATS board (exact, and earliest)

Companies publish to their own ATS days before aggregators index it, and the JSON is
authoritative. `scripts/ats_fetch.py` covers the three that matter:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/ats_fetch.py greenhouse <slug> --filter "cto|vp|head of|architect"
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/ats_fetch.py auto <slug>       # tries all three
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/ats_fetch.py --batch companies.txt --filter "..."
```

| Provider | Public API | Verified |
|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true` | ✅ |
| Lever | `api.lever.co/v0/postings/<slug>?mode=json` | ✅ |
| Ashby | `api.ashbyhq.com/posting-api/job-board/<slug>` | ✅ |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/<CompanyId>/postings` | ✅ |
| Recruitee | `<slug>.recruitee.com/api/offers/` | ✅ |
| Personio | `<slug>.jobs.personio.de/xml` | ✅ |
| Teamtailor | `<slug>.teamtailor.com/jobs.rss` | ✅ |
| Workday | `POST <tenant>.<wdN>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs` | ⚠️ built to the published contract; unverified (Workday was in maintenance when added) — on failure, `WebFetch` / Chrome the careers page |

Use this as a **drill-down**, not a sweep: when another tier surfaces an interesting company,
pull its whole board to see everything else open there.

## Tier 2 — WebSearch (aggregators, founder programmes, and anything niche)

`WebSearch` is the right tool for founder programmes, EIR and accelerator tracks, and for
aggregators that block direct fetching. Useful landing spots: `wellfound.com`,
`startup.jobs`, `remotive.com`, plus VC and venture-studio programme pages.

Query patterns that work — fill the titles and geography from the user's own criteria:
- `"<lane A title>" OR "<lane B title>" remote <region> <sector> hiring <month year>`
- `entrepreneur in residence EIR program <year> apply venture studio <region>`
- `site:wellfound.com <title> remote <region>`
- `<company name> careers <title>` — to find a company's board slug for Tier 1.

## Tier 3 — Y Combinator jobs ⚠️

**https://www.ycombinator.com/jobs** — YC portfolio roles: AI-native, well-funded, often
remote-friendly. The filter pages are public and fetchable:

```
https://www.ycombinator.com/jobs/role/engineering
https://www.ycombinator.com/jobs/role/engineering?remote=true
https://www.ycombinator.com/jobs             (all roles)
```

**Two honest caveats — check these before promising the user anything from here:**
1. **The apply flow is an account wall.** "Apply" goes to `account.ycombinator.com/authenticate`
   → `workatastartup.com/application`, and this plugin never creates an account. If the user is
   already logged into `workatastartup.com`, the form can be driven from there — ask rather than
   assume. Otherwise it is a hand-off: build the CV and answers, they submit.
2. **The public role pages skew junior/IC.** Senior roles are mostly behind the
   `workatastartup.com` filters, which need the login. Sweep it, but do not expect it to carry
   a senior shortlist on its own.

Also worth a WebSearch pass: `site:workatastartup.com "<lane A title>" remote <region>`.

## Tier 4 — WebFetch on a specific posting

Once a job is shortlisted, `WebFetch` the posting URL to read the real requirements, comp and
work-authorization language before scoring it. Do this for the **top ~2× the shortlist target only** (`learn.py target`) —
it is the expensive step.

---

## Tested and NOT usable — do not retry

| Source | Result |
|---|---|
| `jobs.ashbyhq.com/<company>` (HTML) | JS-rendered, returns nothing — use the Ashby **API** above |
| `remoterocketship.com` | HTTP 403 to WebFetch |
| Indeed / Glassdoor direct fetch | bot-walled; reach them through WebSearch results instead |
| Bayt, GulfTalent direct fetch | HTTP 403 — read them in the user's Chrome (criteria §3b) or via `site:` search |
| Workable public API | no public listing API — `WebFetch` `apply.workable.com/<slug>` or search. The `apply.workable.com/api/v1/widget/accounts/<slug>` endpoint returns HTTP 200 with a not-found body for **any** string, so it cannot be used to probe whether a slug exists |
| Workday / SuccessFactors / iCIMS by slug-guessing | large corporates keep these behind their own careers domain; slug probing finds startups only. Find the employer first, then its portal |
| Search-index and aggregator hits as proof a role is open | they go stale fast; a role that ranks in WebSearch is often gone from the board. Confirm on the employer's live board or API before it reaches a shortlist |

## Rate and etiquette rules

Public endpoints only, and never an authenticated session scraped at volume. Keep the built-in
delays between requests, and identify honestly — the scripts send a plugin User-Agent rather
than impersonating a browser. If a provider starts returning empty pages mid-sweep, stop that
query, report it, and lean on the other tiers for the day. Do not hammer it.

**Enterprise portals that can be read without an account.** Reading a list needs no login even
where applying does:
- **Phenom** career sites (`careers.<company>.com`, JS-rendered) answer `POST /widgets` with a JSON
  body: `ddoKey: "refineSearch"` for the list, `ddoKey: "jobDetail"` plus `jobId` for a description.
  This beats WebFetch, which sees only the JS shell. Multi-unit groups often expose one site per
  unit at `<host>/<unit>/widgets`.
- **SuccessFactors** career sites usually publish `/sitemap.xml` listing every job URL when the
  search page is JS-rendered.
- **Workday**: `ats_fetch.py workday <host>/<site>` (the public CXS JSON).

**Recruiter and aggregator pages carry other listings.** A recruiter's job page often shows
"similar jobs" or "other people applied" with *their* salaries and titles beside this one. Never
take a salary from a regex over the page; read this job's own text, and treat comp as not posted
unless it appears there. `knockout.py` cuts the page at the usual sidebar headings, but check
which listing a matched sentence belongs to.

**A posting's listed date is the LISTING date, not the opening date.** A re-listed job looks
brand new. Where a role resolves to a company ATS board, prefer that board's `publishedAt`;
gaps of weeks between the two are common. Do not award freshness points on an aggregator's
date alone for anything you can cross-check.
