---
name: job-onboarding
description: Set up a person's job-search profile — their career facts, target roles, geography, compensation floor and settled application answers — from an existing CV, a Second Brain vault, a LinkedIn export, or a guided conversation. Use on first run, when no profile exists, or when the user says "onboard", "set up my job search", "update my criteria", or their situation has changed.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Job Onboarding

Everything the other four skills know about a person lives in seven Markdown files. This skill writes
them. Nothing else may.

Without a profile the pipeline cannot run: a scout with an invented compensation floor and guessed
locations wastes an entire day and produces a shortlist of jobs the user would never take. **Never
proceed on assumptions — run this instead.**

## Where the profile goes

```
<surface root>/45-jobs/profile/
    profile.md              career facts, contact sets, allowed title variants, education
    search-criteria.md      lanes, target titles, geography, comp floor, hard exclusions
    scoring.md              the weights, the thresholds, the disqualifiers
    application-answers.md  settled answers — work authorization, notice, salary, framing,
                            and the ## Knock-outs block knockout.py screens against
    sources.md              which boards and queries to sweep for this person
    archetypes.md           the 2–3 role types targeted, and how each is argued
    stories.md              STAR+R stories for behavioural questions and interview prep
```

The surface root is the brain when the session is running inside one, otherwise the working folder
(`paths.py` resolves it). **Read order everywhere else:** this surface → the other surface, used
with a one-line notice and an offer to copy it here → run this skill. Being asked to onboard twice,
once per surface, is the failure this ordering exists to prevent.

## Step 0 — See what already exists, and create only what is missing

**Never assume a blank slate, and never clobber one.** Look first:

```bash
DIR=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/paths.py | sed -n 's/^profile dir  : //p')
ls -1 "$DIR" 2>/dev/null || echo "(no profile yet)"
ls -1 "$DIR/cv" 2>/dev/null || true
```

The profile is exactly these seven files. Each is independent — a run that can only fill three
of them should write those three and say which are still missing, rather than refusing or
writing placeholders:

| File | Holds | Missing means |
|---|---|---|
| `profile.md` | career facts — roles, employers, dates, **verbatim titles held**, education, skills, contact sets | nothing can be tailored; ask for this first |
| `search-criteria.md` | what to look for — target roles/lanes, geography and work mode, comp floor, hard exclusions | the scout cannot filter, and will return the whole market |
| `scoring.md` | the weights behind the 100-point score, and the disqualifiers | scoring falls back to the rubric's defaults |
| `application-answers.md` | **the autonomy level** (§0), plus the settled answers reused on every form — work authorisation, notice period, consents, languages, and the raw material free text is composed from | the run defaults to `supervised` and gates every step, and every application re-asks the same questions |
| `sources.md` | the boards and lanes worth sweeping for this person | the scout uses only its neutral defaults |
| `archetypes.md` | the lanes, each with target titles, trigger keywords, lead proof points, why-angles, framing policy | the scout cannot tell a fitting job from an adjacent one, and CVs are argued generically |
| `stories.md` | eight STAR+R stories built from real events | behavioural form questions are answered from scratch, thinly |

Rules for this step:
- **A file that exists is not rewritten** unless the user asked to update it. Read it, use it, and
  say you found it.
- **A file that is missing is created** — that is the job of this skill.
- Write only inside `45-jobs/profile/`. Nothing else in the vault belongs to this skill.

**One exception to "not rewritten": a missing autonomy section.** An
`application-answers.md` written before this setting existed has no `## 0. Autonomy`, and
without it every run is `supervised` forever — the setting would be unreachable for exactly
the people who have been using this longest. So: if the file exists but has no §0, ask the one
question (*"When I find a job that fits, should I tailor the CV, fill the form and submit it
for you — or show you each one first?"*) and **insert the section**, leaving every other line
of the file untouched. Say that you added it. This is an addition, not a rewrite, and it is
the only one allowed here.

### An uploaded CV lives in the profile

Second Brain Studio's **Jobs Agent → Settings** writes the user's CV to
`45-jobs/profile/cv/`. **Look there before asking for one** — if it is there, the user has already
answered "do you have a CV?" and being asked again is the failure this check exists to prevent.

```bash
ls -1 "$DIR/cv" 2>/dev/null
```

Extract it with `pypdf` (PDF) or `python-docx` (DOCX); Markdown and text read directly. If several
are present, use the most recently modified and say which one you took.

### Upgrading an older profile — the v2 additions

Profiles written before the knock-out screen, the archetypes and the story bank lack them, and
without them every job is unscreened and every CV generic. Like the autonomy section, these are
**additions, never rewrites**: when onboarding runs over an existing profile (or the user says
"upgrade my profile"), check for each and add only what is missing, leaving every other line
untouched, then list what was added:

1. `## Knock-outs` in `application-answers.md` (template in `answers-template.md`). Ask per country
   group, and ask for a **number** per currency for salary fields.
2. `archetypes.md` — propose two or three lanes from the profile and the criteria's target titles,
   mark each lane's evidence strength honestly, and ask the user to confirm or cut. Recommend
   dropping any lane whose `critical` requirements the profile cannot show.
3. `profile.md` §4 **Scale / Why it ended / Employment type** per role, and §9 **Framing policy** —
   ask for team sizes, budgets and users role by role; record `TBD` for anything unknown.
4. `stories.md` — draft eight from the profile's bullet bank, then ask the user to correct the
   situation and action of each. Mark any number not in `profile.md` as `(unconfirmed)`.
5. `scoring.md` — if it has no **shortlist likelihood** component, propose the rubric's default
   weights and apply floor, showing old → new, and write them only on a yes.
6. If a legacy state folder with applications exists, offer
   `learn.py import-legacy <folder>` (it copies; the source is untouched).

## Step 1 — Look before you ask

Run the detection in this order and **say what you found** before asking anything. Most people have
one of these lying around and will not think to mention it.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/paths.py          # where a profile would live
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/find_brain.py --verbose
```

| Look for | Then |
|---|---|
| **A Second Brain vault** at or above the working directory | Read `00-me/identity.md`, `40-career/*`, `90-synthesis/positions-i-hold.md` and `90-synthesis/target-companies.md`. The richest starting point by far, because the data is already structured. Confirm the brain belongs to the person you are onboarding — a vault can hold several. |
| **A CV** (`*.pdf`, `*.docx`, `*.md`) in the working folder, or a path the user gives | Extract with `pypdf` / `python-docx`: roles, employers, dates, titles, education, contact details. |
| **A LinkedIn data export** (a zip or folder with `Positions.csv`, `Education.csv`, `Profile.csv`) | Parse those three; they are clean and complete. |
| **A LinkedIn profile URL** | **Say the truth about this one.** LinkedIn blocks automated fetching and its User Agreement forbids scraping, and enforcement lands on the user's own account, not ours. Do not fetch it. Offer the two routes that work: paste the profile text into the chat, or download the data export (Settings → Data Privacy → Get a copy of your data). |
| **Nothing** | Guided conversation, step 3. |

Multiple sources are better than one — a CV has the polished wording, a brain has the network and
the history. Merge them, and prefer the CV's own phrasing for anything that will appear on a CV.

## Step 2 — Confirm every extracted fact

**Never write a fact the user has not confirmed.** Present what you extracted compactly — roles with
dates, titles, education, contact details — and ask for corrections in one pass, not field by field.
Wrong dates and inflated titles are exactly what a background check finds.

Two things to ask about explicitly, because extraction gets them wrong and they matter later:
- **Which titles were actually held**, verbatim, per role. This becomes the closed list of allowed
  title variants, and the CV skill may never write a title outside it.
- **Which roles were remote**, and from where. A US employer worked for from another country must
  read `Remote from <country> · US company (city)`, or every reader assumes the person lived there.

## Step 3 — Interview for what no file contains

A CV never states these, and every one of them changes the shortlist:

1. **Compensation floor** — a number and a currency and a period. Ask for the walk-away figure, not
   the hope. Then ask: is a *published* figure below it a drop, and is *no published figure* a drop?
   (Usually yes and no — on senior boards almost nothing publishes a salary.)
2. **Target roles** — the two or three lanes worth searching, in the user's own words.
3. **Geography and work authorization** — where they can work without sponsorship, where they would
   relocate, where they will not go, and how they rank remote against on-site.
4. **Hard exclusions** — industries, company types, competitors of a current employer, anything
   equity-only, anything requiring money up front.
5. **Portals to avoid** — anything needing an account the user does not have.
6. **Settled application answers** — notice period, earliest start, salary-expectation phrasing,
   visa status, how to frame a current side venture.
7. **Languages spoken**, honestly. A required language nobody checks for is the biggest silent
   filter in a European search.
8. **Knock-outs** — for each country group: right to work, would live there, would relocate
   there; citizenships; degrees; clearances; the salary figure to type per currency.
9. **Archetypes** — which two or three kinds of role, and which near-misses to exclude.
10. **Scale and stories** — team sizes, budgets, users per role; eight real stories.

Ask these in **small batches with sensible defaults offered**, not as a form. Anything the user
declines to answer is recorded as a TBD in the file, never invented.

### The questions, by the file they fill

Ask only what you could not find, and ask in one pass per file rather than one at a time.

**`search-criteria.md`**
- Which **roles/titles** are you targeting? Any second lane you would also take?
- **Where** — countries or cities, and is remote acceptable, preferred, or required?
- Do you have the **right to work** there already, or would you need sponsorship?
- **Compensation floor**: the number below which you would decline. Base, or total?
- **Hard exclusions** — sectors, company stages, or arrangements you will not consider.
- **Company size/stage** you do best in.

**`application-answers.md`** (each is asked on nearly every form)
- **How much should I do on my own?** Ask this one plainly and first, because it decides
  whether anything is ever sent without them:
  *"When I find a job that fits, should I tailor the CV, fill the form and **submit it for
  you** — or show you each one first and wait for your go-ahead?"*
  Write it as `level: autonomous` or `level: supervised` in §0, and say in one line what
  they chose. If they hesitate at all, write `supervised`: it is the reversible choice, and
  they can change one word later. Also ask the cap — *"and at most how many in one run?"* —
  defaulting to 10.
- Notice period / earliest start date.
- Willing to relocate? Travel percentage you accept?
- Do you now or will you require sponsorship? (the exact wording forms use)
- Languages and honest level for each.
- Standing consent answers — AI-evaluation, data retention, background checks.
- Pronouns / EEO fields: what to answer, or "prefer not to say".
- **The raw material for free text.** Not "anything you want said" — the actual substance:
  what draws them to a company (the two or three things they look for), their proudest piece
  of work in a paragraph, the size and shape of what they have managed. The agent composes
  every "Why <company>?" box from this, freshly, per employer — so a thin answer here is a
  thin answer on every form. Push for specifics.

**`scoring.md`**
- Of comp, seniority, work mode, company stage and domain fit — **which matters most**, and which
  would you trade away first?
- What single fact makes you skip a role outright?

**`sources.md`**
- Companies or boards you already know you want swept.
- Anywhere you have already applied recently, so it is not offered again.

**`profile.md`** is confirmation, not interview: step 2 covers it.

## Step 4 — Write the seven files

Each carries frontmatter so it is indexable if the profile lives in a vault:

```markdown
---
type: profile          # or criteria | scoring | answers | sources
title: Career profile — <name>
tags: [jobsearch, profile]
owner: <full name>     # this is what identifies the user's own brain — get it exactly right
updated: <today>
---
```

`owner:` matters beyond bookkeeping: `find_brain.py` matches it against a vault's
`00-me/identity.md` to be sure it is reading the right person's brain and not someone else's.

Use the shipped templates in `references/` for the shape of each file, and the structure of the
existing profile if one is being updated. `references/` carries `profile-template.md`,
`criteria-template.md`, `answers-template.md`, `archetypes-template.md` and
`stories-template.md`; `scoring.md` and `sources.md` follow the shape described in
`job-scout/references/scoring-rubric.md` (its default weights and apply floor) and `sources.md`.

**Write every file that is missing, even the ones the user did not discuss.** A `sources.md` that
says only "no preferred boards yet — using defaults" is a real answer and stops the next run
asking again; an absent file looks like an unfinished onboarding forever.

## Step 5 — Show the diff, then confirm

If a profile already exists, **show what would change before writing** — old value, new value, one
line each. Profiles accumulate real decisions and quietly overwriting them loses work.

Close by naming what is still a TBD, and run one sweep to prove it works:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/ats_pool.py --quiet
```

## Non-negotiables

- **Never invent a fact, a title, a date or a number.** A TBD in the file is fine; a fabrication
  becomes a lie on a CV and in an application submitted in the user's name.
- **Never scrape LinkedIn.** Their ToS forbids it and the consequence lands on the user's account.
- **Never read a brain belonging to someone else**, and never merge two people's brains.
- **Never write outside `profile/`.** Rendered notes belong to `render_brain.py`; the ledger belongs
  to `learn.py` and `scout_state.py`.
- **Never record a credential** — no passwords, passport or national ID numbers, payment details.
  Those are asked at form-fill time and answered by the user, never stored here.
