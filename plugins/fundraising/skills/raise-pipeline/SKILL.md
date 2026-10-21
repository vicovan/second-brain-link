---
name: raise-pipeline
description: Run the founder's raise end to end — onboard if needed, then the daily raise (new programs and investors found and screened, today's note opened first, applications filed and investor angles drafted within the autonomy level, follow-ups due, threads worth a comment) and the weekly update (KPIs, the optimizer, stale claims re-verified, the Funding Plan rebuilt) — holding whatever gates the founder's setting calls for. Use for "run my raise", "run today's raise", "build my funding plan", "what's due", "record a reply", the daily or weekly fundraising routine, or any fundraising request where the right skill is not obvious.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, Skill, Agent, TodoWrite, mcp__claude-in-chrome__*
---

# Raise Pipeline

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/raise-apply/references/`). Tool:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/memory.py`, scope `fundraising`, tags `targeting,research,planning,apply,outreach`.
1. **First:** `memory.py recall --scope fundraising --tags targeting,research,planning,apply,outreach` — apply it, say in one line which items changed what you do, never re-ask what it answers.
2. **User says a preference, rule or correction** → `observe --source user` at once (`--scope shared` if it holds for every agent).
3. **An outcome lands** (an investor's reply or pass, a program's decision (`ledger.py log-outcome`), a claim the lint rejected) → `observe --source outcome` with the evidence, `--match` the item it strengthens.
4. **Last:** at most 3 inferred lessons → `observe --source agent` (saved and used at once, flagged as inferred — the user can edit or remove them); end with *"Learned: …"*.


The orchestrator. It **owns no logic of its own** — it sequences the other five and holds the gates.
The daily is the Jobs loop over two item kinds — **programs** (accelerators, fellowships, grants,
pitch forms) and **investors** (funds, angels, strategics, syndicates) — in the founder's own words:
*what programs to find new daily, apply on each in Chrome, and what angles to email.*

## The shape of every run — the shared runner (`daily.py`)

`S=${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts`. Eleven steps, every day; the scripts
guarantee the shape, this file the words:

```bash
python3 $S/daily.py start --agent fundraising --routine "Daily raise"     # 0-3: preflight · memory recall · orient (stats, due, counters, goal pace) · OPEN THE DATED NOTE
```

It prints the goal lines with their pace (*investor meetings 3 of 5 · on pace* · *acceptances 0 of 1*),
the `=== LAST REPORT ===` block (pick those up first), what memory says, and the note it opened:
**`46-fundraising/reports/Raise today <date>.md`** — `## Status` first, then *New today · Due ·
Angles today · Threads worth a comment · Needs you · Explored today*. That note is the home Studio
shows beside this chat for the whole run.

| Step | Programs | Investors | Mark it |
|---|---|---|---|
| 4 discover | new doors: the brain first (`_correlations` ties to alumni and partners, `10-people`), then the proven program sources in `profile/sources.md`, then today's explore slice — `python3 $S/daily.py explore --agent fundraising` names it (directories, cohort calendars, public lists the founder pasted) | new targets from thesis / portfolio signals, recent announcements, warm paths through the brain | `daily.py status "found N programs, M investors" --phase discovering` |
| 5 screen + score | `raise-research`: the filter chain (`round.md`, cheapest first) → desk-screen 📋 → verify survivors on their own site ✅ within `max_research_agents` | the same chain, the tier, and **the angle**: which verified claim + recent signal makes this fund the right door this week (`ledger.py set-claim`, `set-tier`; the angle in the record's `angle`) | `--phase screening` |
| 6 the note | `python3 $S/ledger.py table shortlist | python3 $S/daily.py section "New today" --agent fundraising --file -` (why it fits · deadline · access route · apply route); `ledger.py due --days 14` into *Due*; the angles into *Angles today* (angle + draft link) | same note | `--phase shortlisting` |
| 7 act | `raise-apply` per `level:` in the founder's Chrome — find the real form, draft every answer within limits, lint against the facts file, fill, verify the DOM, **submit per level** (supervised: the approval card); never an account, never a credential | `raise-outreach`: one draft per angle (email / intro request / pitch-form note), linted, saved (+ Gmail draft when the tool exists). **Never sent.** `contacted` only when the founder says "I sent it" | `--phase acting` after each |
| 7b secondary | follow-ups due (`raise-outreach` drafts), `raise-engage` threads (≤ `max_per_run`, drafts only) into *Threads worth a comment* | same | — |
| 8 log | `ledger.py` events: `log-app`, `log-draft`, `next`, `log-outcome` — every outcome with the sentence that decided it | same | — |
| 9 render | `render_brain.py --quiet` after every change (status calls render too, debounced) | | `--phase rendering` |
| 10 reflect | the memory block above (≤ 3 inferred lessons) | | `--phase reflecting` |
| 11 handoff | `report.json` → `python3 $S/daily.py close --agent fundraising --report report.json`; paste what it prints LAST in your reply: the chat report (goal counters · done · needs you · due next with dates), then the ```report fence | | — |

Record what an explored source produced: `python3 $S/explore.py record --sources 46-fundraising/profile/sources.md --source "<name>" --found N [--converted N]`.

## The modes

| Asked | Mode |
|---|---|
| the daily routine, "run today's raise", "run my raise" | **daily** — the table above |
| the weekly routine (*Weekly raise update*), "how is it going" | **week** — `python3 $S/daily.py start --agent fundraising --routine "Weekly raise update" --mode week`, then `python3 $S/kpi.py --pipeline 46-fundraising/pipeline.json --events <state root>/events.jsonl --signals origin,kind,tier,channel,angle --md --label Fundraising`, `python3 $S/optimize.py apply --pipeline 46-fundraising/pipeline.json --events <state root>/events.jsonl --profile 46-fundraising/profile --contract ${CLAUDE_PLUGIN_ROOT}/studio.json --level <level> --review-out "46-fundraising/reports/Raise update <date>.md" --label Fundraising` (sources, tiers, angles, channels — applied at `autonomous`, one card at `supervised`; never a cap or a gate), re-verify every stale Tier 1–2 claim (`raise-research`), rebuild **`Funding Plan.md`** (`raise-plan`, the previous one archived), and complete the update note: *since last week* (`ledger.py since <date>`) · *deadlines 30 d* (`ledger.py due --days 30`) · *what I changed and why*. Close with `daily.py close`. |
| "Build my funding plan" | research (rescreen → fan-out → verify → tier) → `raise-plan` → offer this week's actions |
| "Screen this list" / "Apply to <program>" / "Draft this week's emails" / "Threads to comment on" / "I sent it" / "I posted" / "What's due?" / "Record a reply" | the rows below, unchanged |

```
supervised:  profile → research → plan → [FOUNDER PICKS] → apply: [APPROVE ANSWERS] → [SUBMIT]
                                                         → outreach: drafts (the founder sends)
autonomous:  profile → research → plan → pick by tier+deadline → apply → lint → verify → submit
                                                              → outreach: drafts (the founder sends)
```

| Stage | Skill |
|---|---|
| Profile | `raise-onboarding` |
| Import, screen, verify, tier | `raise-research` |
| The Funding Plan | `raise-plan` |
| Program forms | `raise-apply` |
| Emails, intros, follow-ups | `raise-outreach` |
| Public threads worth a comment | `raise-engage` |
| Memory | `scripts/ledger.py` (in raise-research) |

Invoke them with the Skill tool (`fundraising:<skill>`). Never re-implement one here.

## Step 0 — orient, in one line each

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/paths.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/founder_profile.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py stats
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py due --days 14
```

- No profile → `raise-onboarding`, then continue.
- Say the level in one line ("Running supervised — I'll stop before each submit").
- Read `<state root>/lessons.md` if it exists; it holds what outcomes taught.

## The modes — pick from what the founder asked

| Asked | Do |
|---|---|
| "Build my funding plan" / "run my raise" | research (rescreen → state fan-out → verify stale + untiered survivors → tier) → plan → offer this week's actions |
| "Screen this list" | research ingest + rescreen; report survivors and removals by filter; offer verification |
| "Apply to <program>" / "apply to this week's programs" | `raise-apply` per program; several = fan out drafting, fill one at a time |
| "Draft this week's emails" | `raise-outreach` for Tier 2 records in `verified`/`queued` without a draft |
| "Prepare this week's packages" | `raise-outreach` package flow for Tier 2 targets without a PASS package: brief → fit → draft → lint → investor review → buttons; report the Ready-to-send count |
| "I sent the <Name> email" (the ✓ button) | the founder's own confirmation → `ledger.py sent <key>` at once, re-render, one line back — the only way a record becomes `contacted` |
| "Threads to comment on" / a pasted post / the engagement routine | `raise-engage`: unposted drafts first, then find → score → draft ≤ `max_per_run` comments; nothing is posted |
| "I posted the comment on t-…" (the ✓ button) | the founder's own confirmation → `threads.py posted <id>`, re-render, one line back |
| "What's due?" | `ledger.py due`; draft the due follow-ups (`raise-outreach`); flag deadlines ≤ 7 days |
| "Record a reply" / pasted email | the outcome flow below |
| weekly run (the nudge) | the **week** mode above |

## The gates — how many is the founder's setting, never your call

- `supervised`: **pick** (which targets this run — "none today" is a normal answer), **approve
  answers** (per application), **submit** (per application). Email drafts need no gate — the founder's
  own send is the gate.
- `autonomous`: none of those three. `max_submits_per_run` caps submissions; on reaching it, stop,
  finish the records, list what is prepared but unsent.
- **Both levels**: which browser (once per run; not connected → `references/browser-setup.md`, the
  founder's steps to install, sign in and reconnect the extension), and a missing fact (ask when supervised; skip that
  item with a reason when autonomous).

## Recording an outcome

1. Classify the reply the founder pasted or described: `replied` (a response, no decision) ·
   `meeting` · `passed` (a fund's no) · `rejected` (a program's no) · `accepted` · `term_sheet` ·
   `no_reply` (the founder says the window passed). Quote the sentence that decided it.
2. Match it to a record (`ledger.py list`), ask if two could match — never guess a key.
3. `ledger.py log-outcome <key> <result> --note "<their words, if a reason was given>"`.
4. A meeting → prep from the target note (claims, partner, why this one) and `stories.md`.
5. A rejection from a program → note the next cohort if the page shows one; re-queueing later needs
   `--different` naming what changed (a cofounder, an entity, a pilot, real usage). Same profile,
   same door, same answer.
6. `ledger.py add-lesson "<one line>"` when an outcome teaches something reusable
   ("cold forms to <kind> never answered — prefer warm intros there").
7. `render_brain.py --quiet`; if the ledger changed materially, rebuild the plan.

## The report — always this order, and twice

1. The goal counters: meetings, acceptances (and replies) — from `ledger.py count`, never typed.
2. What needs the founder: gates waiting, facts missing, decisions from §3 of the plan, drafts to send, "I sent it" confirmations.
3. What was done: applications filed, drafts written, targets verified, what the filter removed.
4. What is due next, with dates.

Then the ```report fence `daily.py close` prints (done with evidence · not done · next · needs you ·
news). Keep the dashboard, the note and the plan true throughout — `render_brain.py --quiet` after
every status change (the plan's §0 ledger table is refreshed between its markers by the render).
