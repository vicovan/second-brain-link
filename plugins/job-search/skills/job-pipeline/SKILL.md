---
name: job-pipeline
description: Run the whole job hunt end to end — "run my job pipeline", "run the job automation", "find and apply to jobs", or run it against the user's Second Brain. Finds today's roles, scores them, tailors a CV for each, fills the applications and logs the outcomes. Works from any working directory, including a Second Brain vault, and fires on the daily prompt.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, Skill, Agent, TodoWrite, mcp__claude-in-chrome__*
---

# Job Pipeline

The daily loop, start to finish. This skill **owns no logic of its own** — it sequences the other
four and holds whatever gates the user's autonomy setting calls for.

```
supervised:  lessons -> scout -> [USER PICKS] -> tailor CV -> [USER APPROVES] -> fill -> [USER SUBMITS] -> log
autonomous:  lessons -> scout -> pick by score -> tailor CV -> fill -> verify in DOM -> submit -> log
```

| Stage | Skill that does the work |
|---|---|
| Find + score | `job-scout` |
| Write the CV | `cv-tailor` |
| Fill + submit | `job-apply` |
| Remember | `job-scout/scripts/learn.py` |

**Never re-implement any of them.** If something is wrong with scoring, fix the scout. If a CV is
wrong, fix the tailor. This file only orchestrates.


## Asking the user something

This skill runs on two surfaces and they ask differently. **Check which one you are on
before a gate**, and never let a gate silently do nothing:

- **A terminal / interactive session, or Second Brain Studio:** use `AskUserQuestion`.
  Studio shows the options as buttons and your call waits for the answer, just as in a
  terminal.
- **Any other non-interactive stream, where `AskUserQuestion` is unavailable or fails:**
  emit ONE fenced `gate` block and end your turn. The surface renders it as buttons and
  the answer arrives as the next message.

````
```gate
{"id":"submit","question":"Submit this application to <company>?","options":["Submit","Cancel"]}
```
````

Either way the rule is the same: the gate is a real person deciding. Never assume an answer,
never treat silence as consent, and never chain past a gate.

## How this runs by default

These are the plugin's defaults. They are deliberate, and each one is here because the
alternative was tried and was worse. A user who wants it differently says so once and it goes
into `profile/search-criteria.md`; until then, do not re-ask.

**Run it end to end without stopping.** Do not pause between jobs for confirmation, do not report
progress and wait, do not ask whether to continue. Sweep, score, tailor every CV, fill every form,
fix every broken field, and keep going. **How much stops you is the user's `level:` setting**, read
from §0 of `profile/application-answers.md` — three gates at `supervised`, none at `autonomous`.
A pipeline that asks after every step is slower than doing it by hand.

**Read the level once, at the start of the run, and say which one you are in in one line.**
Missing or unreadable file → `supervised`. Never infer it from the user's phrasing. At
`autonomous`, honour `max-submits-per-run` (default 10): on reaching it, stop submitting, finish
the records, and list what is prepared but unsent.

**But never trust a subagent's read-back.** Expect a material fraction of delegated fills to be
wrong while reporting success. Failure shapes to watch for: a form whose dropdowns *display*
answers and have registered none; a form lost entirely to a navigation; a missing required city
field; and — the one that matters most — a work-authorisation dropdown that auto-selects a visa
the applicant does not hold, which is a false statement made in their name. **Re-verify every form
yourself in the DOM** (`field-policy.md` §6d) before you gate or submit, and expect to repair some
of them by hand. This matters more at `autonomous`, not less: verification is the only check left.

**Keep the report true the whole way through.** `<state root>/reports/<date>.md` is what they watch while
the run is happening — linked titles, a `CV` column, a `Status` emoji and a `Status detail`
sentence, all updated the moment anything changes. They have had to ask for this twice; do not make it
a third time.

**Surface Chrome domain permissions immediately.** Claude cannot grant them. Name the domain and the
job waiting on it (`field-policy.md` §6e). If a run covers several ATS domains, ask for all of them
in one go at the start rather than interrupting once per job — the fills themselves still happen
one at a time (Phase B).

## The gates — how many depends on the level, and it is never your call

Read `level:` from §0 of `profile/application-answers.md` before anything else. Missing or
unreadable → `supervised`.

**At `supervised`, three gates, never collapsed:**

1. **Which job** (or none today) — or "all of them", which is what they usually say
2. **Is the CV right** — skip this when they have already approved the batch
3. **Submit** — the only one that never goes away at this level

They do **not** want a field-by-field review. Three lines, then Submit or Skip. Never chain
past a gate on an assumption, never treat silence as a yes. "None today" is a completely
normal answer — most days it is the right one.

**At `autonomous`, none of the three.** You pick by score, approve your own CV, and click
submit. What replaces the gate is the record and the verification, and both get stricter
rather than looser: every required field read back from the DOM before the click, and
`answers.json` + `ANSWERS.md` complete before it, because those are what the user reads
instead of approving in advance. An application that is sent but not recorded is the one
outcome there is no way back from.

**Two questions survive both levels**, because neither is an approval:

- **Which browser** — the Chrome extension's own contract requires the user to choose and
  forbids you picking. Ask once per run and reuse the connection.
- **A missing FACT** — a required factual field the profile cannot answer truthfully
  (`field-policy.md` §3a). At `supervised` ask; at `autonomous` **skip that job with a
  one-line reason**. Never guess it, at either level.

Free text is not in either list: composed answers are written every time, never left blank,
never handed back (`field-policy.md` §3b).

## Workflow


### 0a. Work out which surface you are on — REQUIRED, before anything else

This pipeline is triggered from two places and must behave identically in both: **Claude Code** in
a working folder, and **Second Brain Studio**, whose agent panel calls Claude Code with the user's
selected brain as the working directory.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/paths.py        # prints every path this run will use
```

Read the output before doing anything. It tells you the surface, the ledger, and where the profile
and the rendered layer belong.

**The surface rule — one location per run, never both:**

```
cwd inside a brain   ->  <brain>/45-jobs        and nothing else
otherwise            ->  <working folder>/45-jobs    and nothing else
```

That is the user's explicit choice, and it has a cost worth stating plainly when it bites: **a run
from one surface leaves the other surface holding the previous run.** `Job Dashboard.md` records
which surface wrote it and when, so a stale copy identifies itself. `render_brain.py --import-to`
is the only thing that crosses, and only when the user asks for it.

**If the working directory is not the project folder, its `CLAUDE.md` does not auto-load.** When
one exists, read it before searching — it carries the local conventions this file cannot know.

**Check whether the apply half can run at all.** Stage 6 needs the Chrome MCP tools
(`mcp__claude-in-chrome__*`). If they are not available on this surface:

- Run stages 1–5 fully — sweep, score, render the layer, build the tailored CVs.
- Then **stop and say so plainly**: *"Scout and CVs are done; the dashboard is at
  `45-jobs/Job Dashboard.md`. Applying needs Claude Code with Chrome."*
- Do **not** log anything as applied, and do **not** imply the run finished.

### 0b. Load the profile, then the brain

**The profile first** — it is what this run is for. Read order: this surface's
`45-jobs/profile/` → the other surface's, used with a one-line notice and an offer to copy it
here → **run `job-search:job-onboarding` (the **Skill** tool)**. Never guess a compensation floor, a location or a target title.

**Then the brain, if one is reachable** — best-effort enrichment, never a dependency:

```bash
BRAIN=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/find_brain.py) || BRAIN=""   # empty -> skip, run on
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/find_brain.py --who                  # exit 0 theirs, 2 someone else's
```

`find_brain.py` identifies a brain by `00-me/identity.md` → `title:` matched against the profile's
`owner:`, never by folder name — vaults move and folders get renamed. A vault can hold several
people's brains: if the one selected is **not** the user's, say so in one line and skip this step
rather than substituting theirs. Never read across brains, never merge two.

**Read exactly these, and nothing else:**

| File | What you take from it |
|---|---|
| `40-career/preferences.md` | Saved location / title / industry / job-type preferences |
| `40-career/saved-jobs.md` | Companies the user bookmarked themselves — the strongest sourcing signal in a vault |
| `40-career/applications.md` | **Frontmatter only** — counts, top roles, top companies |
| `90-synthesis/target-companies.md` | Where they have actually aimed, ranked. The clearest read on what they want |
| `95-goals/job-search.md` | The warm-intro map: which companies they know someone at |

Deliberately **not** read: `90-synthesis/positioning-gaps.md` is ad-network interest tags and says
nothing about a career; `85-places` is restaurants; `_quarantine/` is never read at all.

**The boundary.** The brain **tunes sourcing and scoring only.**

- `profile/search-criteria.md` and `profile/scoring.md` **win every conflict.** A vault's
  `preferences.md` is usually a stale copy of LinkedIn job-alert settings and will contradict the
  real criteria; follow the criteria and say in one line that you did.
- **`profile/profile.md` remains the only source of facts for a CV.** Nothing from a vault — not a
  title, not a number, not a company — may appear on a CV or in an application answer.
- **Warm intros are for the user, not for the form.** *"You know four people at <company>"* belongs in
  the chat summary. A named contact never goes into a rendered note, a cover letter or a form field.
  Never surface anyone's email, phone or private message body.

**What to do with it:** add bookmarked companies to the Tier-0 drill list and append confirmed
boards to `companies.txt`; nudge the company score by a point or two for a bookmark or a warm
intro — never enough to lift a role past a hard exclusion or the comp floor; drop nothing on the
strength of a vault alone. Then say in one line what the brain changed, or that it changed nothing,
or that none was reachable.

### 1. Load the loop
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py show
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py pending
```
If anything has been pending more than ~14 days, mention it once — it is probably a silent
rejection worth recording as `--result none` so the statistics stay honest.

### 2. Find today's jobs
Invoke the **Skill** tool with `job-search:job-scout` and let it run its own workflow. Do not duplicate its sweep here.

### 3. Choose which jobs
Present the top 10 in the scout's format.

- **`supervised` — Gate 1, they pick.** *"Apply to one of these today?"* → *"#N — <company>,
  <role>"* for the top 3 · *"A different number"* · *"None today"*. On **None today**: log
  nothing, say one line, stop. Do not push.
- **`autonomous`** — take the top N by score, where N is what the user asked for (default 1)
  capped by `max-submits-per-run`, and say which ones you are taking in one line. Skip
  anything the scout marked walled, excluded or disqualified.

### 4. Phase A — build every application, in parallel

For each chosen job, dispatch one **`Agent`** subagent, **at most four at a time**. Each does
job-apply steps 1–4 for its own job and nothing else: classify the portal, create the folder
via `learn.py log-outcome --status filled`, invoke `job-search:cv-tailor` with that folder as
the output directory, and write `answers.json`.

**The ledger has exactly one writer: you.** A subagent writes only inside its own
`<state root>/applications/<YYYY-MM-DD>/<job_key>/`. It must never call `learn.py`, never
touch `outcomes.jsonl`, `seen.json` or the report, and never run `render_brain.py`. Two
parallel appends to a JSONL produce a line nothing can parse, and a line nothing can parse is
an application that silently disappears from the user's vault. Say this in every brief.

*(The one exception is the folder-creating `log-outcome` above: if you would rather keep even
that centralised, make the folders yourself before dispatching and tell each agent the path.
What must never happen is two agents logging at once.)*

As each agent returns, **you** run `render_brain.py --quiet` so its folder and CV appear in the
user's tree one by one — they are watching that pane, and four applications that all appear at
the end look like nothing happened for four minutes.

### 5. The CV
- **`supervised` — Gate 2, they approve.** Name the PDF and its folder so the surface can link
  it. Two lines: the contact set chosen and why, the title mirrored, the keywords led with.
  Gate: **"Use this CV?"** → *Use it* · *Change something* · *Stop*.
- **`autonomous`** — check it yourself against `cv-tailor`'s own ATS criteria (2 pages,
  keywords present, no replacement characters) and say the filename in one line. A CV that
  fails those checks is rebuilt, not sent.

### 6. Phase B — fill and submit, one at a time

Connect and select the browser **once** in this session, then for each job in score order:
open a tab, invoke **`job-search:job-apply`** from its step 5, verify every required field in
the DOM, submit (`autonomous`) or gate (`supervised`), close the tab, log
`--status applied`, `render_brain.py --quiet`, next.

**Sequential on purpose.** The extension drives one browser; interleaving DOM work across tabs
risks typing one job's answers into another's form or clicking the wrong submit — the single
mistake that cannot be undone, to save a few minutes. Parallelism belongs in Phase A, where
the time actually goes.

Do not second-guess `job-apply`'s policy file.

### 7. Close the loop
`job-apply` logs the outcome. Add anything the whole run taught, then consolidate:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py add-lesson "<observation>" --tag sourcing|scoring|cv|apply
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py consolidate
```

### 7b. Keep the day's report current — REQUIRED

The report is the user's **live dashboard**, not an end-of-run artefact. Every role
title links to its apply URL, every row has a `CV` column linking to the exact PDF sent, and the
`Status` cell changes the moment the state does — `⬜` → `🟡` → `✅`. Never batch the updates.

**Mirror it into the brain in the same breath** — the dashboard should be openable from inside
the brain and stay current there in parallel, not only in the state root. One command,
immediately after every write to the report:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/render_brain.py --quiet
```
It re-renders the whole `45-jobs/` layer for **this surface only** — the dashboard, every
application note, the shortlists — from the ledger. It is idempotent, so calling it after each
status change costs nothing when nothing moved.

It is cheap (it skips the write when nothing changed), one-way (state root → brain; the copy says so
on its own first line), and silent when no brain is reachable. **The canonical report is still
`<state root>/reports/<date>.md`** — edit that one, never the mirror.
Before reporting back, confirm `<state root>/reports/<date>.md` reflects reality: the
`Status` column updated for every job touched (✅ applied · 🟡 filled, awaiting submit ·
⛔ skipped · ❌ disqualified), and a row in the "Application log" table for each. The user reads this
file as their pipeline; stale status is a bug.

### 8. Report — lead with the KPI
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py kpi
```
Open with **successful applications**, then shortlist conversion and wasted shortlist. Then the
usual six lines. The user tracks this system by the number of applications that actually land — a run
that shortlisted ten and submitted two is a failed run even if the ten looked good.

**Improve it every day.** Each run, name one specific thing that cost a submission (an account
wall that was not detected, a form trap, a requirement missed at shortlist time) and fix it in the
skill — not just log it.

### 8b. The original report format
Six lines maximum: how many new jobs, how many cleared the bar, what they applied to, what is still
pending, and anything they need to do themselves (a LinkedIn hand-off, a TBD to answer, a result to record).

## Running more often

The daily nudge is once per day. To run again the same day, they just asks — or:
```bash
rm "<state root>/last-run.txt"   # re-arms today's prompt
```
For a genuinely higher frequency, edit the LaunchAgent
your scheduler (see `docs/scheduling.md` for launchd and cron recipes). Note the scout's search window shrinks to what is actually new,
so a second run the same day mostly returns nothing — which is the correct answer, not a bug.

## Degraded surfaces

| Surface | What runs |
|---|---|
| **Claude Code in a plain working folder** | Everything. Output lands in `<working folder>/45-jobs`. |
| **Claude Code from the Second Brain vault** (Second Brain Studio's agent panel) | Everything, once step 0a has read the project `CLAUDE.md`. Same state root, same skills — Studio loads the plugin for the session, so they are available from any working directory. If that surface has no Chrome tools, it is scout + CVs and stop. |
| **claude.ai / mobile** | Stages 1–5 approximated only. `cv-tailor` works fully; the scout runs without `seen.json`; nothing is logged and nothing is submitted. |

The test is not the app name, it is whether `mcp__claude-in-chrome__*` is available and
`<state root>/` is writable. Check both at step 0a rather than assuming.

### Triggering it from Second Brain Studio
Any of these phrasings in the Studio agent panel should land here, because the skill descriptions
are what Claude matches on: *"run my job pipeline"*, *"run the job automation in the context of my
brain"*, *"find and apply to jobs today"*. Studio loads the plugin for the session, which that panel
already lists — no per-app installation, nothing to copy into the vault. If it ever fails to find
them, the fix is how the plugin is loaded (`--plugin-dir`), not a second copy of the skill.
