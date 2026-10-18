---
type: answers
title: Settled application answers
tags: [jobsearch, profile, answers]
owner: <Full Name>
updated: <YYYY-MM-DD>
---

> Answered once, on purpose, so no form asks again. Anything not here is asked, never guessed.

# Settled application answers

## 0. Autonomy
How much of an application the agent completes on its own. Two values, and the shipped
default is the cautious one — change it deliberately, not by accident.

```
level: supervised          # supervised | autonomous
max-submits-per-run: 10
daily-target: 10           # valid applications a day — the pace KPI
fill-mode: sequential      # sequential | parallel-tabs
filler-model: same         # same | cheap
review-rounds: 1           # 1-3 rework rounds after a recruiter-review maybe/reject
when-stuck: ask            # ask | skip
reviewer-ignore:           # e.g. visa, relocation — what the recruiter reviewer must not grade on
```

- **`supervised`** — three approval gates: pick the job, approve the CV, approve the submit.
  Nothing is sent without a tap.
- **`autonomous`** — no gates. It picks, tailors, drafts every answer, fills the form,
  verifies each field in the DOM, **submits**, and reports what it did. Applications go out
  in your name without you seeing them first; the audit trail (`answers.json` and
  `ANSWERS.md`, one folder per application) is what you read afterwards instead.
- `max-submits-per-run` caps a single run so one instruction cannot empty a shortlist.
- `daily-target` is the pace KPI: valid applications (sent through every gate) per day, counted
  across all of the day's runs. The scout sizes its shortlist to reach it (`learn.py target`) by
  sourcing wider — never by lowering the apply floor. Keep it at or below `max-submits-per-run`
  unless you expect to run more than once a day.

How the run behaves, each a deliberate choice:
- **`fill-mode`** — `sequential` fills one form at a time (the safe default). `parallel-tabs`
  opens one tab per ready application and fills them side by side; each filler is told its own tab
  and never touches another, and the DOM check and the submit stay per-tab and deliberate.
- **`filler-model`** — `same` fills forms on the model running the run. `cheap` hands the mechanical
  typing to a smaller model, because by then every answer is already written in `answers.json`.
  The DOM verification, the repair of fields the form silently dropped, and the submit decision
  always stay with the main model: that is exactly where small fillers fail.
- **`review-rounds`** — after a `maybe` or `reject` from the recruiter review, how many rounds of
  CV rework (against that posting's must-haves, with confirmed facts only) and re-review to run
  before giving up. More rounds help only when there are facts to add; rewording alone rarely
  changes a verdict.
- **`when-stuck`** — a field that will not register, a missing fact, a frame the agent cannot reach.
  `ask` brings that tab to the front and tells you exactly what to click or type; `skip` records a
  one-line reason and moves on.
- **`reviewer-ignore`** — topics the recruiter review must leave out of its verdict because you
  have decided they are not blockers for you (for example `visa` if you accept roles needing
  sponsorship). Form answers on those topics stay truthful.

Neither level ever types a password, an identity or passport number, payment details or a
date of birth, and neither invents a factual answer that is not in this file or the profile.
See `job-apply/references/field-policy.md`.

## 1. Identity and contact
Name, email, phone, city, country. **No date of birth, no national ID, no passport number** — those
are never stored and never typed by an agent. If you keep more than one contact set (a phone and
address per region, see `profile.md` §1), the set follows **the job's location**, never one set
for every application, and the CV and the form always carry the same one. Street address, city,
region and postal code per set, in the exact form to type (and what to type when a form requires
a postal code your address does not have).

## 2. Work authorization
Per region: authorized without sponsorship / needs sponsorship / not authorized. Exact wording for
the common phrasings of the question.

## 3. Logistics
Notice period · earliest start · salary expectation, in the phrasing to use verbatim · willingness
to relocate · remote/hybrid/on-site preference.

## 4. Standing screening answers
The recurring free-text questions and the raw material to compose from: **why this company**
(a paragraph with a slot for what the specific employer does), biggest achievement, management
scope, team size led, why this role.

This section is the source the agent COMPOSES from — it does not paste it. Free text is
written fresh for each employer in that employer's own vocabulary, and it is never left blank
and never handed back to you as a question. Fill this in properly and every "Why <company>?"
box answers itself well; leave it empty and they answer thinly.

## 5. Framing
How to describe a current side venture or period of self-employment on an employer's form.

## 5b. Standing defaults
The small questions every form asks. Settled once so nothing stalls on them:

- previously employed by / interviewed with / relatives at the employer: <No — unless you say otherwise for a company>
- consent to a background check if an offer is made: <Yes / ask>
- start date when the form wants a calendar date, not a notice period: <e.g. "immediately", "two weeks after offer">
- salary in a numbers-only "local currency" field: <the number to type>
- gender / pronouns / disability / veteran status when required with no "prefer not to say": <answer, or "ask">
- remote collaboration tools used professionally: <list>

## 5c. Consents and attestations
- optional "keep my data for future roles" / talent-pool boxes: <decline (default) / accept>
- marketing, WhatsApp or SMS updates: <No (default)>
- consents inherent to submitting (processing the application, AI-assisted screening of it): <accept — there is no application without them>
- **"I personally completed this application" or a policy forbidding AI help with the answers:**
  never ticked by an agent at any autonomy level. The agent fills the factual fields, leaves the
  box, and hands that form to you. A form that explicitly allows AI help is filled normally.

Every consent is recorded verbatim in that application's `ANSWERS.md`.

## Knock-outs
The answers an ATS auto-rejects on. `job-apply/scripts/knockout.py` reads these exact keys and
screens every posting against them **before** a CV is written, so a job the truthful answer
disqualifies is skipped instead of sent. Comma-separated; ISO country codes or `EU` / `EEA`.

- right_to_work: <countries where no sponsorship is needed, e.g. EU, EEA>
- sponsorship_acceptable: <countries where a sponsored role is wanted — applied to ONLY when the posting offers sponsorship>
- based_in: <where the person lives now>
- relocate_to: <where they would move for the right role>
- nationalities: <citizenships held>
- languages: <languages at working level or better>
- degrees: <degrees held, as named on the certificate>
- clearances: <security clearances held, or leave empty>
- years_experience: <total professional years>
- salary_floor: <currency amount per year, e.g. EUR 100000 — the DROP line: a published base below it is skipped>
- salary_target: <currency amount per year, e.g. EUR 140000 — the RANK line: a band below it scores low but is not dropped>
- salary_figures: <the figure to type when a form demands one, per currency, e.g. EUR 130000, GBP 115000>

A number, never an instruction: a salary field that receives "prefer to discuss" is either
rejected by validation or read as evasive.

## 6. Never answered by an agent
Passwords · passport or national identity number · payment details · date of birth · anything
requiring a legal declaration the user has not read. These stop the run and go to the user.
