---
name: cv-tailor
description: Build a tailored, ATS-first CV as Markdown and PDF for one target job, from the user's own career profile. Use whenever a job description, JD, role, accelerator or investor programme is shared, or the user says "tailor my CV", "resume for this", "apply to this", or shares a new career fact.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebFetch, Skill
---

# CV Tailor

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/job-apply/references/`). Tool:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/memory.py`, scope `job-search`, tags `cv`.
1. **First:** `memory.py recall --scope job-search --tags cv` — apply it, say in one line which items changed what you do, never re-ask what it answers.
2. **User says a preference, rule or correction** → `observe --source user` at once (`--scope shared` if it holds for every agent).
3. **An outcome lands** (a reply, rejection or interview (`learn.py set-result`), a reviewer's verdict, a knock-out, a form that failed) → `observe --source outcome` with the evidence, `--match` the item it strengthens.
4. **Last:** at most 3 inferred lessons → `observe --source agent` (saved and used at once, flagged as inferred — the user can edit or remove them); end with *"Learned: …"*.


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
| `<app dir>/posting.md` | Written at step 1 (or by job-apply). The JD text the gates check vocabulary against. |
| `<app dir>/fit.md` | ALWAYS when it exists (job-apply writes it). The two-pass requirement table, keywords, reviewer doubts, gaps. Build the CV from its `existing`/`supported` rows only. |
| `<profile>/archetypes.md` | ALWAYS. The lane this job belongs to decides the headline, summary skeleton, lead proof points and bullet priority. |
| `scripts/lint_cv.py` | Before building and after every edit. The deterministic gate — chronology, fact gate, de-tell, self-disqualifiers. Its result goes into `gates.json`. |
| `assets/example-cv.md` | Once, to see the Markdown shape and the register to write in. It passes every gate; copy its shape, never its (fictional) facts. |
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

### 0c. Know the archetype
Read `profile/archetypes.md` and pick the lane this job belongs to (the scout already recorded it
if the job came from a sweep). The archetype supplies the headline pattern, the summary skeleton,
the proof points to lead with, and the framing policy for concurrent roles. **A job that fits no
archetype is not tailored** — say so and stop; that is a targeting problem, not a writing one.

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
- **Save the JD text as `<outdir>/posting.md`** unless job-apply already did. `lint_cv.py` reads
  it to allow the posting's own vocabulary; without it every posting-only term fails.
- **Write `<outdir>/fit.md`** (playbook §1b) unless job-apply already did: pass 1 from the JD
  alone, pass 2 against the profile, then `## Keywords`, `## Bullet plan`, `## Reviewer doubts`,
  `## Gaps`. The **bullet plan** maps each `critical`/`high` requirement to the one role and the
  one profile fact that proves it, and names the three roles that get depth. The CV is written
  from the plan; a bullet that serves no row is not written.

### 2. Decide the contact set
Apply playbook §2. Output exactly one phone + one primary location (dual city
allowed only for global programmes). Note the reason in one clause for the
final message.

### 3. Read the master profile and select
- If `45-jobs/profile/cv/` holds the user's own CV (uploaded via Studio -> Jobs Agent ->
  Settings), read it too — it carries their real wording, which `profile.md` may have
  summarised away. Never contradict `profile.md`; it stays the source of truth for facts.
- Read `profile/profile.md` in full.
- **Apply the profile's CV conventions (§10)** — date format, spelling system, title forms — and
  each role's **public record** for dates and location, **company site** for the URL line, and
  **acquired / renamed** for one continuous entry under the new owner. Where a profile predates
  these fields, use what it has and tell the user in one line that `/onboard` → "upgrade my
  profile" adds them.
- **Title mirroring — playbook §3, the three-rung ladder.** Mirror the target title verbatim in the
  headline (the summary may use it once, naturally — never as a bolded opener); use an allowed title variant for each role
  where one matches; otherwise keep the true title and add a one-line **context line** — team
  size, who the role reported to, what it covered. **Never write a title the user did not hold** —
  titles are the most verifiable thing on a CV.
- **Set the title for EVERY role, not just the headline.** Go through
  `profile/profile.md` **§4.0 Allowed title variants** and pick the closest variant per role using
  the target map there. `§4.0` is a closed list — nothing outside it may appear as a title.
- **Add a context line under any role whose title still reads distant from the target**
  (playbook §3, rung 3): one plain, factual sentence — *"Led 23 engineers and two managers,
  reporting to the CTO."* It states the reach in numbers a recruiter can weigh. It **never names
  the target title or a level** ("VP-level", "director-level scope", "scope equivalent to…"): a
  candidate describing the level they want reads as tailoring, and `lint_cv.py` fails it.
- Their titles are often **more senior** than the target — keep them, never downgrade.
- **Rewrite every past role for this target — playbook §3b.** Four moves: (1) reframe each
  company's descriptor line toward the target's world; (2) **select** 2–5 bullets per recent role
  and drop the rest — the bank is a superset, not a checklist; (3) restate the same facts in the
  **JD's exact nouns and verbs** (if they say "ship", do not write "deliver"); (4) order bullets so
  the first one under the most recent relevant role answers the JD's **#1 requirement**.
- Rewriting = the same true fact in their words. **Never add scope, scale or numbers** that are not
  in `profile/profile.md` §7.
- Write the **Skills** line (the last section): one plain comma-separated line of 12–18 terms,
  JD must-haves first, each one truthfully supported by the profile. No grid of labelled skill
  groups at the top of the page — recruiters read it as generated, and the ATS gets the same
  keywords from the bullets and this line.
- Apply the company-type variant (playbook §7) and regional convention (§8).
- Decide the older-roles depth (merge roles more than ten years back unless relevant).
- For full-time employee targets, decide how the user's own ventures and side
  projects are framed (playbook §6); if unclear, ask the user the one framing
  question and use the default (current venture as the current role) meanwhile.

### 3b. Write the summary — playbook §3c
- **Professional Summary, rewritten from scratch every time.** Three or four sentences, implied
  subject (no "I"), that say who this person is and why they fit THIS role: the career in one
  line · the JD's riskiest `critical` requirement answered with a specific fact · a scale
  credential (team, org, users) from the profile. It reads like a confident senior person
  describing their own career — not credentials glued with semicolons, not "<Title> profile:". **55–90 words, no sentence over 28 words, at least one under 12.** The top
  five `fit.md` keywords inside it. Plain words: a recruiter who is not an engineer must
  understand every sentence.
- **Never name a gap on the CV** (playbook §3c, "Gaps never go on the CV"). Gaps live in
  `fit.md` for interview prep.
- **No "Why This Role" section** (playbook §3d). That material goes to the cover letter and the
  why-answers, which job-apply writes from `company.md`.
- **Roles in strict reverse-chronological order.** Relevance comes from bullet count and depth,
  never from moving a role up.

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

### 4b. The gate, then the de-tell pass — playbook §3e
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/cv-tailor/scripts/lint_cv.py cv <outdir>/<cv>.md \
   --profile <profile>/profile.md --fit <outdir>/fit.md
```
**Every FAIL is fixed before building** — chronology, a "Why" section, first person, a named gap,
banned phrases, negative parallelism, em-dash and bold-lead-in counts, and any number, employer or
title that is not in the profile. Re-run until it prints `RESULT: PASS`; the result is recorded in
`<outdir>/gates.json`, and an application whose CV gate is red cannot be logged as applied.

Then read the Markdown back for the tells the linter cannot count. The short version, in order of
how loudly each one shouts:

1. **The same bullet shape everywhere.** `**Label:** a, b, c` on every bullet (the bold-lead-in
   tell's replacement) — at most one per role, three per CV. Bold lead-ins on at most half the
   bullets. Rewrite the rest to open with a verb or with the number.
2. **Long sentences and jargon.** No bullet sentence over 32 words; no more than three acronyms or
   product names in one bullet; no system-design vocabulary the posting does not use
   (*deterministic, orchestration, end to end*, algorithm names). Say what changed for whom.
3. **The headline** — the posting's title first, then one short differentiator, ≤ 80 characters.
   The title never reappears in the bullets, and no "-level" phrasing anywhere.
4. **A skills grid at the top** — no labelled skill groups above the work history. Skills are one
   plain line at the end.
5. **Em-dashes** — two per page, maximum. Count them.
6. **Even sentence lengths** — put at least one sentence under twelve words in the summary.
7. **Round numbers** (100%, 3x, 50+) — use the real uneven figure.
8. **One date format** — `MM/YYYY` throughout when the profile has months, `YYYY` throughout when
   it does not. Never both on one CV.
9. **Banned phrases** — *proven track record, leveraging, spearheaded, seamless, cutting-edge,
   passionate about, at the intersection of, not just X but Y*. Full list in the playbook.

**Rewrite, do not just unbold or swap punctuation** — deleting a lead-in leaves a broken sentence
(*"…for volume and for trust high-volume data pipelines"*), and swapping an em-dash for a comma
manufactures comma splices. Read every changed sentence back.

Then **the bullet test, one bullet at a time** (playbook §3f): only-you · so what · read aloud ·
serves the posting · one idea. Read every bullet as the recruiter will — two seconds, no context.
A bullet that fails and cannot be made specific truthfully is cut. Then **the consistency pass**
(playbook §3g): spelling system, title forms, tense, punctuation, dates, capitalisation.

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
1. The **headline** contains the target title verbatim, first.
2. **Every** role title appears in `profile/profile.md` §4.0. Anything else is a defect — fix it.
3. Any role whose title still reads distant from the target carries a scope-equivalence line.

### 6. Verify like an ATS
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/cv-tailor/scripts/check_pdf.py <outdir>/<file>.pdf \
   --keywords "must1;must2;..." --nice "nice1;nice2" --title "<target title>"
```
Fix every FAIL and every "missing" keyword (if a keyword is not truthfully
placeable, leave it out and tell the user). `check_pdf.py` also fails a bullet whose wrapped
line fell back to the left margin — a human reads that as a broken document.
Then render the pages and **look at them**:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/cv-tailor/scripts/check_pdf.py <outdir>/<file>.pdf --png <outdir>/_pages
```
Read each PNG: every bullet whole with a hanging indent, no role header alone at a page bottom,
no role line wrapping onto a second line (shorten the descriptor), no overflow. Run through
`references/ats-checklist.md`.

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

Three or four sentences in plain words: who this person is and why they fit this role.

## Work Experience
<!-- blocks: mixed -->

### Chief Technology Officer | Northwind Data · One-Line Company Descriptor in Title Case
*07/2021 – 04/2022*
City, Country · what the company does
<https://northwind.example>

*An optional italic context line goes here, after a blank line: team, reporting line, reach.*

- Opens with a verb, says what changed for whom, then how.
- **A bold lead-in:** at most one "Label:" bullet per role.

#### Earlier Experience

## Education
<!-- blocks: entries -->

- **Degree** · Institution — 2017

## Skills
<!-- blocks: prose -->

Distributed systems, multi-tenant SaaS, LLM systems, hiring and developing managers, Python, AWS
```

**Block kinds.** `prose` = paragraphs · `kv` = labelled competency groups · `entries` = a
two-column list with the right column right-aligned (education, awards, certifications) · `mixed` =
roles, bullets, subheadings and paragraphs together. When the marker is absent the heading name
decides (`Core Competencies` → kv, `Education` → entries), so a hand-edited CV still builds.

**Inline markup** in any text: `**bold**`, `*italic*`, `[label](https://url)`.

**No skills block at the top of the page** — neither a middot wall nor a grid of labelled `kv`
groups. Both read to a recruiter as generated, and both push the work history below the fold. The
keywords live in the bullets (where the evidence is) and in one plain `## Skills` line at the end;
the ATS indexes both. `lint_cv.py` fails a skills section or `kv` block above the work history.

**A role's meta lines are the ones directly under the `###`, with no blank line between them**:
italic is the dates, `<...>` is a company URL (one line each; an acquired employer may carry both
the new owner's site and the old one), anything else is the location and descriptor. The
blank line is what separates them from a following paragraph — keep it.

Section order: Professional Summary → Work Experience → (Open Source, or a programme-specific
section) → Education → Skills.

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
- **A link always shows its URL as the visible text** — `[example.com](https://example.com)`,
  never `[Project Name](https://…)`. A printed CV, a PDF-to-text parser and an ATS all drop the
  hidden target, so a linked title leaves the reader with no address at all.
- **Mark remote roles as remote.** When someone worked for a foreign employer from their own
  country, write `Remote from <country> · <Employer country> company (<city>)`, never just the
  employer's city — otherwise the reader assumes they lived there, and the assumption surfaces
  later as a discrepancy.
- **Typeface: one sans family, no serif.** A display serif on a CV reads as a template. The
  builder picks a designed open-licensed sans when one is installed (IBM Plex Sans, Source Sans 3,
  Inter, Lato), else a system sans; it never downloads a font.
- **Design is drawn, never written.** The accent band, the section-rule accents and the bullet
  colour are vector shapes with no text in them, so the page still extracts as one clean column.
  The only running text is the page-2+ footer (`name · page`), drawn after the page content so a
  parser reads it last. Never add icons, photos, columns, text boxes or contact details in a
  header/footer — those are what break scrapers.
- **Colour: one deep blue** (`#1F4E8C`) on the headline, section headings and links. Nothing else is
  coloured. Bright web-blue everywhere is what makes a CV look generated; no colour at all reads as
  a plain-text dump.
- Target title verbatim in the headline.
- ≤ 2 pages; PDF always; verified with `lint_cv.py` (gate green) and `check_pdf.py` before delivery.
- Strictly reverse-chronological, consistent date format; overlaps framed per the profile's
  framing policy.
- No "Why …" section, no first person, no named gap — on any employment CV.
- **Every bullet in the three most recent roles serves a `fit.md` requirement.** A true,
  impressive bullet that answers nothing in the posting is cut (`lint_cv.py --fit` fails more than
  one per role).
- **Employment roles lead.** For an employee-track application the most recent employed role sits
  on top; the user's own venture or open-source project is framed per the profile's framing
  policy, normally its own small section, never above the employed role.
- **The CV agrees with the user's LinkedIn** on titles, employers and dates — a recruiter checks.
