---
name: job-scout
description: Sweep the market daily for the roles the user actually wants, score them against their own criteria, and deliver a ranked, applyable shortlist with a saved report. Use for the daily job scan, "any good jobs today", or a fresh search of the market.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, TodoWrite
---

# Job Scout

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/job-apply/references/`). Tool:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/memory.py`, scope `job-search`, tags `scoring,sourcing`.
1. **First:** `memory.py recall --scope job-search --tags scoring,sourcing` — apply it, say in one line which items changed what you do, never re-ask what it answers.
2. **User says a preference, rule or correction** → `observe --source user` at once (`--scope shared` if it holds for every agent).
3. **An outcome lands** (a reply, rejection or interview (`learn.py set-result`), a reviewer's verdict, a knock-out, a form that failed) → `observe --source outcome` with the evidence, `--match` the item it strengthens.
4. **Last:** at most 3 inferred lessons → `observe --source agent` (saved and used at once, flagged as inferred — the user can edit or remove them); end with *"Learned: …"*.


A daily sweep of the market for the roles the user actually wants **and can win**, scored against
their real profile, deduped against everything they have already been shown, and delivered as a
ranked shortlist sized to the **daily target** — only jobs that clear the apply floor — with a
saved report.

**The daily KPI is valid applications: `daily-target:` (default 10) a day**, counted across every
run of the day. *Valid* means sent through every gate — knock-out, CV and answers lint, and a
`shortlist` recruiter verdict. Roughly half of what gets picked dies at those gates, so the
shortlist must be bigger than the target: `learn.py target` prints the size from the user's own
recent yield. **Volume never buys a weaker application.** A recruiter who sees the same person
apply as CTO, ML scientist and product director in one week reads none of them seriously — so the
target is met with more roles *inside* the user's lanes, not with roles outside them.

**This skill finds jobs. It does not write CVs.** If the user pastes *one* job description
and wants a document, that is **`cv-tailor`** — hand off and stop. This skill's
output is the shortlist; the CV skill turns one item on it into a PDF.

## Files

| File | Read when |
|---|---|
| `profile/search-criteria.md` | ALWAYS. What they are looking for — lanes, geography, comp, red flags. |
| `references/sources.md` | ALWAYS. Which sources work, the exact commands, and what not to retry. |
| `references/regional-sources.md` | ALWAYS. Where each market posts, and the route to read each board. |
| `references/scoring-rubric.md` | Before ranking. The 100-point scale, shortlist likelihood, the apply floor, the disqualifiers. |
| `profile/archetypes.md` | Before scoring. The lanes the user targets and each lane's trigger keywords — a job matching no lane is dropped. |
| `${CLAUDE_PLUGIN_ROOT}/skills/job-apply/scripts/knockout.py` | Step 5 — every fetched posting is knock-out screened before it is scored. |
| `<brain>/45-jobs/profile/profile.md` | ALWAYS. The **only** source of facts about the user. Never copy it here. |
| `scripts/linkedin_jobs.py` | Tier 0 — LinkedIn's public, no-login job search, time-filtered (only if criteria §3b turns it on). |
| `scripts/companies.py` | Tier 1 — the company registry: every employer seen hiring, its careers board, when it was last swept. |
| `scripts/ats_fetch.py` | Tier 1 — read one company's own board: Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Personio, Teamtailor, Workday. |
| `scripts/ats_pool.py` | Tier 1b — bulk probe of many companies' open Greenhouse/Lever/Ashby boards → JSON. |
| `scripts/scout_state.py` | Daily gate, `since-seconds` window, `merge` (cross-source dedupe, new vs seen), `coverage` gate, report path. |
| `scripts/learn.py` | The shared feedback loop — `show` at step 0, `add-lesson` at the end. |
| `<state root>/lessons.md` | **Step 0, always.** Rules earned from real outcomes. |

State lives in `<state root>/` — outside the skill folder, so it never lands in
a zip: `last-run.txt`, `snooze.txt`, `seen.json`, `companies.jsonl`, `coverage.json`,
`reports/YYYY-MM-DD.md`.

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

Then the pace:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py target
```
It prints today's valid applications, what remains, and the **shortlist target** (and how many
postings to fetch to reach it). Carry both numbers into steps 5–6. If the target is already met,
say so and deliver a normal list — do not sweep for more.

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
SCRATCH=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/paths.py --scratch)       # today's working files
```
**Run every script from the brain root** (Studio starts there; a subagent may not). From another
folder the state root resolves elsewhere: the ledger gate passes roles already applied to and the
knock-out screen finds no profile. **Working files go in `$SCRATCH`, never `/tmp`** — `/tmp` is
shared by parallel agents (one builder's file overwrites another's) and can be wiped mid-run. A
parallel agent uses its own folder: `paths.py --scratch <job_key>`.

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

### 2. Sweep — discovery, every market (Tier 0)
**Older profiles** may lack criteria §3a Markets and §3b Sources. Build the markets from §3,
treat every §3b setting as its default (`linkedin-public: off`, `chrome-boards: off`,
`walled: surface`), run, and say once at the end that `/job-search:onboard` → "upgrade my
profile" adds them.

**Market first, then companies, then their own sites.** Build the query grid from the profile:
every lane title plus its common synonyms (criteria §1) × every market (criteria §3). Then, for
each market, run **every source in its pack** in `references/regional-sources.md`, limited to what
was posted since the last run:
```bash
SINCE=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py since-seconds)
# LinkedIn's public, no-login search — only if criteria §3b turns it on
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/linkedin_jobs.py --since-seconds "$SINCE" \
        --keywords "<title>" --keywords "<synonym>" ... --location "<market>" ... \
        --out $SCRATCH/scout-linkedin.json          # add --remote for a remote-only market
```
Regional boards and recruiters follow their route in the pack: `fetch` with WebFetch; `chrome`
in the user's browser **only when criteria §3b allows it**, read-only — never sign in, apply or
register; `search` with `site:` queries otherwise. Write each source's rows to
`$SCRATCH/scout-<source>.json` with `company`, `title`, `location`, `posted`, `url`, `source`,
`market`. On Codex (no browser) the `chrome` route falls back to `search`; say so in coverage.

If LinkedIn throttles (`linkedin_jobs.py` says so and stops), do not retry today. Report it and
lean on the other sources.

**The browser captures LISTS, never descriptions.** Driving Chrome is slow. Use it only to read
the result pages of sites that refuse automated fetching (the signed-in LinkedIn search when the
user allows it, some regional boards), and only to capture title, company, location, date and
link. Every description, salary line and apply-form check afterwards goes through WebFetch or the
ATS APIs. A signed-in LinkedIn read follows the pace and stop rules in `sources.md` → *On
LinkedIn* without exception: the account at risk is the user's.

### 2b. Sweep — the companies' own boards (Tier 1)
Every company discovery named goes into the registry, and every company that is hiring is then
read **at its own careers board** — the full list (roles the aggregators never showed), the
employer's own posting date, and the real apply link:
```bash
# the in-lane rows discovery found, one per job (the same filters as step 4)
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py merge \
        --titles "<criteria §1 seniority>" --domain "<criteria §1 discipline>" \
        --exclude-titles "<criteria §5>" --markets "<as in step 4>" \
        --out $SCRATCH/discovered.json $SCRATCH/scout-*.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/companies.py add < $SCRATCH/discovered.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/companies.py unresolved
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/companies.py batch > $SCRATCH/boards.txt
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/ats_fetch.py --batch $SCRATCH/boards.txt \
        --filter "<lane regex>" --out $SCRATCH/scout-careers.json
```
For each `unresolved` company (most hits first, at least the top 15): `WebSearch "<company> careers"`,
classify the page (`job-apply/scripts/detect_portal.py`), record it with
`companies.py set "<company>" --ats <type> --slug <slug>`, or `--careers <url>` for a board no
adapter reads, which you then read with WebFetch (or Chrome, if §3b allows) into
`$SCRATCH/scout-careers-<company>.json`. Stamp what you swept: `companies.py swept "<company>" ...`.

### 2c. Sweep — the open ATS pool and Y Combinator (Tier 1b, Tier 3)
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/ats_pool.py \
        --out $SCRATCH/scout-ats.json \
        --titles "<seniority band, criteria §1>" --domain "<discipline, criteria §1>" \
        --regions "<geographies to keep, criteria §3>" --exclude-titles "<exclusions, criteria §5>"
```
`ats_pool.py` ships **neutral** defaults — pass the profile's own criteria in, never hardcode a
lane. It covers US and EU tech companies on Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee
and Personio well and other markets hardly at all, which is why it is one source among several,
not the first. **An empty open-ATS sweep never proves a market is empty.** Large corporates and
whole regions (the Gulf above all) hire through job boards and account-walled enterprise portals
that no slug probe reaches; a sweep of a hundred Gulf slugs can return nothing in a week when the
job boards carry dozens of in-lane roles. Before calling slugs dead, run
`ats_pool.py --diagnose` (no title filter — a restrictive `--titles` makes live boards look dead)
and a **slug-variant pass**: hyphenated, `-bank`, `-io`, `-ltd`, `-hq`, the product name, the legal
name. Grow `companies.txt` from boards that actually resolved. Include
`ycombinator.com/jobs` (see `sources.md` Tier 3; its apply flow needs a workatastartup.com login,
so those rows are `⛔ YC login — you apply`).

### 3. Sweep — WebSearch for what the boards miss (Tier 2)
Founder programmes and EIR tracks, niche boards, and `site:` passes over boards that block reading.
Query patterns are in `sources.md` §Tier 2.

### 4. Merge, dedupe, and check coverage
One command combines every source, keeps the in-lane rows (the profile's own regexes), collapses
the same job found on several sources into **one row** listing all of them (the employer's own date
and link win), and marks each row **new since the last run** or already seen:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py merge \
        --titles "<criteria §1 seniority>" --domain "<criteria §1 discipline>" \
        --exclude-titles "<criteria §5>" \
        --markets "<Market A>=<city|country regex>;<Market B>=<regex>" \
        --out $SCRATCH/scout-merged.json $SCRATCH/scout-*.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py coverage
```
**`coverage` is a gate.** A market with no in-lane rows from fewer than three sources is a
**coverage failure**, not a thin market: widen before going further — the next source in its
regional pack, a title-synonyms pass, the boards of companies hiring nearby — and run `merge` and
`coverage` again. Only a market that comes back empty across three or more sources may be reported
as thin. Paste the coverage table into the report, and lead the report with one line:
*"Scanned N postings from M sources across K markets — P new since the last run."*

Score the **new** rows. Rows already seen stay in the report's "still open" section with their
earlier score; do not re-read them unless the posting changed.

**Senior markets are thin week to week.** When the 1–7 day window leaves a market short, run a
**30-day repost pass** over the same boards: a role re-posted after a month usually means the
search is still open, and it is fair game. Judge freshness by the ATS's own date
(`first_published`, `publishedAt`, `createdAt`) — a LinkedIn date is the *listing* date, and a
re-listed job looks new.

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
cheaply from title + company + location. Take the **top ~2× the shortlist target** (the fetch
count `learn.py target` printed — ~40 on a fresh day) and `WebFetch` each posting for
what only the full text reveals: comp, work-authorization wording, whether "CTO" means CTO,
team size, funding. Do not fetch all of them — that is the expensive step and most candidates
die on the title alone.

**Knock-out screen every fetched posting** (save the text, then):
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-apply/scripts/knockout.py --jd $SCRATCH/posting-<n>.txt
```
`STOP` → out of the ranking, into an "excluded — knock-out" line with the quoted sentence. `FLAG`
→ keep, and show the flag in the job's Flag line. This is where UK-only, citizenship-gated,
language-gated and below-floor roles leave the list, *before* anyone tailors a CV for them.
**Check every salary or language STOP against its quoted sentence before dropping** — a benefit
line, another listing on an aggregator page, or a negated requirement can still slip through.

What only the full text reveals — read for it on every fetched posting:
- **Multi-city rows.** `ats_pool.py` merges one title across cities into one row (`multi_city`).
  Each city is often its own req with its own band, language and visa questions; read the req for
  the city you score, and when several fit, show the choice rather than taking whichever came first.
- **Remote that is not remote.** "Remote (US)", "remote within the US", or salary bands quoted only
  for US metros mean US residence is required. An EU-tagged posting that asks for US work
  authorisation or quotes USD is a US req with an EU location tag. "Remote anywhere / any time
  zone / work from anywhere" is the wording that means it.
- **Stated minimum qualifications.** Quote any stated minimum the profile does not visibly meet
  (managing managers, an org size, a regulated-industry record) as a FLAG on the row. A gap is first
  an **evidence** question — does the brain or the user hold the fact the CV is missing? — and only a
  true hard knock-out (citizenship, a required language, a licence) drops the role. When the same
  minimum keeps sinking applications, ask the user for the fact once (cv-tailor's evidence note)
  rather than dropping every such role.

### 5b. Applyability check — BEFORE anything reaches the shortlist
**A job the user cannot actually apply to does not belong on the shortlist.** For every candidate that
survives scoring, establish how the application is submitted *before* ranking it:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-apply/scripts/detect_portal.py "<url>" --fetch
```
- `linkedin` → **resolve it first** (ATS board · `site:job-boards.greenhouse.io "<company>"` ·
  the company's own /careers page). Classify the resolved URL, not the LinkedIn mirror.
- `walled` (Workday, Taleo, SuccessFactors, iCIMS, **join.com**, BrassRing, Oracle HCM, Avature,
  Eightfold, Phenom, Cornerstone) → follow criteria `walled:` (§3b). **`surface` (the default):**
  keep it and rank it like any other row, Apply column `⛔ <portal> — you apply`. Claude cannot
  create the account, so the application is a hand-off (job-apply prepares the CV and answers).
  In some markets most senior roles sit behind these portals, and hiding them empties the list.
  **`assist`:** keep and rank it, Apply column `🔐 <portal> — assisted`; job-apply fills it in the
  user's browser and hands over only the account, password, e-mail code and CAPTCHA steps.
  **`drop`:** leave it out and list it in an "excluded — account wall" line.
- `fillable` → keep, and **record the real apply URL in the report** so the apply step does not
  have to rediscover it.
- `unknown` → fetch the page and look for an account wall (*create an account · sign up to apply ·
  register to apply · log in to apply · set a password*). Treat as walled if found.

The report's shortlist table carries an **Apply** column: `✅ direct form (<ats>)` · `⛔ <portal> — you apply` ·
`🔐 <portal> — assisted` · `✉️ email only` · `? unverified`. **A row must not say `?` in a delivered report** — verify it or
leave the job out.

This costs a few fetches per run and saves the user discovering the wall themselves after reading a role
they liked. It is not optional.

### 6. Score and rank
Apply `references/scoring-rubric.md` — six components out of 100 including **shortlist
likelihood** (would a recruiter put *this* person on a call?), hard disqualifiers dropped
outright. Rank, break ties on the work-mode order in `profile/scoring.md`.

**Only jobs that clear the apply floor are shortlisted** (the floor is in `profile/scoring.md`;
the rubric's default is total ≥ 75 and shortlist likelihood ≥ 20/30). **Cut at the shortlist
target** from step 0a, not at a fixed ten. At most one role per company.

**The daily target sets how wide you source, never how low you score.** Below target, widen
the *sweep* — more ATS boards, a Tier-2 drill-down on every strong company, the full geography
and every lane the profile allows. Never lower the apply floor, never add a lane, never relax
an exclusion, never two roles at one company to reach the number. If the list is still short after that, run
step 7 on every strong company *before* delivering, then deliver what cleared and say plainly how
far short it is (`14 of 20 — the day will land at ~7 valid`) and the one sourcing change that would
close it.

**Ledger gate — REQUIRED, on the final list, right before it is written.** Step 4's
`filter-seen` ran on the raw sweep; everything added after it (the drill-down, the saved
ATS pool, a carried-over role from an earlier shortlist) never passed through it, and that is
how a role the user applied to — and was rejected from — came back as #1. So the rows about to
go into the table go through the ledger one last time:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py gate < $SCRATCH/scout-final.json > $SCRATCH/scout-shortlist.json
```
It drops the same posting (matched by the board's job id, so an embed or mirror URL still
matches), the same company + title, and any company applied to in the last 30 days, printing
each drop and its reason to stderr. **A dropped row does not appear in the shortlist at all** —
not as a ❌ or ⛔ row, not "for context". Refill from the next roles above the floor, gate
those too, and put the drops in one "left out — already applied" line with the count and the
earliest eligible date. Never hand-edit the ledger's verdict.

**Rank scarce fit above title fit.** The roles that convert are usually the ones whose #1
requirement is something rare the user has actually done, not the ones whose title sits one rung
up their ladder. When two rows tie, the one that matches the user's rarest proof wins.

Record each shortlisted job's archetype and likelihood in the report; job-apply logs them to the
ledger so `learn.py calibrate` can check the score against what comes back.

### 7. Drill down (required when below the shortlist target)
If a company looks strong — and on every strong company when the shortlist is short — pull its whole board — the best-fitting role is often not the
one that surfaced:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/ats_fetch.py auto <company-slug> --filter "cto|vp|head of|chief|architect"
```

### 8. Finish the report, then record the run

`$REPORT` already exists — you created it in step 1 and have been updating its status line
since. Now write the **full ranked list** into it: date, what was searched, counts per source,
the whole shortlist with scores, reasoning, red flags and apply links, the line
`Target: <valid today>/<daily target> · shortlist <n> of <shortlist target>`, then a short "also seen / near
misses" section. Replace the `## Status` line with the final summary.

Three more sections, every run:
- **Opening line:** *"Scanned N postings from M sources across K markets — P new since the last
  run."* (the counts `merge` printed).
- **`## Coverage`** — the table `scout_state.py coverage` printed, with its verdict per market. A
  market that ended as a coverage failure says what was tried and what will be tried next run.
- **`## Still open (seen before)`** — in-lane roles from earlier runs that are still live, one line
  each with their earlier score, so a good role is not lost because it was first seen yesterday.
  **Not** the hand-offs: a role from an earlier day's board that was handed to the user (a portal,
  an Easy Apply) stays on *that* day's board; never carry it into today's list. When the user says
  they applied, log it (`learn.py log-outcome --status applied`, noting they submitted it).

**The report shows the CURRENT list ONLY.** Never append "Run 2", "Run 3"
sections — a second sweep the same day **replaces** the list, it does not stack onto it. Rewrite
the file, carrying forward only the statuses of jobs already actioned. Permanent history lives in
`outcomes.jsonl`, not in the report.

**The shortlist table MUST have a `Status` column as its second column**, every row starting at
`⬜ not started`, followed by this legend line:

> **Legend:** ✅ applied · 🟡 filled, awaiting submit · 🔐 waiting on you in the portal (account step) ·
> 🟠 ready — you apply (portal or LinkedIn) ·
> ⬜ not started · ⛔ skipped · ❌ disqualified · 🚫 excluded by criteria · 🔵 replied · 🎯 interview

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
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py add-seen < $SCRATCH/scout-new.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py mark-run
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/render_brain.py --quiet     # mirror the dashboard into the brain
```
**Record only after the report is written** — a crashed run should be repeatable.

`render_brain.py` mirrors the report into `<brain>/45-jobs/reports/Shortlist <date>.md` (into the `## Shortlist` section of the dated daily note when `daily.py start` opened it first) — plus
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
- Public endpoints only, keep the built-in rate delays, and no Chrome on a routine run unless
  criteria §3b turns it on (see `sources.md` → *On LinkedIn* and `regional-sources.md`).
- Deduped against `seen.json` — they should not be shown the same job twice. If a genuinely
  better-matching *re-post* appears, say it is a repost.
