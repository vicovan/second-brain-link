# Scoring rubric — how to rank down to a shortlist worth sending

Score every surviving candidate out of **100**. Be harsh: a 60 is a mediocre job. The point of the
number is to make the ordering arguable, not to flatter the list.

**The score answers two questions, and the second matters more:** does the user want this job, and
**would a recruiter put this person on a screening call for it?** A score built only on the first
(pay, location, freshness) ranks attractive jobs the candidate cannot win, and sends applications
that come back as fast, generic rejections.

**This file is the method. The numbers are not here.** Every weight, threshold and disqualifier
comes from the user's `profile/scoring.md`, the lanes from `profile/archetypes.md`, and the
geographies from `profile/search-criteria.md`. Read those first; if one is missing, run onboarding
rather than inventing a floor. Where `profile/scoring.md` predates the shortlist-likelihood
component, use the default weights below and tell the user once that onboarding can re-weight it.

## Step 0 — archetype, before any points

Every job is mapped to exactly one lane in `profile/archetypes.md` by its title and the lane's
trigger keywords. **A job that matches no lane is dropped, not scored low.** Applying across
unrelated lanes in the same week is itself a signal recruiters read.

## The six components

| # | Component | Default max | What it measures |
|---|---|---|---|
| 1 | **Shortlist likelihood** | **30** | Would *this* candidate make the screening call? See below. |
| 2 | **Compensation** | 15 | Does the pay clear the user's floor, and by how much. Convert to the floor's currency and period before comparing — never eyeball a foreign headline number. A *published* figure below the floor is a drop (the knock-out screen catches it); **no published figure is not a drop** unless the profile says so. |
| 3 | **Role fit** | 15 | Title and scope against the archetype's target titles. An exact title at the right company size scores at the top; adjacent titles mid; a senior-IC job wearing an executive title near zero. |
| 4 | **Domain fit** | 15 | Overlap with the domains in the profile. Score the *intersection* highest — two domains the user combines are rarer, and more defensible, than one they merely know. |
| 5 | **Geography and work mode** | 10 | Where the job is and how it is worked, against the profile's mode table. A knock-out (right to work, must-be-based-in, required language) never reaches scoring — `knockout.py` removed it. |
| 6 | **Company quality and stage** | 10 | Funding, product reality, investor credibility. An agency repost for an unnamed client scores at the bottom regardless of the title. |

Freshness and a confirmed direct application form are **gates**, not points: a stale repost or an
account wall does not reach the shortlist (workflow step 5b).

### Shortlist likelihood — the 30 points that decide interviews

Score it from the posting and `profile/profile.md` only, as a recruiter would in six seconds:

| Signal | Points |
|---|---|
| **Title ladder** — the highest title the profile holds is at the target's level (or one below in a larger company) | 0–8 |
| **The JD's #1 requirement** — years of *direct* evidence for it in the profile, at or above what the JD asks | 0–8 |
| **Recency** — that evidence sits in the last five years, not only in an older role | 0–6 |
| **Critical-requirement coverage** — share of the JD's must-haves the profile shows as `existing` or `supported` (the fit-file pass, done roughly here) | 0–8 |

Deductions a recruiter makes silently — apply them honestly:
- The role is a **different discipline** wearing a familiar word (research scientist, hands-on ML
  engineer, sales engineering) for a profile whose evidence is leadership or architecture → cap at 8.
- The JD's scale words (headcount led, budget, regulated licence, public-company) are **absent from
  the profile** → −4 each, up to −8.
- The candidate is **far over-level** (a C-level profile for a senior-IC role) → cap at 14: the
  screener assumes they will leave.

## The apply floor

A job reaches the shortlist only if **both** hold (defaults; `profile/scoring.md` may set its own):
- **total ≥ 75**, and
- **shortlist likelihood ≥ 20 / 30**.

Also: **one role per company** per shortlist, and none at a company the ledger shows an
application to in the last 30 days.

Weights are per-user. Apply `profile/scoring.md` where it sets them; do not assume an even split.

## Disqualifiers

`profile/scoring.md` carries the user's list. Two rules about how to apply it:

- **Drop means drop.** A disqualified job never appears in the ranked list, never gets "surfaced
  anyway", and is never padded in to reach ten. It goes to a separate "excluded" section with one
  line of reason — visible, but not ranked and not presented as an option.
- **Never disqualify on a title or a company name alone.** Read the posting when the sector is
  unclear. A digital-asset market maker posting as "Stealth" carries nothing incriminating in either
  field; only the body reveals it.

Two things that are **never** disqualifiers, whatever the profile says:

- **A Chrome extension permission block.** That is a tooling gap, not a fact about the job — ask for
  the domain and keep the job on the list.
- **An unverified apply route.** If step 5b could not establish the route either way, the job may
  still be shortlisted, marked `? unverified`. Only a *confirmed* wall removes it. Many good
  employers simply block automated fetching of their careers page.

## Presenting the shortlist

**Link every title** — the Role cell is a Markdown link to the apply URL, always. Users open jobs
straight from the table.

Rank by score, then break ties with the work-mode preference order in `profile/scoring.md`. Give
each job **at most three lines**:

```
**7. Chief Technology Officer — <Company>** · <location, mode> · 84/100 · likelihood 23/30 · <archetype>
Why: <the one thing that makes this a fit, in the user's own terms>
Flag: <what to check before applying> → <apply url>
```

Close with **one line** naming which lane dominated today and anything that changes the search — a
dry geography, a repeated employer worth a Tier-2 drill-down.

**Say plainly when the day is thin.** "Only four cleared the floor today" is a useful result and far
better than padding to ten with roles the user would never be shortlisted for. The point of a daily
scan is that most days are quiet.

Close with an **excluded** line per reason — knock-out (with the count), no matching archetype,
below the floor — so the user can see the gates working without reading every rejected job.
