# Search method — how to run a sweep for anyone

**What to search for is not here.** Lanes, titles, geographies, the compensation floor and the hard
exclusions all live in the user's `profile/search-criteria.md`; the numbers live in
`profile/scoring.md`. This file is the procedure that turns those into a shortlist, and it is the
same procedure for every user.

If no profile is reachable, **stop and run onboarding**. Never guess a compensation floor, a
location or a target title — a shortlist built on invented criteria wastes the user's whole day.

## 1. Freshness and volume

Sweep the last **4–5 days** by default, widening from whatever `scout_state.py window` reports since
the last run. **Always deliver the full target count** (ten by default) — if fewer clear the bar,
widen the search before you shorten the list, then say plainly how thin the day was.

## 2. Source order — open boards before aggregators

Sweep **open ATS boards first** (`ats_pool.py`), then LinkedIn's public guest search, then targeted
web search for what neither covers. This ordering is not cosmetic: it is the difference between a
shortlist that can be applied to and one that cannot. Sweeping an aggregator first surfaces jobs
that turn out to sit behind account walls; sourcing from open boards makes the shortlist applyable
by construction.

## 3. Exclude before you score

Apply the profile's hard exclusions **before** ranking, not as a penalty afterwards. Report the
count in one line; do not list them all.

**Do not rely on the title and the company name alone.** Any employer whose sector is unclear must
be read before it is ranked — a company posting as "Stealth" carries nothing incriminating in
either field, and only the body of the posting reveals what it actually does.

## 4. Read the real postings, but only the ones that survive

Score everything cheaply from title, company and location first. Take the top ~15 and fetch each
posting for what only the full text reveals: compensation, work-authorization wording, whether the
executive title means what it says, team size, funding. **Do not fetch all of them** — that is the
expensive step, and most candidates die on the title alone.

## 5. Applyability — establish it BEFORE anything reaches the list

**A job the user cannot apply to does not belong on the shortlist.** For every candidate that
survives scoring, establish how the application is submitted first:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-apply/scripts/detect_portal.py "<url>" --fetch
```

| Result | What to do |
|---|---|
| `linkedin` | **Resolve it first** — find the employer's own board (`site:job-boards.greenhouse.io "<company>"`, the company's `/careers` page). Classify the resolved URL, never the aggregator mirror. |
| `walled` | An account wall. Claude cannot create accounts, so **drop it from the shortlist** and list it under "excluded — account wall". |
| `fillable` | Keep, and **record the real apply URL in the report** so the apply step does not have to rediscover it. |
| `unknown` | Fetch the page and look for an account wall (*create an account · sign up to apply · register to apply · log in to apply · set a password*). Treat as walled only if found. |

The report's Apply column carries `✅ direct form (<ats>)` · `⛔ account wall` · `✉️ email only` ·
`? unverified`. This costs a few fetches per run and saves the user discovering the wall themselves
after reading a role they liked. It is not optional.

## 6. Rank, cut, and be honest about the tail

Apply `scoring-rubric.md` with the user's weights. Rank, break ties on work mode, cut at the target
count. If fewer clear the bar, deliver fewer and say so.

## 7. Drill down when a company looks strong

The best-fitting role is often not the one that surfaced:

```bash
python3 <skill>/scripts/ats_fetch.py auto <company-slug> --filter "cto|vp|head of|chief|architect"
```

Append confirmed boards to `<state root>/companies.txt` so the pool compounds across runs.

## 8. Never invent

Every job in a report carries a real URL that was actually fetched. If a source returned nothing,
say so. Never fabricate a listing, a salary or a company, and never claim a skill, year or title the
profile does not contain in order to justify a match. A requirement the user does not meet is a red
flag to report, not a detail to gloss.
