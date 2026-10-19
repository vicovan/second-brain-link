# Sources — what to read, by tier, and how

| Tier | Source | Route | Gives |
|---|---|---|---|
| 0 | the brain | `warm_rank.py` | revival · warm · dormant · intro accounts, with contacts and ties |
| 1 | LinkedIn public job search | `linkedin_jobs.py` (no login, paced, capped) | `hiring` signals: companies posting the buyer or need roles |
| 1 | the companies' own careers boards | `ats_fetch.py auto <slug>` / WebFetch | the hiring signal confirmed, with the employer's own date |
| 1 | news and press | WebSearch, time-bounded | `funding` · `exec_hire` · `expansion` · `migration` · `news` |
| 1 | directories and portfolios | WebFetch (Chrome if allowed, lists only) | `directory` rows |
| 1 | events | WebFetch exhibitor / speaker pages | `event` rows |
| 1 | registries | WebFetch, open registry pages and APIs | `registry` rows (new incorporations, officer changes) |
| 1 | public threads | WebSearch on forums and public posts | `intent` rows — someone asking for what you sell |
| 2 | each company's own site | WebFetch | domain, about, size, team, published addresses, contact form |
| 3 | lookalikes | the tiers above, seeded by accounts that replied | `lookalike` rows |

## Query patterns (WebSearch)

- Funding: `"<segment>" "raises" OR "Series A" OR "seed round" <market>` — past month.
- Exec hire: `"appoints" OR "joins as" "<buyer role>" <market>` — past month.
- Migration: `"migrating from" OR "moving off" "<tool>" <segment>`; job posts naming a migration.
- Expansion: `"opens office" OR "expands to" <market> <segment>`.
- Intent: each `intent_phrases` entry, quoted, plus `site:` the forums the market uses.
- Directories: `"<segment>" companies directory <market>`, `"portfolio" <accelerator> <segment>`.

Write every hit as a signal row with `url` and `seen`. A search result snippet is a lead to a
page, not a source: open the page and stamp what it says.

## On LinkedIn

LinkedIn's terms discourage automated access even to public pages. So:
- The public job search runs slowly (≥ 1.5 s between requests), with a request cap, and stops at
  the first sign of throttling (HTTP 429 / 999). Never retry a throttled day.
- The signed-in search runs only with `source.linkedin-signed-in: on`, in the seller's own
  Chrome, **reading result lists only** — name, company, title, URL. One tab, human pace, no
  "see more" loops, no profile visits in bulk, no exports, no connection-list scraping.
- Any captcha, "unusual activity" or limit banner → stop all LinkedIn reads for the day and say so.

## Codex

The Codex packaging has no browser: `chrome` routes fall back to WebSearch / WebFetch, and the
coverage line says so.
