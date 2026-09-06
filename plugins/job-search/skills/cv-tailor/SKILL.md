---
name: cv-tailor
description: Build a tailored, ATS-first CV as Markdown and PDF for one target job, from the user's own career profile. Use whenever a job description, JD, role, accelerator or investor programme is shared, or the user says "tailor my CV", "resume for this", "apply to this", or shares a new career fact.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebFetch, Skill
---

# CV Tailor

**When this applies (the description above is capped at 200 chars, so the full
trigger list lives here):** any time the user pastes or links a job description,
company careers page, accelerator or investor programme; says "tailor my CV",
"resume for this", "apply to this", "adapt my CV", "which location should I
use"; asks about their job titles, career history or application materials; or
shares a new career fact that should go into the master profile.

You are producing the single document that decides whether the user gets the
interview. Treat every run as high-stakes: research properly, mirror the
target precisely, never invent, verify the PDF the way a machine will read it.

## Files in this skill

| File | Read when |
|---|---|
| `<profile>/profile.md` (in the user's data, resolved at step 0) | ALWAYS. The only allowed source of facts, titles, numbers, contacts. |
| `references/tailoring-playbook.md` | ALWAYS. Intake, location decision, title mirroring, keyword strategy, human-gate rules, variants by company type. |
| `references/ats-checklist.md` | Before delivering. QA gates. |
| `assets/example-cv.md` | Once, to see the content-JSON shape and the tone that worked. |
| `scripts/build_cv.py` | To render JSON → PDF (`--docx` for Word too). Pure Python + reportlab. |
| `scripts/check_pdf.py` | To verify keyword coverage, page count, extraction order, fonts. |

## Workflow (do all steps, in order)

### 0. Load the profile — REQUIRED, before anything else

Everything this skill knows about the person is in their profile. Resolve it:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/paths.py     # prints the profile dir for this surface
```

**Read order:** this surface's `45-jobs/profile/` → the other surface's, used with a one-line notice
and an offer to copy it here → **run `job-search:job-onboarding` (the **Skill** tool)**. Never guess a fact, a floor or a location:
this skill's whole output goes out under the user's name.

### 0b. Load what past applications taught
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py show
```
If `job-scout` is installed, `lessons.md` records which CV choices actually drew replies —
which headline variants, which lead bullets, which title labels. Apply anything tagged `[cv]`.
Skip this step silently if the file or the scout is not present.

### 1. Get the target
- If the user gave a URL, fetch it (web_fetch / browser). If it is a company page or
  programme page rather than a JD, read it for what they screen for.
- If only a company name + role, search for the JD and the company site.
- If nothing but a company, ask one question: "Which role/title?" and proceed
  with a CTO/VP-Eng default while waiting.
- Fill the intake table from playbook §1 (title, seniority, company type,
  location/work mode, must-have keywords, nice-to-haves, domain, culture
  signals, the three silent questions). Write it in your reasoning; do not
  dump it on the user.

### 2. Decide the contact set
Apply playbook §2. Output exactly one phone + one primary location (dual city
allowed only for global programmes). Note the reason in one clause for the
final message.

### 3. Read the master profile and select
- If `45-jobs/profile/cv/` holds the user's own CV (uploaded via Studio -> Jobs Agent ->
  Settings), read it too — it carries their real wording, which `profile.md` may have
  summarised away. Never contradict `profile.md`; it stays the source of truth for facts.
- Read `profile/profile.md` in full.
- **Title mirroring — playbook §3, the three-rung ladder.** Mirror the target title verbatim in the
  headline AND in the first sentence of the summary; use an allowed title variant for each role
  where one matches; otherwise keep the true title and add a one-line **scope-equivalence** sentence
  in the JD's own vocabulary. **Never write a title the user did not hold** — titles are the most
  verifiable thing on a CV.
- **Set the title for EVERY role, not just the headline.** Go through
  `profile/profile.md` **§4.0 Allowed title variants** and pick the closest variant per role using
  the target map there. `§4.0` is a closed list — nothing outside it may appear as a title.
- **Add a scope-equivalence line under any role whose title still does not match the target's
  vocabulary** (playbook §3, rung 3): one sentence, using the JD's own noun, describing what they
  actually did. e.g. target *Engineering Director* → under a CTO role at a scale-up:
  *"Directed the engineering organisation across two sites, doubling it while running a full
  platform rebuild."* This is where most of the matching happens and it stays entirely truthful.
- Their titles are often **more senior** than the target — keep them, never downgrade.
- **Rewrite every past role for this target — playbook §3b.** Four moves: (1) reframe each
  company's descriptor line toward the target's world; (2) **select** 2–5 bullets per recent role
  and drop the rest — the bank is a superset, not a checklist; (3) restate the same facts in the
  **JD's exact nouns and verbs** (if they say "ship", do not write "deliver"); (4) order bullets so
  the first one under the most recent relevant role answers the JD's **#1 requirement**.
- Rewriting = the same true fact in their words. **Never add scope, scale or numbers** that are not
  in `profile/profile.md` §7.
- Build the Core Competencies list: JD must-haves first (both forms), then
  nice-to-haves, then the user's strongest adjacent keywords. 40–60 terms.
- Apply the company-type variant (playbook §7) and regional convention (§8).
- Decide the older-roles depth (merge studios unless relevant).
- For full-time employee targets, decide how the user's own ventures and side
  projects are framed (playbook §6); if unclear, ask the user the one framing
  question and use the default (current venture as the current role) meanwhile.

### 3b. Write the summary and the closing section — playbook §3c and §3d
- **Professional Summary, rewritten from scratch every time.** Four sentences: target title verbatim
  and bolded + strongest proof · their #1 requirement answered with a specific fact · their #2–#3
  compressed · scale credential or the honest calibration. 90–120 words. Quote a distinctive line
  from the JD back at them where one exists.
- **Include an honest calibration clause wherever there is a real gap** — name the seniority,
  domain or depth the profile genuinely does not have, in the profile's own words. Told plainly it makes the rest credible; found
  by the reader it discounts everything.
- **Close with a 3-bullet "Why This Role"** named for the target: strongest match, second match,
  then logistics or the gap.

### 4. Write the CV as Markdown

**Where it goes.** The caller passes an output directory — for an application that is
`<state root>/applications/<YYYY-MM-DD>/<job_key>/`. Write BOTH the Markdown and the PDF
there. If no directory was given, ask for one rather than guessing: writing to the current
directory drops the CV in the root of the user's vault, where it does not belong and will
not be found again.

Create `<outdir>/<Firstname>_<Lastname>_CV_<Company>.md` following the schema below —
**no role in the filename**. Upload widgets reject long names, and the role is already in the
folder name and in the CV itself. `build_cv.py` enforces the rule (40 chars, ASCII,
underscores) and renames your `.md` to match if you write something longer, so the pair
always agrees; write the short name yourself and nothing has to be corrected.
Everything the reader sees lives in this one file; the builder only lays it out. Keep to
≤ 2 pages of content: ~450–650 words on page 1, ~350–550 on page 2.

Markdown, not JSON, for three reasons: the user can read and correct it, it diffs cleanly between
versions, and it is indexable as a note if their job data lives in a Second Brain vault.

### 4b. The de-tell pass — playbook §3e
Before building, read the JSON back and fix the eight tells that make a CV look generated. The
short version, in order of how loudly each one shouts:

1. **Bold lead-ins on every bullet** — at most half per role, never three in a row. Rewrite the
   surplus to open with a verb or with the number.
2. **Core Competencies as one `·` wall** — convert it to a `kv` block, four or five labelled
   groups, ≤ 7 terms each.
3. **Em-dashes** — two per page, maximum. Count them.
4. **Even sentence lengths** — put at least one sentence under nine words in the summary.
5. **Round numbers** (100%, 3x, 50+) — use the real uneven figure.
6. **Banned phrases** — *proven track record, leveraging, spearheaded, seamless, cutting-edge,
   passionate about, at the intersection of, not just X but Y*. Full list in the playbook.

**Rewrite, do not just unbold or swap punctuation** — deleting a lead-in leaves a broken sentence
(*"…for volume and for trust high-volume data pipelines"*), and swapping an em-dash for a comma
manufactures comma splices. Read every changed sentence back.

Facts never move. This is how it is written, not what it says.

### 5. Build
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/cv-tailor/scripts/build_cv.py <cv.md> --out <outdir>        # PDF
python3 ${CLAUDE_PLUGIN_ROOT}/skills/cv-tailor/scripts/build_cv.py <cv.md> --out <outdir> --docx # + Word
```
If reportlab is missing the builder first looks for another python on the machine that
has it and re-runs itself there — which is what makes this work inside a GUI app, where
`python3` is often the system interpreter with no packages. If nothing has it, the run
says so and exits **3**: the Markdown CV is complete, the PDF was not written. Do not
report a PDF that does not exist. Fix with `pip install reportlab` (add
`--break-system-packages` on an externally-managed python).

The builder auto-shrinks to fit `--max-pages 2`; if it still warns, cut content — do not
ship 3 pages.

### 5b. Title check before verifying
Read the built CV's role headers back and confirm:
1. The **headline** and the **first sentence of the summary** both contain the target title verbatim.
2. **Every** role title appears in `profile/profile.md` §4.0. Anything else is a defect — fix it.
3. Any role whose title still reads distant from the target carries a scope-equivalence line.

### 6. Verify like an ATS
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/cv-tailor/scripts/check_pdf.py <outdir>/<file>.pdf \
   --keywords "must1;must2;..." --nice "nice1;nice2" --title "<target title>"
```
Fix every FAIL and every "missing" keyword (if a keyword is not truthfully
placeable, leave it out and tell the user). Then render page images if you can
(`pdftoppm -jpeg -r 70 file.pdf page`) and look at them: no orphaned role
headers at a page bottom, no overflow, bold lead-ins scan as a checklist.
Run through `references/ats-checklist.md`.

### 7. Deliver
- Name the PDF and its folder in one line so the surface can link it. Add DOCX only if
  asked or the portal needs Word.
- Reply in ≤ 6 lines: contact set chosen + why; title label used; the top
  keywords you led with; anything you need the user to confirm (a fact you lacked,
  a framing choice). No essays.
- If the user shared new career facts during the run, tell them in one line that
  `profile/profile.md` should be updated with them, and update it if
  you have write access to the skill folder (Claude Code / Desktop).
- If this run taught something durable about what works on a CV, record it:
  `python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py add-lesson "<observation>" --tag cv`

## If you cannot run code (Chrome extension, mobile without a container)
Do steps 1–4 fully and output the content JSON in a code block plus the
5-line summary; tell the user to run "build this CV" in Claude Desktop/Code where
the builder can execute. Never hand-write a "PDF" in chat.

## The CV Markdown format

YAML frontmatter carries the header and the target; the body carries the sections. The
`<!-- blocks: -->` marker after a heading says how its list items should be read — it is an HTML
comment, so it is invisible in every Markdown renderer.

```markdown
---
type: cv
title: Jane Doe — VP Engineering
tags: [jobsearch, cv]
name: Jane Doe
headline: "VP Engineering · one differentiator, in the target's own words"
output_basename: Jane_Doe_CV_Company
company: <target company>
role: <target title, verbatim>
target_type: <listed scale-up | seed startup | accelerator | agency>
contact_set: <which set from profile/profile.md §1, and why in one clause>
email: jane@example.com
phone: "+00 000 000 000"
location: City, Country
status: <citizenship / work authorization — whatever the profile's status line says>
links:
  - text: linkedin.com/in/janedoe
    url: https://www.linkedin.com/in/janedoe/
---

## Professional Summary
<!-- blocks: prose -->

Four sentences. Target title verbatim and **bolded** in the first one.

## Core Competencies
<!-- blocks: kv -->

- **Architecture:** Cloud-native · distributed systems · event-driven · multi-tenant SaaS
- **AI / ML:** LLM systems · agentic AI · retrieval architecture · embeddings
- **Leadership:** Leading senior engineers · hiring · executive communication

## Work Experience
<!-- blocks: mixed -->

### Chief Technology Officer | Northwind Data · one-line company descriptor
*07/2021 – 04/2022*
City, Country · what the company does
<https://northwind.example>

An optional italic scope-equivalence line goes here, after a blank line.

- **Bold lead-in:** the outcome-first bullet.
- A bullet with no lead-in — at most half of them should carry one.

#### Earlier ventures and roles

## Why This Role
<!-- blocks: mixed -->

- **Strongest match.** …
- Second match. …
- **On fit and logistics:** the honest calibration.

## Education
<!-- blocks: entries -->

- **Degree** · Institution — 06/2017
```

**Block kinds.** `prose` = paragraphs · `kv` = labelled competency groups · `entries` = a
two-column list with the right column right-aligned (education, awards, certifications) · `mixed` =
roles, bullets, subheadings and paragraphs together. When the marker is absent the heading name
decides (`Core Competencies` → kv, `Education` → entries), so a hand-edited CV still builds.

**Inline markup** in any text: `**bold**`, `*italic*`, `[label](https://url)`.

**`kv` is how Core Competencies must be written** — four or five labelled groups, not one
middot-separated wall of fifty terms. The wall is the loudest "generated by a machine" signal on the
page, and no recruiter reads past its third line. Same keywords, same ATS value, a fraction of the
visual noise.

**A role's meta lines are the ones directly under the `###`, with no blank line between them**:
italic is the dates, `<...>` is the company URL, anything else is the location and descriptor. The
blank line is what separates them from a following paragraph — keep it.

Section order for ATS: Professional Summary → Core Competencies → Work Experience →
(programme-specific section) → Education → Technical Skills (optional).

`scripts/cv_md.py` converts between this and the internal structure
(`to-md`, `to-json`, and `check` for a round-trip gate over a folder of CVs).

## Non-negotiables
- Truth boundary: nothing outside `profile/profile.md` (playbook §0).
- One phone, one primary location, no DOB by default.
- **The status line says what the profile's status line says** — citizenship and work
  authorization, nothing else. No time zones, no overlap hours, and **never** a statement that the
  role would need visa sponsorship: the form asks that question and it is answered honestly there,
  not volunteered on the CV where it only ever costs the user a screen.
- **One link in the header, and it is LinkedIn**, unless the profile names another. Every extra link
  is a place the reader leaves the page.
- **Mark remote roles as remote.** When someone worked for a foreign employer from their own
  country, write `Remote from <country> · <Employer country> company (<city>)`, never just the
  employer's city — otherwise the reader assumes they lived there, and the assumption surfaces
  later as a discrepancy.
- **Typeface: one sans family, no serif.** A display serif on a CV reads as a template.
- **Colour: one deep blue** (`#1F4E8C`) on the headline, section headings and links. Nothing else is
  coloured. Bright web-blue everywhere is what makes a CV look generated; no colour at all reads as
  a plain-text dump.
- Target title verbatim in headline and summary.
- ≤ 2 pages; PDF always; verified with `check_pdf.py` before delivery.
- Reverse-chronological, continuous timeline, consistent date format.
