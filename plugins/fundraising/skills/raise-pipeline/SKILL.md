---
name: raise-pipeline
description: Run the founder's raise end to end — onboard if needed, research and verify targets, write the Funding Plan, apply to the week's programs and draft the week's investor emails, then track replies, follow-ups and deadlines — holding whatever gates the founder's autonomy setting calls for. Use for "run my raise", "build my funding plan", "what's due", "record a reply", the weekly fundraising run, or any fundraising request where the right skill is not obvious.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, Skill, Agent, TodoWrite, mcp__claude-in-chrome__*
---

# Raise Pipeline

The orchestrator. It **owns no logic of its own** — it sequences the other five and holds the gates.

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
| "What's due?" | `ledger.py due`; draft the due follow-ups (`raise-outreach`); flag deadlines ≤ 7 days |
| "Record a reply" / pasted email | the outcome flow below |
| weekly run (the nudge) | due → re-verify stale dated claims on Tier 1–2 → rebuild the plan → report |

## The gates — how many is the founder's setting, never your call

- `supervised`: **pick** (which targets this run — "none today" is a normal answer), **approve
  answers** (per application), **submit** (per application). Email drafts need no gate — the founder's
  own send is the gate.
- `autonomous`: none of those three. `max_submits_per_run` caps submissions; on reaching it, stop,
  finish the records, list what is prepared but unsent.
- **Both levels**: which browser (once per run), and a missing fact (ask when supervised; skip that
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

## The report — always this order

1. The number that matters: replies, meetings, acceptances since the last run.
2. What needs the founder: gates waiting, facts missing, decisions from §3 of the plan, drafts to send.
3. What was done: applications filed, drafts written, targets verified, what the filter removed.
4. What is due next, with dates.

Keep the dashboard and the plan true throughout — `render_brain.py --quiet` after every status change.
