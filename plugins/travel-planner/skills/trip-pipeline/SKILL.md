---
name: trip-pipeline
description: Run the Travel Agent's loops from the user's Second Brain — the daily "Today near me" (what to try near where they are, from their own places first, on the Map), the weekend edition, the weekly trip check, and a whole trip end to end (ideas from their places, the itinerary on the Map, flights with stopover nights, stays, ground and food on public sites) — holding the gates and the single ledger. Use for "what should I do today", "plan me a trip", "plan my next holiday", the daily or weekly travel routine, or anything that spans more than one travel skill.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, Skill, Agent, TodoWrite, mcp__claude-in-chrome__*
---

# Trip Pipeline

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/flight-search/references/`). Tool:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/memory.py`, scope `travel-planner`, tags `destinations,itinerary,flights,stays,ground,food,taste`.
1. **First:** `memory.py recall --scope travel-planner --tags destinations,itinerary,flights,stays,ground,food,taste` — apply it, say in one line which items changed what you do, never re-ask what it answers.
2. **User says a preference, rule or correction** → `observe --source user` at once (`--scope shared` if it holds for every agent).
3. **An outcome lands** (a rating (`learn.py rate`), a booking or cancellation, a site that blocked you, a price that moved) → `observe --source outcome` with the evidence, `--match` the item it strengthens.
4. **Last:** at most 3 inferred lessons → `observe --source agent` (saved and used at once, flagged as inferred — the user can edit or remove them); end with *"Learned: …"*.


The whole trip, start to finish — and the daily. This skill **owns no logic of its own** — it
sequences the others and holds the gates. Two loops, two funnels: **trips** (idea → planned →
shopped → booked → done) and **picks** (suggested → saved → went → loved / not for me / expired).

## The modes

| Asked | Mode |
|---|---|
| the daily routine (*Today near me*), "what should I do today", "anything new near me" | **today** — below |
| the Friday routine (*This weekend*), "what should I do this weekend" | **weekend** — `today-scout`'s weekend edition, `--mode weekend` |
| the Monday routine (*Weekly trip check*) | **recheck** — below |
| "plan me a trip", "where should I go", "find flights" … | the **trip** loop (the rest of this file) |

### today — the shared runner (`daily.py`)

`S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts`:

```bash
python3 $S/today.py here        # where today is built for - the trip's stop, home_city, or what they said; never the device
python3 $S/daily.py start --agent travel-planner --routine "Today near me"   # 0-3: preflight · recall · orient (here, current trip, went this week, goal pace) · OPEN THE DATED NOTE
```

The note is **`47-travel/reports/Today near me <date>.md`** — a structured shortlist like the other
agents' daily notes (`## Status` first; one section per slot *Coffee · Food · Activity · Event ·
Social · Wildcard*, then *This week's events · Trip day · Yesterday · Needs you · Explored today*);
the Map (`Today.geojson`) is the alternate view, one click away. Then `today-scout`
(the Skill tool) does steps 4–6: the brain half (`today.py picks`), the web half with `seen_at`
(`today.py add`), `today.py note` fills the slot sections; the pins land in `Today.geojson` for the Map. Mark progress with `daily.py status "…"
--phase discovering|shortlisting`. Step 7 (act) is **nothing** — no booking, no buying; the only
feedback is the user's *went / save / loved / not for me* (`learn.py`). Steps 8–11: render
(`render_brain.py --quiet`), reflect (the memory block), and
`python3 $S/daily.py close --agent travel-planner --report report.json` — paste the chat report
(places tried · today's picks · needs you) and the ```report fence last. Then `today.py mark-run`.

### recheck — the weekly trip check

`python3 $S/daily.py start --agent travel-planner --routine "Weekly trip check" --mode week` →
for each upcoming trip (`itinerary.py count upcoming`): quotes older than a week (`quotes.py`),
what still needs the user (a self-transfer leg, "I booked it"), then the picks funnel's week:
`python3 $S/kpi.py --pipeline 47-travel/pipeline.json --signals kind,slot,source --md --label Travel`
and `python3 $S/optimize.py apply --pipeline 47-travel/pipeline.json --profile 47-travel/profile
--contract ${CLAUDE_PLUGIN_ROOT}/studio.json --level research --review-out "47-travel/reports/Trip
check <date>.md" --label Travel` (the kinds and sources the user actually went to — proposals only;
nothing here changes a gate). Close with `daily.py close`.

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
line verbatim before they choose). Plus the browser choice, once per run (not connected →
`references/browser-setup.md`: the user's steps to install, sign in and reconnect the extension). Ask with
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
