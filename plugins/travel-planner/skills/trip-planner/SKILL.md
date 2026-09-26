---
name: trip-planner
description: Turn a destination and dates into a day-by-day itinerary built from the user's own Second Brain places — saved pins first, loved places next — clustered into areas, ordered into walking routes and drawn on Studio's Map. Use when the user picks a destination, says "plan N days in X", "build the itinerary", "add this place to day 3", or asks to see a trip on the map.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, TodoWrite
---

# Trip Planner

Owns `itinerary.json` — the one object the whole plugin is built on — and the shared scripts
every other skill calls by absolute path:

```
${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/<script>.py
```

This skill makes **no web requests**. Everything it produces comes from the brain.

## Files

| File | What it is |
|---|---|
| `scripts/paths.py` | Where everything lives. Run it to see the brain, the state root and the layer. |
| `scripts/places.py` | The brain's places as full records (coordinates, lists, your rating and review text). |
| `scripts/taste.py` | Category, price band and a love score per place; proposes `taste.md`. |
| `scripts/scout.py` | Where to go, from the brain alone (trip-scout's engine). |
| `scripts/itinerary.py` | Create and edit the itinerary; validates, and rewrites `map.geojson` (and `All Trips.geojson`) on every change. |
| `scripts/quotes.py` | Quote sets — real flight and stay options as read on the sites (price, when, where); Studio shows them as a flights / hotels list. |
| `scripts/suggest.py` | Suggestion sets — places you recommend before (or without) a trip; drawn on the Map from `Suggestions.geojson`. |
| `scripts/interline.py` | Separate-ticket flight combinations and stopover nights (flight-search's engine). |
| `scripts/geo.py` | Distances, clustering, walking routes, great circles. |
| `scripts/render_brain.py` | The travel layer the user reads. Run with `--quiet` after every change. |
| `scripts/learn.py` | The ledger. **Only the orchestrator writes it.** |
| `references/itinerary-schema.md` | Every field of `sbl-itinerary/1` and the three invariants. Read before editing a trip. |
| `references/category-lexicon.md` | The words `taste.py` classifies by. |
| `references/airports.json` | Airports, coordinates and self-transfer connection floors. |
| `<travel layer>/profile/taste.md` | The user's confirmed taste — prefer it over `taste.py`'s guesses. |

## The three invariants

`itinerary.py` enforces them and refuses to save a trip that breaks one. Do not work around it.

1. **A stopover is a stop.** `role: "stopover"` gets nights, a stay, places and a route like
   any other stop.
2. **No price without `quoted_at`.** A price is a snapshot of one page at one moment.
3. **`from_brain` is never claimed.** It is set by `itinerary.py` when the name resolves to a
   place note in the brain — never by you.

## Planning a trip

Pick a short, lowercase trip id: letters, digits, hyphens (`lisbon-spring`).

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/
python3 $S/itinerary.py new --id lisbon-spring --title "Lisbon — spring"
python3 $S/itinerary.py add-stop lisbon-spring --place Lisbon --arrive YYYY-MM-DD --nights 4 \
    --why "7 saved places you never visited · 2 you rated ★4+"
python3 $S/itinerary.py activate lisbon-spring      # the Map opens on it
python3 $S/itinerary.py brain-pois lisbon-spring --stop s1      # your own places, best first
python3 $S/itinerary.py plan-days lisbon-spring                 # areas → days → walking routes
python3 $S/render_brain.py --quiet
python3 $S/itinerary.py show lisbon-spring
```

- `add-stop` finds the city's coordinates from the user's own pins there, else the engine's
  offline gazetteer; pass `--lat/--lng` when neither knows it.
- `brain-pois` pulls places within ~12 km: saved-but-never-visited first, then loved ones,
  never anything rated ★2 or below, never coworking desks or transport hubs.
- `plan-days` gives arrival and departure days half a day, keeps an area on one day, and
  orders each day by walking distance from the stay (once there is one).
- A place the user names that is **not** in the brain goes in with coordinates and an honest
  `why`: `add-poi <trip> --stop s1 --name "…" --lat … --lng … --kind cafe --why "no brain
  signal — web only"`. Find the coordinates from a map page the user or a shopping skill
  opened; never invent them.
- Re-run `plan-days` after adding or removing places. Run `render_brain.py --quiet` after
  every step, not once at the end — the user is watching the tree and the Map.

Tell the user, per stop: how many places came from their brain, and the one or two reasons
that matter most (cite the notes). Then show the map with a `map` fence fitting the trip
(`{"fit":"all"}`), if you are in Studio.

## Editing on request

"Move X to day 3", "drop the museum", "add a day in Sintra": edit through `itinerary.py`
(`add-poi`, `add-stop --role daytrip`, then `plan-days`), never by hand-editing the JSON. If a
change needs something the CLI does not do, edit `itinerary.json` with a single `Edit`, then
run `itinerary.py validate <trip>` and `itinerary.py geojson <trip>` — a hand edit that is not
validated is how an invariant breaks.

## What this skill never does

- Creates a note named like a place, or writes into the places layer. It links.
- Writes outside the travel layer and the ledger.
- Treats a guessed category as the user's taste. `taste.md`, once confirmed, wins.
