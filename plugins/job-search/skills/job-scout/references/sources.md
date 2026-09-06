# Sources — where to look, in order, and what actually works

Ordered by yield. Everything here uses **public, unauthenticated endpoints**: no login,
no scraping of a signed-in session, no browser automation for discovery. Sources that were
tried and do not work are listed at the bottom so nobody wastes a run on them.

> **On LinkedIn.** This plugin does not search LinkedIn. Its User Agreement forbids
> automated access, and enforcement lands on the user's own account rather than on us —
> so the trade is a bad one to make on someone else's behalf. A LinkedIn posting that
> reaches you another way is still worth reading, and step 1b of `job-apply` resolves it
> to the employer's own ATS, which is where the application should be made anyway.

---

## Tier 0 — search the open ATS boards first ⭐ the highest-yield source

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
work-authorization language before scoring it. Do this for the **top ~15 candidates only** —
it is the expensive step.

---

## Tested and NOT usable — do not retry

| Source | Result |
|---|---|
| `jobs.ashbyhq.com/<company>` (HTML) | JS-rendered, returns nothing — use the Ashby **API** above |
| `remoterocketship.com` | HTTP 403 to WebFetch |
| Indeed / Glassdoor direct fetch | bot-walled; reach them through WebSearch results instead |

## Rate and etiquette rules

Public endpoints only, and never an authenticated session scraped at volume. Keep the built-in
delays between requests, and identify honestly — the scripts send a plugin User-Agent rather
than impersonating a browser. If a provider starts returning empty pages mid-sweep, stop that
query, report it, and lean on the other tiers for the day. Do not hammer it.

**A posting's listed date is the LISTING date, not the opening date.** A re-listed job looks
brand new. Where a role resolves to a company ATS board, prefer that board's `publishedAt`;
gaps of weeks between the two are common. Do not award freshness points on an aggregator's
date alone for anything you can cross-check.
