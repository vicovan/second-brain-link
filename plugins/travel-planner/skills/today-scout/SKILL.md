---
name: today-scout
description: A traveller in your own city — every day, what is new to try near where the user is (the active trip's stop, else their home city, else what they said, never the device) — one coffee, one lunch or dinner, one activity, one event, one new neighbourhood, a social option — their own saved and loved places first, then the web for what is on this week with when each page was seen, as a dated shortlist (the Map one click away). Use for "what should I do today", "anything new near me", "what's on this week", the daily routine, or the weekend edition.
allowed-tools: Read, Glob, Grep, Bash, WebSearch, WebFetch, TodoWrite
---

# Today Scout — "what should I do today?"

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/flight-search/references/`). Tool:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/memory.py`, scope `travel-planner`, tags `taste,today,places`.
1. **First:** `memory.py recall --scope travel-planner --tags taste,today,places` — apply it; never re-ask what it answers.
2. **The user says a preference, rule or correction** → `observe --source user` at once.
3. **An outcome lands** (went · loved · not for me — `learn.py` records it and feeds memory) → it is already saved; `--match` the item it strengthens when you add context.
4. **Last:** at most 3 inferred lessons → `observe --source agent` (flagged as inferred). End with *"Learned: …"*.

`S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts`. The brain half is deterministic
(`today.py`); the web half is yours, and every web fact carries when it was seen.

## 1. Where — never the device

```bash
python3 $S/today.py here            # the active trip's stop covering today → else profile home_city → else what the user said today
python3 $S/today.py here --set "Porto"   # the user said "I'm in Porto": stamped for today only
```

No "here" → ask once (*"Where are you today?"*), set it, go on. Never read a location from the
machine, a browser or a photo.

## 2. The brain half — new to the user

```bash
python3 $S/today.py picks --radius-km <profile radius_km, default 6> --mix <profile mix>
```

It expires yesterday's unsaved suggestions, then picks from the places layer: saved-but-never-
visited first, then the kinds the user loves (`taste.py`), not picked in the last 30 days, within
the radius, nearest among equals — one per slot of the balanced mix (**coffee · meal · activity ·
event · wildcard new neighbourhood** + **social** when the profile wants it). Every pick cites
its note. It prints the slots the brain could not fill — those are the web half.

## 3. The web half — with `seen_at`, marked web only

For each empty slot (and always for **events this week**): search public pages — the venue's own
site, the city's event listings, a market's page — in the user's own browser or with `WebSearch`.
Add what fits the taste (`taste.md`) and the profile (budget, pace, companions):

```bash
python3 $S/today.py add --name "<place>" --kind cafe|restaurant|museum|venue|market|… --lat … --lng … \
    --slot coffee|meal|activity|event|wildcard|social --why "<why, in their taste's words>" \
    --url <the page> --seen-at <ISO now> [--price "<as shown>" --quoted-at <ISO now>]
```

Rules: an opening time or an event only with `seen_at` and its page; a price only with
`quoted_at`; nothing within 30 days of a previous pick; a reservation is a link, never made;
**explore** — 20 % of the web budget goes to a neighbourhood or a kind the user has no history
with (the wildcard), and `python3 $S/explore.py pick --sources 47-travel/profile/sources.md` names
the sources to try today.

## 4. The note and the Map

```bash
python3 $S/today.py note            # the per-slot sections of the dated note, between markers (R2)
python3 $S/render_brain.py --quiet
```

**`Today near me <date>`** is a structured shortlist like every other agent's daily note: one
section per slot — *Coffee · Food · Activity · Event · Social · Wildcard* — each pick with its why
(cited), open today (`seen_at`), price (`quoted_at`), distance, and the three feedback words
(*save · I went · not for me*); then *This week's events*, *Trip day* (on a trip: the itinerary's day
first — the picks fill the gaps near its route), *Yesterday* (went / not for me), *Needs you*,
*Explored today*. The Map is the alternate view: `Today.geojson` carries the numbered pins
(Open ▾ → Map in Studio); end the reply with a `map` fence only when the user asked for the map.

## 5. Feedback — the only "act"

Nothing is booked or bought. The user says *"I went to #2"*, *"save #4"*, *"loved it"*, *"not for
me"* (in chat, from the card, or from the note):

```bash
python3 $S/learn.py went|loved|not-for-me|save --pick p-<date>-<n> [--note "…"]
python3 $S/render_brain.py --quiet
```

`went` is what the goal *Try my city* counts; `loved` / `not for me` feed the taste through memory.

## Weekend edition

On Friday (*This weekend*): the same steps for Saturday and Sunday — a day trip from the
saved-but-never-visited places within reach, the weekend's events and markets, a longer walk in a
neighbourhood not yet visited — written to `Today near me weekend <date>` (`daily.py start --mode weekend`).
