# Scoring rubric — how to rank down to a defensible top 10

Score every surviving candidate out of **100**. Be harsh: a 60 is a mediocre job. The point of the
number is to make the ordering arguable, not to flatter the list.

**This file is the method. The numbers are not here.** Every weight, threshold and disqualifier
comes from the user's `profile/scoring.md`, and the geographies and lanes from
`profile/search-criteria.md`. Read those first; if one is missing, run onboarding rather than
inventing a floor.

## The six components

| # | Component | What it measures |
|---|---|---|
| 1 | **Compensation** | Does the pay clear the user's floor, and by how much. Convert to the floor's currency and period before comparing — never eyeball a foreign headline number. A *published* figure below the floor is a drop, not a low score; **no published figure is not a drop** unless the profile says so, because on most senior boards almost nothing publishes a salary, and requiring one filters out the good roles rather than the bad ones. |
| 2 | **Role fit** | Title and scope against the target lanes. An exact lane title at the right company size scores at the top of the band; adjacent titles score mid; a senior-IC job wearing an executive title scores near zero however good the company is. |
| 3 | **Domain fit** | Overlap with the domains in the profile. Score the *intersection* highest — two domains the user combines are rarer, and more defensible, than one they merely know. |
| 4 | **Geography and work mode** | Where the job is and how it is worked, scored against the profile's mode table. Score any no-sponsorship-needed advantage explicitly. **A required language the user does not speak caps this component and is flagged** — in European searches it is usually the biggest silent filter. |
| 5 | **Company quality and stage** | Funding, product reality, investor credibility. An agency repost for an unnamed client scores at the bottom regardless of the title. |
| 6 | **Freshness and applyability** | Recency plus a *confirmed direct application form*. An account wall is not scored here — it removes the job from the shortlist entirely (workflow step 5b). |

Weights are per-user. Apply `profile/scoring.md`; do not assume an even split.

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

## Presenting the top 10

**Link every title** — the Role cell is a Markdown link to the apply URL, always. Users open jobs
straight from the table.

Rank by score, then break ties with the work-mode preference order in `profile/scoring.md`. Give
each job **at most three lines**:

```
**7. Chief Technology Officer — <Company>** · <location, mode> · 84/100
Why: <the one thing that makes this a fit, in the user's own terms>
Flag: <what to check before applying> → <apply url>
```

Close with **one line** naming which lane dominated today and anything that changes the search — a
dry geography, a repeated employer worth a Tier-2 drill-down.

**Say plainly when the day is thin.** "Only four cleared 60 today" is a useful result and far better
than padding to ten with roles the user would never take. The point of a daily scan is that most
days are quiet.
