---
type: criteria
title: Job search criteria
tags: [jobsearch, profile, criteria]
owner: <Full Name>
updated: <YYYY-MM-DD>
---

# Job search criteria

## 1. Lanes and titles
The two or three kinds of role worth searching for, each with the titles that signal it.

## 2. Compensation
Two numbers, each with a currency and a period: the **floor** (a published base below it is a
drop) and the **target** (what you rank on — a band below it scores low, but stays). Keep them in
step with `salary_floor` / `salary_target` in `application-answers.md` Knock-outs; if they ever
disagree, the newer one is the one you meant, and the agent asks rather than guesses. Then the
two rules —
- a **published** figure below the floor: drop, or down-score?
- **no published figure**: drop, or shortlist and flag? (In markets where pay is rarely posted,
  the agent estimates from employer size and level and labels it an estimate.)

## 3. Geography and work authorization
Where they can work without sponsorship · where they would relocate · where they will not go ·
how remote ranks against on-site · any low-preference market.

### 3a. Markets — the scout's query grid
One line per market, with the cities and country names that identify it in a job's location —
`scout_state.py merge --markets` and the coverage gate use exactly these:

| Market | Location regex | Work modes accepted |
|---|---|---|
| `<Market A>` | `<city|city|country>` | remote · hybrid · on-site |

## 3b. Sources
Where the scout may read. Each is the user's decision; record it as written.

| Setting | Choice | What it means |
|---|---|---|
| `linkedin-public` | on · off | LinkedIn's no-login job search (`linkedin_jobs.py`): broad, dated, time-filtered. No account is used. LinkedIn's terms discourage automated access even to public pages, so it runs slowly and stops when throttled. |
| `linkedin-signed-in` | on request · daily · never | A read of LinkedIn result pages in the user's own signed-in Chrome — on request, or as a daily source. Read-only at a human pace, about 10 pages per search, a handful of searches a day; a warning, CAPTCHA or 429 ends it for the day; anything beyond reading (Easy Apply, messages) is handed to the user. Any enforcement would land on their account. Claude Code only. |
| `chrome-boards` | on · off | Boards that block automated reading (Bayt, GulfTalent…) read in the user's Chrome — read-only, never sign in, apply or register. Claude Code only. |
| `walled` | surface · assist · drop | Jobs on account-walled portals (Workday, SuccessFactors, iCIMS, Taleo, join.com…): **surface** keeps them on the shortlist as a hand-off — CV and answers ready, the user applies there; **assist** fills them in the run, in the user's browser, and stops only for the steps an agent may not do (creating the account, passwords, e-mail codes, CAPTCHAs), then carries on; **drop** leaves them out. In some markets most senior roles are behind these portals. |

## 4. Domains
In scope, and adjacent-but-acceptable.

## 5. Hard exclusions
Drop, never rank. Industries, company types, competitors of a current employer, equity-only,
pay-to-play, required languages not spoken. (Portals requiring an account are §3b `walled`, not
an exclusion.)

## 6. Freshness and volume
How many days back, and how many results to deliver.
