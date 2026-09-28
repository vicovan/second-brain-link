---
name: trip-scout
description: Answer "where should I go, and when?" from the user's own Second Brain alone — cities where they saved places and never went, places they rated highly, people they know there, the months they usually travel — with every idea citing the notes behind it. Makes no web requests. Use for "where should I go next", "give me trip ideas", "somewhere I've been meaning to go", or before planning when no destination is chosen.
allowed-tools: Read, Glob, Grep, Bash, TodoWrite
---

# Trip Scout

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/flight-search/references/`). Tool:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/memory.py`, scope `travel-planner`, tags `destinations,taste`.
1. **First:** `memory.py recall --scope travel-planner --tags destinations,taste` — apply it, say in one line which items changed what you do, never re-ask what it answers.
2. **User says a preference, rule or correction** → `observe --source user` at once (`--scope shared` if it holds for every agent).
3. **An outcome lands** (a rating (`learn.py rate`), a booking or cancellation, a site that blocked you, a price that moved) → `observe --source outcome` with the evidence, `--match` the item it strengthens.
4. **Last:** at most 3 inferred lessons → `observe --source agent` (saved and used at once, flagged as inferred — the user can edit or remove them); end with *"Learned: …"*.


Zero web requests. The scout's whole value is that it uses what no travel site has: the
user's own history.

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/
python3 $S/scout.py --top 5            # ranked ideas; also writes <state root>/ideas.json
python3 $S/render_brain.py --quiet     # → "Trip Ideas" note in the travel layer
```

`scout.py` ranks cities by:

- **saved-but-never-visited** places there (the strongest signal — a trip already planned
  and never noticed)
- places **rated ★4+** there (a return worth making)
- **people** in the brain whose notes carry coordinates within ~40 km
- minus cities that are **worn** (many visits, nothing left saved) and the **home** city

It reports the months the user has historically travelled, from dated visits, photos and
check-ins.

Writing `ideas.json` also puts every idea on Studio's Map as a trip-idea ring
(`Suggestions.geojson`). In Studio, end the message with ```` ```map {"fit":"ideas"}``` ````
so the Map zooms to them.

## Then

1. Read `travel-criteria.md` if it exists and drop ideas that break it (a climate they avoid,
   a flight longer than their limit — judge that from the distance to their home airport).
2. Present **three** ideas. For each: the city, the one-line reason, and two or three note
   links that prove it (`[[Alfama Tile Café]]`). Mention the months they usually travel.
3. Ask which to plan (`AskUserQuestion`), then hand to `trip-planner` with the choice.

Never pad the list with places the brain gives no reason for. If the brain has fewer than
three cities with a signal, say so and offer to plan the one it does have, or to take a
destination from the user.
