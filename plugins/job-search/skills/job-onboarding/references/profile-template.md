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
- **Dates:** MM/YYYY – MM/YYYY (the internal record)
- **Public record:** the dates and location this role shows on the person's LinkedIn (or `not on
  LinkedIn`). **The CV uses these** — a recruiter opens LinkedIn next, and a CV that disagrees
  reads as invented. A role not on LinkedIn goes in the CV's `Earlier Experience` group.
- **Where:** `City, Country` or `Remote from <country> · <employer country> company (<city>)`
- **Company site:** the live URL, or `none` (the CV prints the bare domain for little-known
  employers; never a dead or parked site).
- **Acquired / renamed:** `<New Owner> acquired <Old Name> in MM/YYYY`, or `—`. The CV keeps ONE
  entry under `<New Owner> (formerly <Old Name>)` with the original start date.
- **Allowed title variants:** the closed list of labels genuinely accurate for this role. The CV
  skill may not write anything outside it. For a compound founder title (`Co-Founder & CTO`), ask
  whether the plain function (`CTO`) may be used on CVs for employed roles, and record which lanes
  use which.
- **What it was:** one line the CV can adapt as the company descriptor (Title Case on the CV).
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
| `<archetype>` | current role · its own small `## Open Source` / `## Projects` section below the work history | separate entries · grouped |

An employee-track archetype shows a founder venture or side project in its own small section below
the work history, never as the current full-time role: a founder title directly above an
application for a job is the loudest "will leave" signal on a CV. On those CVs the older roles are
grouped as `Earlier Experience`, written role-first (*"CEO of …"*), never as "ventures" and never
led by *founded* / *co-founded*.

## 10. CV conventions

Decided once at onboarding, so every CV reads as one hand (`lint_cv.py` enforces them):

| Convention | Choice |
|---|---|
| Date format | `YYYY` (when the public profile shows years only) · `MM/YYYY` |
| Spelling system | British · American — or "match each posting" |
| Title forms | `CTO` · `Chief Technology Officer` (one form across the CV) |
| Header link | LinkedIn URL |
| Roles in `Earlier Experience` | which roles collapse into the grouped line |
