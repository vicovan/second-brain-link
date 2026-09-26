---
type: profile
title: Career profile — <Full Name>
tags: [jobsearch, profile]
owner: <Full Name>
updated: <YYYY-MM-DD>
---

> The only source of facts for a CV or an application answer. If it is not here, it is asked —
> never inferred, never rounded up.

# Career profile — <Full Name>

## 1. Contact sets

One set per CV. Give each a name, and say when it applies.

| Set | Location | Phone | Email | Status line |
|---|---|---|---|---|
| `<eu>` | City, Country | +00 000 000 000 | name@example.com | `<Citizenship> · remote · open to relocation` |

The **status line is citizenship and work authorization only** — never time zones, never a note
that a role would need sponsorship. The form asks that question; the CV does not volunteer it.

Links in a CV header: **one**, normally LinkedIn.

## 2. Positioning

One paragraph on what this person is, in their own words. The CV headline is built from this.

## 3. Domains

Where they have real depth, strongest first. Name the *intersections* — two domains combined are
rarer than either alone, and that is what a shortlist should be scored on.

## 4. Roles (reverse chronological)

### <Employer> — <true title held>
- **Dates:** MM/YYYY – MM/YYYY
- **Where:** `City, Country` or `Remote from <country> · <employer country> company (<city>)`
- **Allowed title variants:** the closed list of labels genuinely accurate for this role. The CV
  skill may not write anything outside it.
- **What it was:** one line the CV can adapt as the company descriptor.
- **Scale:** team or org size led (engineers, managers, reports), budget, users or revenue — the
  numbers a Director/VP screen looks for first. `TBD` if unknown; never estimated.
- **Why it ended:** acquisition, funding round, contract end, venture wound down — one clause the
  CV can use so a short tenure is not read as a firing.
- **Employment type:** full-time employee · founder · part-time / advisory · contract. Decides how
  overlapping dates are shown.
- **Facts:** the bullet bank — real, specific, uneven numbers. A superset; each CV selects from it.
  Keep the verb honest: *used*, *integrated*, *led the team that built* and *built* are different
  claims, and the CV may not upgrade one to another.

## 5. Education, certifications, languages

Institution, qualification, date. Languages with an honest level.

## 6. Numbers

Every figure that may appear on a CV, with what it actually counts. Nothing may be rounded up or
restated more impressively elsewhere. `lint_cv.py --profile` fails a CV whose numbers are not in
this file.

## 7. What this person has NOT done

The real gaps — scale not yet run, domains not worked in, credentials not held. **Used for
targeting and interview prep only:** the scout scores against them and `fit.md` lists them so the
candidate can prepare an answer. They never appear on a CV or in a free-text form answer, where a
screener reads them as the reason to reject.

## 8. Contact-set decision rule

How to pick one set from §1 for a given employer.

## 9. Framing policy

Decided once, per archetype in `archetypes.md`, so no application has to ask:

| Archetype | Current own venture / side project shown as | Overlapping roles shown as |
|---|---|---|
| `<archetype>` | current role · a line under the employed role · a "Founder ventures" group | separate entries · grouped |

An employee-track archetype usually shows a founder venture as a line alongside, not as the
current full-time role: a founder title directly above an application for a job is the loudest
"will leave" signal on a CV.
