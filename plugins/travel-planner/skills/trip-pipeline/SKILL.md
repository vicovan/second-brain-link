---
name: trip-pipeline
description: Run a whole trip end to end from the user's Second Brain — onboard if needed, suggest where to go from their own places, build the itinerary on the Map, then shop flights (with stopover nights), stays, ground transport and food on public sites — holding the approval gates and the single ledger. Use for "plan me a trip", "plan my next holiday", "take me somewhere I've been meaning to go", or anything that spans more than one travel skill.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, Skill, Agent, TodoWrite, mcp__claude-in-chrome__*
---

# Trip Pipeline

The whole trip, start to finish. This skill **owns no logic of its own** — it sequences the
others and holds the gates.

```
lessons → [profile?] → scout → [USER PICKS] → plan + map → flights → [USER PICKS] →
stays → ground → taste → render → report                          (no booking in this version)
```

| Stage | Skill | Web? |
|---|---|---|
| Profile | `travel-onboarding` | no |
| Where + when | `trip-scout` | no |
| Itinerary + map | `trip-planner` | no |
| Flights + stopovers | `flight-search` | browser |
| Stays | `stay-search` | browser |
| Ground | `ground-search` | browser |
| Food + activities | `taste-scout` | browser / search |

**Never re-implement any of them.** Wrong scoring → fix the scout. Wrong day plan → fix the
planner. This file only orchestrates.

## Start of every run

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/
python3 $S/paths.py                 # brain, state root, travel layer
python3 $S/itinerary.py list        # existing trips (* = current)
```

Read `<state root>/lessons.md` if it exists, `travel-criteria.md` and `taste.md` if they
exist, and `level:` from §0 of `booking-answers.md` (missing → `research`).

- **No profile** → planning still works (scout and planner need only the places layer);
  offer `travel-onboarding` before any shopping, because shopping needs home airports and
  citizenships.
- **The user named a destination** → skip the scout.
- **A trip is current and the request is about it** ("find flights", "add a day") → go
  straight to that stage.

## Gates

Two decisions are always the user's, at every level: **which trip** (from the scout's ideas)
and **which flight journey** (because a self-transfer moves risk onto them — show the risk
line verbatim before they choose). Plus the browser choice, once per run. Ask with
`AskUserQuestion`; in a non-interactive stream without it, emit one fenced `gate` block and
end the turn.

Everything else — which of their places go on which day, three stay candidates per stop —
you do without asking, and they correct afterwards.

**`level:`** — `research` is the only level with any effect in this version: every run ends
at links. `supervised` and `autonomous` will add booking later; until then treat them as
`research` and say so once if the user has set one. Never infer a level from phrasing —
"just book it" is enthusiasm, not a setting.

## Order of work, and keeping the user's view moving

1. Plan first, shop second. Everything before shopping makes no web requests of its own and
   is the part worth doing even if every site blocks.
2. After each stage: `render_brain.py --quiet`. The user watches the Map and the notes.
3. In Studio, end a stage's message with a `map` fence to show what changed:
   `{"fit": "s2", "highlight": ["p4"]}` (see the Studio grounding).
4. Any places you recommend outside a trip go through `suggest.py` so they are on the Map,
   and trip ideas are pins too once `scout.py` has run.

## Parallel work — one ledger writer

Research may fan out: one subagent per stop (at most four at a time) for stays or food.
A subagent:

- reads the brain and the web, and returns candidates **as text** to you;
- never runs `itinerary.py`, `render_brain.py` or `learn.py`, and never writes into the travel
  layer or `outcomes.jsonl`.

**You** apply their results through `itinerary.py`, one at a time. Two parallel writes to the
itinerary or the JSONL ledger lose one of them silently. Browser work is never parallel: one
browser, one tab, one site at a time.

## Remember

```bash
python3 $S/learn.py log --trip <id> --kind planned      # after the itinerary exists
python3 $S/learn.py log --trip <id> --kind shopped      # after flights/stays are chosen
python3 $S/learn.py add-lesson "…" --tag pace           # when the user corrects something durable
```

After a trip (the user says how it went): `learn.py rate --trip <id> --stars N --note "…"`,
and turn anything durable ("the stopover night was the best part") into a lesson.

## The report

Three to six lines: where, why *for them* (cite two notes), the days, the cheapest honest
flight option with its risk, the stays, and what needs them next. Say what failed (a blocked
site) in one line. Point at the trip note and the Map.
