# Regional sources — where each market actually posts

Every market posts somewhere different. A sweep built for one market (open ATS boards suit US and
EU tech companies) returns **zero** in another (most Gulf employers use LinkedIn, local boards,
recruiters and walled corporate career sites). Zero from the wrong instrument is not a thin market.
**Never report a geography as empty on the strength of an open-ATS slug sweep alone.**

The method that works in a board-led market: **board → employer name → the employer's own site.**
Capture the list on the board (in the browser only if the board blocks fetching), filter it with no
network against the lanes and exclusions, then find each survivor on the employer's own careers
site or ATS and apply there. The board is never the application route.
`scout_state.py coverage` fails the run until each target market has been fed by enough sources.

For each market in the user's criteria §3, use **every row of its pack**, in this order. The
**Route** column says how each source can be read:

| Route | Meaning |
|---|---|
| `linkedin` | `scripts/linkedin_jobs.py` — LinkedIn's public, no-login search (if the user turned it on, criteria §3b) |
| `api` | `scripts/ats_fetch.py` / `ats_pool.py` — a public JSON board |
| `fetch` | `WebFetch` the public listing page |
| `chrome` | read the public listing page in the user's own Chrome, read-only (criteria §3b) — Claude Code only |
| `search` | `WebSearch` with `site:` — for boards that block direct reading |

Routes marked *verify* have not been confirmed for every board: try them, and record what worked
with `memory.py observe --source outcome` so the next run starts from the working route.

## Every market

| Source | Route | Notes |
|---|---|---|
| LinkedIn job search | `linkedin` | The broadest single list in most markets. One query per lane title × market, time-filtered since the last run. Discovery only — the application is made at the employer's site. |
| Company registry | `api` | `companies.py batch` — every employer seen hiring before whose board is known, re-swept weekly or the day it posts a new in-lane role. |
| Open ATS pool | `api` | `ats_pool.py` — Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Personio. Strong for US and EU tech (Recruitee and Personio for DACH and Benelux); weak elsewhere. |
| Search engines | `search` | `"<title>" <city> hiring` and `site:<board> "<title>"` for each board below that blocks reading. |

## Gulf (UAE, Saudi Arabia, Qatar, the wider GCC)

| Source | Route | Notes |
|---|---|---|
| LinkedIn job search | `linkedin`, or `chrome` signed-in if §3b allows | Usually the freshest and broadest Gulf list — work it first. |
| Bayt | `chrome`, else `search` | The richest local board for senior roles, with dates; blocks automated fetching (HTTP 403). Its "nationals only" titles are common — drop them on the list. |
| GulfTalent | `chrome`, else `search` | Senior and professional roles; blocks automated fetching. Measured low yield for executive technology titles (hotel and facilities IT dominate); filter by seniority and check, but expect little. |
| Naukrigulf | `chrome`, else `search` | Large volume; mostly mid-level. |
| Recruiters: Michael Page Middle East, Hays Middle East, Robert Walters Middle East, Cooper Fitch | `fetch` *(verify)* | Retained and contingent search for senior roles; many list salary bands. A recruiter row names the recruiter as the route. |
| Corporate careers sites (Workday, SuccessFactors, Oracle, Taleo) | `api` for Workday, else `fetch` / `chrome` | Large regional employers, banks, government-linked groups. Reading the list needs no account; applying does — surface the row with the portal named. |

**Nationality gates are common.** A posting reserved for nationals of the country is a knock-out
unless the user holds that nationality — a residence visa does not satisfy it. Screen it with
`job-apply/scripts/knockout.py`, and read the form's own question: a duty such as "support the
national-hiring (localisation) objectives" is not a gate, and the form often offers an expatriate
option.

**Salary is usually not posted here.** Do not penalise an unposted band. Estimate it from the
employer's size and the role's level, label it *estimate* in the Comp column, and keep only a
*published* base below the floor as a drop. A large named employer at head or director level
usually pays well above a small agency or an unnamed startup at the same title.

**A few regional employers do run open ATS boards.** Keep the ones found as a standing watchlist
in `companies.txt` rather than re-probing a hundred slugs every run.

## European Union and Switzerland

| Source | Route | Notes |
|---|---|---|
| StepStone (DE, AT), jobs.ch and jobup.ch (CH), Welcome to the Jungle (FR) | `search` *(verify `fetch`)* | National boards; many employers post here before LinkedIn. |
| Recruiters: Michael Page, Hays, Robert Walters (per country) | `fetch` *(verify)* | Senior search, often with bands. |
| Corporate careers (SAP SuccessFactors is common in DACH) | `fetch` / `chrome` | Read the list; surface walled rows with the portal named. |
| Wellfound, Welcome to the Jungle / Otta | `search` | Startups and scale-ups. |

## United Kingdom

| Source | Route | Notes |
|---|---|---|
| Otta / Welcome to the Jungle, Totaljobs, Reed | `search` | Reed and Totaljobs skew mid-level; Otta skews tech. |
| Recruiters (Michael Page, Hays, Harvey Nash) | `fetch` *(verify)* | Senior and interim roles. |

## Remote (global, or "remote in <region>")

| Source | Route | Notes |
|---|---|---|
| LinkedIn job search with the remote filter | `linkedin --remote` | Use the market the user can work from as the location. |
| Open ATS pool, Y Combinator jobs | `api`, `fetch` | See `sources.md`. |
| Remotive, RemoteOK, We Work Remotely | `fetch` *(verify)* | Mostly IC roles; worth a pass for staff and principal titles. |

## Adding a market

A market the user targets but no pack covers: run LinkedIn and the search engines first, harvest
the companies they name, and write down the three boards that produced the most in-lane rows. Add
them to this file only if they are generic public boards — never anything about one user's search.
