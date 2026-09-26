---
name: travel-planner
description: Plan a trip from the places already in your Second Brain — trip ideas from cities where you saved places and never went, a day-by-day itinerary built from your own saved and loved places with walking routes, and pre-filled links for flights, stays and tables. Use for "where should I go next", "plan N days in X", "give me trip ideas", or "what should I do in X". Makes no bookings; this packaging has no browser.
---

# travel-planner — trips from your own places (OpenAI)

> This is the **OpenAI/Codex packaging** of the Second Brain Link `travel-planner` plugin.
> The scripts are byte-identical to the Claude packaging; only this manifest and the layout
> differ. Workflows are in `references/`, code in `scripts/`.

## What differs from the Claude packaging — read this first

Codex has no browser-automation tools, so **this packaging does not shop.** It plans, reasons
over the brain, builds the itinerary and its map data, and hands over **pre-filled search
links** for flights, stays, ground transport and tables. **There is no booking gate to remove,
because there is no browser** — and in any packaging, nothing is booked in this version.

`interline.py` still works on fares the user pastes in (a JSON list — see
`references/flight-search.md`), and still refuses unsafe self-transfers.

## Workflows

Read the one you need, in full, before acting.

| Workflow | Read | When |
|---|---|---|
| Onboarding | `references/travel-onboarding.md` | No `47-travel/profile/` yet, or preferences changed |
| Trip ideas | `references/trip-scout.md` | "where should I go" |
| Itinerary | `references/trip-planner.md` | A destination is chosen; editing a trip |
| End to end | `references/trip-pipeline.md` | "plan me a trip" |
| Flights / stays / ground / food | `references/flight-search.md`, `references/stay-search.md`, `references/ground-search.md`, `references/taste-scout.md` | For the links and the traps — skip their browser steps |

Supporting: `references/itinerary-schema.md`, `references/category-lexicon.md`,
`references/airports.json`, the profile templates, `references/flight-sources.md`,
`references/stay-sources.md`, `references/ground-traps.md`, `references/dining-sources.md`.

## Scripts

```bash
python3 scripts/paths.py                        # where everything lives
python3 scripts/places.py                       # your places by city
python3 scripts/scout.py --top 5                # trip ideas, cited
python3 scripts/itinerary.py new --id <id> --title "…"
python3 scripts/itinerary.py add-stop <id> --place <City> --arrive YYYY-MM-DD --nights 4
python3 scripts/itinerary.py brain-pois <id> --stop s1
python3 scripts/itinerary.py plan-days <id>
python3 scripts/render_brain.py --quiet         # the 47-travel layer
```

## Where your data lives

Inside a brain: notes in `<brain>/47-travel/`, the ledger hidden in
`<brain>/.plugins/travel-planner/`. Outside one: `~/.second-brain/travel-planner/`. Never in
this skill's folder.

## Non-negotiables

- Every suggestion's `why` cites a note in the brain, or says "no brain signal — web only".
- No price without the moment it was seen.
- Never create a note named like a place; never write outside the travel layer.
- Never state that a visa is not needed.
