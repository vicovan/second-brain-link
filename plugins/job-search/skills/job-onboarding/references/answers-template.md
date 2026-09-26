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
```

- **`supervised`** — three approval gates: pick the job, approve the CV, approve the submit.
  Nothing is sent without a tap.
- **`autonomous`** — no gates. It picks, tailors, drafts every answer, fills the form,
  verifies each field in the DOM, **submits**, and reports what it did. Applications go out
  in your name without you seeing them first; the audit trail (`answers.json` and
  `ANSWERS.md`, one folder per application) is what you read afterwards instead.
- `max-submits-per-run` caps a single run so one instruction cannot empty a shortlist.

Neither level ever types a password, an identity or passport number, payment details or a
date of birth, and neither invents a factual answer that is not in this file or the profile.
See `job-apply/references/field-policy.md`.

## 1. Identity and contact
Name, email, phone, city, country. **No date of birth, no national ID, no passport number** — those
are never stored and never typed by an agent.

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
- salary_floor: <currency amount per year, e.g. EUR 100000>
- salary_figures: <the figure to type when a form demands one, per currency, e.g. EUR 130000, GBP 115000>

A number, never an instruction: a salary field that receives "prefer to discuss" is either
rejected by validation or read as evasive.

## 6. Never answered by an agent
Passwords · passport or national identity number · payment details · date of birth · anything
requiring a legal declaration the user has not read. These stop the run and go to the user.
