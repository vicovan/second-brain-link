---
name: job-scout
description: Sweep the market daily for the roles the user actually wants, score them against their own criteria, and deliver a ranked, applyable shortlist with a saved report. Use for the daily job scan, "any good jobs today", or a fresh search of the market.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, TodoWrite
---

# Job Scout

A daily sweep of the market for the roles the user actually wants **and can win**, scored against
their real profile, deduped against everything they have already been shown, and delivered as a
ranked shortlist of up to 10 — only jobs that clear the apply floor — with a saved report.

**Fewer, better applications win more interviews than many average ones.** A recruiter who sees
the same person apply as CTO, ML scientist and product director in one week reads none of them
seriously, and every application that is auto-rejected teaches the system nothing. The shortlist
is judged by the interviews it produces, not by its length.

**This skill finds jobs. It does not write CVs.** If the user pastes *one* job description
and wants a document, that is **`cv-tailor`** — hand off and stop. This skill's
output is the shortlist; the CV skill turns one item on it into a PDF.

## Files

| File | Read when |
|---|---|
| `profile/search-criteria.md` | ALWAYS. What they are looking for — lanes, geography, comp, red flags. |
| `references/sources.md` | ALWAYS. Which sources work, the exact commands, and what not to retry. |
| `references/scoring-rubric.md` | Before ranking. The 100-point scale, shortlist likelihood, the apply floor, the disqualifiers. |
| `profile/archetypes.md` | Before scoring. The lanes the user targets and each lane's trigger keywords — a job matching no lane is dropped. |
| `${CLAUDE_PLUGIN_ROOT}/skills/job-apply/scripts/knockout.py` | Step 5 — every fetched posting is knock-out screened before it is scored. |
| `<brain>/45-jobs/profile/profile.md` | ALWAYS. The **only** source of facts about the user. Never copy it here. |
| `scripts/ats_pool.py` | Tier-0 bulk probe of many companies' open ATS boards → JSON. |
| `scripts/ats_fetch.py` | Tier-1 drill-down into one company's Greenhouse/Lever/Ashby board. |
| `scripts/scout_state.py` | Daily gate, search window, dedupe, report path. |
| `scripts/learn.py` | The shared feedback loop — `show` at step 0, `add-lesson` at the end. |
| `<state root>/lessons.md` | **Step 0, always.** Rules earned from real outcomes. |

State lives in `<state root>/` — outside the skill folder, so it never lands in
a zip: `last-run.txt`, `snooze.txt`, `seen.json`, `reports/YYYY-MM-DD.md`.

## Workflow

Let `S` = the skill dir (`${CLAUDE_PLUGIN_ROOT}/skills/job-scout`).

### 0. Load the profile — REQUIRED, before anything else

Everything this skill knows about the person comes from their profile. Resolve it:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/paths.py     # prints the profile dir for this surface
```

**Read order:** this surface's `45-jobs/profile/` → the other surface's, used with a one-line notice
and an offer to copy it here → **run `job-search:job-onboarding` (the **Skill** tool)**. Never guess a compensation floor, a
location or a target title: a run built on invented criteria costs the user a whole day and
produces a shortlist they would never act on.

### 0a. THE NORTH STAR — interviews
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py kpi
```
**The single measure of whether this system works is how many applications turn into a screen or
an interview.** Submissions are the means, not the result: eighteen fast rejections are worse than
three considered applications, because they burn the employer's first impression and teach
nothing.

Read the KPI's tables before sweeping:
- **By archetype** — a lane with several answered applications and no reply is the first to
  narrow. Say so in the report; the lanes themselves are the user's call.
- **By score band** — once `learn.py calibrate` has ≥ 5 results, it says whether the score
  predicts replies. A flat or inverted score is a scoring bug to raise, not noise.
- **Stopped before sending** — knock-out and review skips are the gates working; a *scouting* bug
  is a job that reached the shortlist and was then stopped for something visible in the posting.

If applications are open with no result, remind the user once to record them
(`learn.py set-result --job-key K --result rejected`, or `--all-open`) — the loop learns nothing
until they do.

### 0b. Load what past runs learned  (never skip)
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py show
```
`lessons.md` holds rules earned from real application outcomes — which sources actually reply,
which shapes of role never do. Apply them when scoring. If a rule conflicts with
`profile/search-criteria.md`, say so and follow the criteria; the criteria are the user's, the rules are the
loop's suggestion.

### 0d. How links must be written in a rendered note

Three separate limits in Second Brain Studio's reader, each of which produced a link that looked
broken before it was found. All three are load-bearing — do not "simplify" this.

**1. A link resolves by `title:` — never by filename.** The live index is keyed on the note's
frontmatter title alone. So `[[CV Northwind]]` works only because the rendered CV
*is titled* `CV Northwind`. **Whatever a note is linked as, that must be its `title:`** — this applies
to the shortlists (`Shortlist 2026-01-15`) and the application notes too, and it is why the
renderer runs the title and the filename through the same `safe()` call: a company like
"Northwind Ventures / Atlas" cannot carry its slash into a filename, so the title must not either.

**2. A table cell cannot contain an aliased wikilink.** A row is split on a bare `|`
(`brain-md.ts`, a plain `.split('|')` with no escape handling), so `[[Long_Name|CV]]` is torn in
half and the reader sees `[[Long_Name` in one column and `CV]]` in the next. Escaping as `\|` makes
it worse — the alias regex swallows the backslash into the target and the link stops resolving.

| Where | Form | Label comes from |
|---|---|---|
| A table cell | `[[CV Northwind]]` | the target's own title — so **name the artefact how it should read** |
| A note body | `[[CV Northwind\|CV]]` | the alias; no splitting happens here |

**In the report you are writing, use the relative path, not the wikilink** —
`[CV](../applications/<date>/<job_key>/<file>.pdf)`. `render_brain.py` rewrites it into
`[[CV <Company>]]` when it mirrors the report into the brain, and it is the only thing that
knows the final label: a second role at the same company gets `CV Northwind Search`, which
you cannot predict while writing. A wikilink you invent yourself is a coin flip that renders
grey when it loses. (If you do write one anyway, the renderer repoints it where it can —
belt and braces, not a licence.)

A bare `CV` cannot be the name: links resolve globally, so twenty-two files called `CV` would
collapse onto one target and most rows would open the wrong CV. `CV <Company>` (plus a role word
when a company appears twice) is the shortest label that still points at the right file.

**3. Only `.md` is indexed.** The walker takes `.md` and nothing else
(`vaultIndexStore.ts` — *"a vault = an entire `.md` tree"*), so **a PDF can never be a link in
Studio.** Do not emit `[[file.pdf]]`; it is permanently grey. Name the PDF in frontmatter and in
the text instead — the file still sits beside the note and opens from Obsidian or Finder.

**And never emit a link to a note that does not exist.** A phantom `[[Company]]` is a healthy
concept in Obsidian and reads as a broken link everywhere else. Check first, and fall back to plain
text — `org_index()` does this against `15-organizations/` and `10-people/` by filename only, which
stays cheap on a 26,000-note vault. **After changing anything about links, re-verify by replicating
the resolver** (walk `*.md`, key on `title:`, resolve every `[[…]]`); the target is zero unresolved.

### 1. Frame the run — and OPEN TODAY'S REPORT FIRST
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py stats
DAYS=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py window)   # 1–14, since the last run
REPORT=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py report-path)
```

**Create `$REPORT` NOW, before searching anything**, with the frontmatter, today's date and a
`## Status` line saying what you are about to do. Then render it into the vault so it appears
in the tree straight away:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/render_brain.py --quiet
```

**Then keep it current as you go** — rewrite the `## Status` line at the end of each step
("sweeping Tier 0 · 47 boards", "scoring 205 survivors", "reading the top 15"), and re-run
`render_brain.py --quiet` after each rewrite.

**Why this and not a report at the end:** a sweep takes minutes, and Second Brain Studio opens
this note beside the conversation and refreshes it as it changes on disk. A file that only
appears at the end leaves the user watching an empty pane with no way to tell the run from a
hang — which is exactly the failure this ordering exists to prevent. It also means an
interrupted run still leaves a record of how far it got.
Read `profile/search-criteria.md` and `profile/profile.md` before searching, not after. If the user
named a focus in their message ("remote only", "AI architect roles", "founder programmes"),
narrow to it and say so. Otherwise sweep all three lanes.

### 2. Sweep — Tier 0, the open ATS boards
Start where the forms are open by construction, so shortlist slots are not spent on roles
behind account walls. Two passes, both of them:
```bash
# (a) bulk-probe every known company board, concurrently
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/ats_pool.py \
        --out /tmp/scout-ats.json \
        --titles "<seniority band, criteria §1>" \
        --domain "<discipline, criteria §1>" \
        --regions "<geographies to keep, criteria §3>" \
        --exclude-titles "<exclusions, criteria §5>"
```
`ats_pool.py` ships **neutral** defaults on purpose — it filters on nothing but job-type
noise until you pass the profile's own criteria in. Never leave the flags off and never
hardcode a lane here; an empty-handed run returns the whole market, which is the honest
failure rather than silently applying someone else's rules.

(b) then a site-restricted `WebSearch` pass across `jobs.lever.co`, `job-boards.greenhouse.io`,
`jobs.ashbyhq.com` and `jobs.smartrecruiters.com`, building the titles from criteria §1 and the
geographies from §3 — never from a list hardcoded in this skill. Search indexes go stale, so
confirm each hit is still live on the board before it reaches a shortlist.

### 2b. Sweep — Y Combinator
Include `ycombinator.com/jobs` every run — see `sources.md` Tier 3. AI-native, well-funded,
remote-friendly companies. Note the apply flow needs a workatastartup.com login, so mark those
rows `⛔ YC login` in the Apply column and ask the user whether they are signed in.

### 3. Sweep — Tier 2, WebSearch
Cover what the ATS boards miss: founder programmes and EIR tracks, aggregators that block
direct fetching, and anything niche. Query patterns are in `sources.md` §Tier 2.

### 4. Merge and dedupe
Combine every source into one JSON list, then drop what they have already seen:
```bash
python3 - <<'PY' > /tmp/scout-all.json
import json,glob
rows=[r for f in glob.glob('/tmp/scout-*.json') for r in json.load(open(f))]
json.dump(rows,__import__('sys').stdout,indent=2,ensure_ascii=False)
PY
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py filter-seen < /tmp/scout-all.json > /tmp/scout-new.json
```
The count it prints to stderr ("N in, M new") is worth reporting — it tells the user whether
the market moved.

### 4b. Screen out the exclusions BEFORE scoring
Drop anything matching the user's own exclusions in `profile/search-criteria.md` §2
(deal-shape exclusions) and §5 (sector and employer exclusions). Those lists are theirs —
this skill has no opinion about which sectors or arrangements are acceptable, and must never
apply an exclusion the profile does not state. **Do not rely on the title and company name
alone**: an employer in an excluded sector can post under a holding name or as "Stealth" with
nothing identifying in either field, and only reading the posting reveals it. Any employer
whose sector is unclear must be read before it is ranked. Report the count of exclusions in one line; do not list them all.

### 5. Shortlist, then read the real postings
Map each candidate to an **archetype** from `profile/archetypes.md` by its title and trigger
keywords; one that matches no lane is dropped here (count it, do not list it). Then score
cheaply from title + company + location. Take the **top ~15** and `WebFetch` each posting for
what only the full text reveals: comp, work-authorization wording, whether "CTO" means CTO,
team size, funding. Do not fetch all of them — that is the expensive step and most candidates
die on the title alone.

**Knock-out screen every fetched posting** (save the text, then):
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-apply/scripts/knockout.py --jd /tmp/posting-<n>.txt
```
`STOP` → out of the ranking, into an "excluded — knock-out" line with the quoted sentence. `FLAG`
→ keep, and show the flag in the job's Flag line. This is where UK-only, citizenship-gated,
language-gated and below-floor roles leave the list, *before* anyone tailors a CV for them.

### 5b. Applyability check — BEFORE anything reaches the shortlist
**A job the user cannot actually apply to does not belong on the shortlist.** For every candidate that
survives scoring, establish how the application is submitted *before* ranking it:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-apply/scripts/detect_portal.py "<url>" --fetch
```
- `linkedin` → **resolve it first** (ATS board · `site:job-boards.greenhouse.io "<company>"` ·
  the company's own /careers page). Classify the resolved URL, not the LinkedIn mirror.
- `walled` (Workday, Taleo, SuccessFactors, iCIMS, **join.com**, BrassRing, Oracle HCM, Avature,
  Eightfold, Phenom, Cornerstone) → **drop it from the shortlist.** Claude cannot create accounts
  and the user has said they do not want these. List them in an "excluded — account wall" line, do not
  rank them.
- `fillable` → keep, and **record the real apply URL in the report** so the apply step does not
  have to rediscover it.
- `unknown` → fetch the page and look for an account wall (*create an account · sign up to apply ·
  register to apply · log in to apply · set a password*). Treat as walled if found.

The report's top-10 table carries an **Apply** column: `✅ direct form (<ats>)` · `⛔ account wall` ·
`✉️ email only` · `? unverified`. **A row must not say `?` in a delivered report** — verify it or
leave the job out.

This costs a few fetches per run and saves the user discovering the wall themselves after reading a role
they liked. It is not optional.

### 6. Score and rank
Apply `references/scoring-rubric.md` — six components out of 100 including **shortlist
likelihood** (would a recruiter put *this* person on a call?), hard disqualifiers dropped
outright. Rank, break ties on the work-mode order in `profile/scoring.md`.

**Only jobs that clear the apply floor are shortlisted** (the floor is in `profile/scoring.md`;
the rubric's default is total ≥ 75 and shortlist likelihood ≥ 20/30). Cut at 10. On a thin day
deliver fewer and say so plainly — **never widen the search to pad the list**, and never lower
the floor to reach a number. At most one role per company, and none at a company applied to in
the last 30 days (`learn.py pending` / the ledger).

Record each shortlisted job's archetype and likelihood in the report; job-apply logs them to the
ledger so `learn.py calibrate` can check the score against what comes back.

### 7. Drill down (when it pays)
If a company looks strong, pull its whole board — the best-fitting role is often not the
one that surfaced:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/ats_fetch.py auto <company-slug> --filter "cto|vp|head of|chief|architect"
```

### 8. Finish the report, then record the run

`$REPORT` already exists — you created it in step 1 and have been updating its status line
since. Now write the **full ranked list** into it: date, what was searched, counts per source,
the top 10 with scores, reasoning, red flags and apply links, then a short "also seen / near
misses" section. Replace the `## Status` line with the final summary.

**The report shows the CURRENT list ONLY.** Never append "Run 2", "Run 3"
sections — a second sweep the same day **replaces** the list, it does not stack onto it. Rewrite
the file, carrying forward only the statuses of jobs already actioned. Permanent history lives in
`outcomes.jsonl`, not in the report.

**The top-10 table MUST have a `Status` column as its second column**, every row starting at
`⬜ not started`, followed by this legend line:

> **Legend:** ✅ applied · 🟡 filled, awaiting submit · ⬜ not started · ⛔ skipped ·
> ❌ disqualified · 🚫 excluded by criteria · 🔵 replied · 🎯 interview

**The table needs a `Status detail` column.** The emoji alone does not tell them
what is happening. Every row carries one plain sentence, rewritten each time the state changes —
what was done, what is blocking it, what was decided and why:

- `✅ **Submitted** — confirmation page reached. Seven dropdowns had to be re-set: the values displayed but never registered.`
- `🟡 **Filled, submit blocked** — form complete and CV attached, but the domain is refused by the Chrome extension.`
- `⛔ **Skipped on the user's call** — the role centres on distributed LLM training, not their experience. Form left filled.`

**Update it the moment anything happens, never in a batch at the end.** They watch this file while
the run is in progress, and they have had to ask twice.

**The report table is the user's live dashboard.** They watch this file to see what
is happening, so it must be true at every moment, not at the end of a run:

- **Every role title is a clickable markdown link** to its apply URL.
- **Every row carries a `CV` column**: the word `CV` as a clickable link to the exact PDF that was
  sent. Use a **relative path** from the report — `[CV](../applications/<date>/<job_key>/<file>.pdf)`
  — which `render_brain.py` turns into `[[CV <Company>]]` in the brain's copy, pointing at the
  CV's Markdown note so it opens in the reader (see §0d).
  **Never a `file://` URL**: markdown viewers refuse those and render the raw path as text, which is
  exactly what the user does not want to see. If no CV exists yet, the cell is `—`.
- **Status is updated the moment it changes**, not in a batch at the end: `⬜ not started` →
  `🟡 form being filled / awaiting submit` → `✅ applied`, or `⛔ skipped` / `❌ disqualified` with
  the reason beside it. A row that is stale is a bug.
- The **Application log** table at the bottom gains a row the moment a job is picked up.

**Every role title in the table must be a clickable markdown link to its apply URL** — `[Director of Engineering, Platform](https://job-boards.greenhouse.io/<company>/jobs/<id>)`.
They open jobs straight from this table; a title they cannot click is a dead row. Link the near-misses
section the same way.

Include a **Comp** column too — posted figure, "not posted", or the exclusion reason. The user's
strongest filter is money, so it belongs in the table rather than a footnote.

the user tracks their pipeline from this table, so it is not decoration — a report without it is incomplete. Then:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py add-seen < /tmp/scout-new.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py mark-run
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/render_brain.py --quiet     # mirror the dashboard into the brain
```
**Record only after the report is written** — a crashed run should be repeatable.

`render_brain.py` mirrors the report into `<brain>/45-jobs/reports/Shortlist <date>.md` — plus
the dashboard, the lessons and one folder per application under
`45-jobs/applications/<date>/<job_key>/` — so the user opens the same dashboard from Obsidian
or Second Brain Studio. Run it again after **every** status change, not just once at the end:
it is a no-op when nothing moved, and silent when no brain is reachable.
(`publish_report.py` is the separate command that copies a report into `<brain>/_notes/`.)

### 9. Deliver
In chat: the shortlist, **three lines each** in the rubric's format (rank, title, company,
location/mode, score · why it fits · flag → link). Then one closing line on what the day
looked like. No essays, no restating their CV back at them.

Close by offering the handoff: *"Want a tailored CV for any of these? Say the number."* —
that runs **`cv-tailor`** with the chosen posting.

## The daily prompt

A `SessionStart` hook in `~/.claude/settings.json` checks `scout_state.py due` and, on
the user's first message of a day where the scout has not run, injects a nudge asking whether
to run it. Handle it like this:
- Ask once with `AskUserQuestion` — "Run the daily job scan?" / "Not today".
- On **no**: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py snooze` and carry on with whatever they
  actually asked. Never re-ask that day.
- On **yes**: run the workflow above.
- If they ignore it and asks for something else, **drop it** and do their work. The nudge is
  an offer, not a gate — never let it hijack a session.

## Non-negotiables

- **Facts only from `profile/profile.md`.** Never claim a skill, year or title they lack
  in order to justify a match. If a role needs something they do not have, that is a red
  flag to report, not a detail to gloss.
- **Never apply, never message a recruiter, never submit anything.** Hand them the link.
- **Never fabricate a listing, a salary or a company.** Every job in the report carries a
  real URL that was actually fetched. If a source returned nothing, say so.
- Public endpoints only, keep the built-in rate delays, and no Chrome on a routine run
  (see `sources.md` Tier 5).
- Deduped against `seen.json` — they should not be shown the same job twice. If a genuinely
  better-matching *re-post* appears, say it is a repost.
