---
name: ground-search
description: Plan how to move on the ground between a trip's stops — rail where it beats driving, a hire car where it does not, ferries and buses — reading public operator and rental sites in the user's own browser and recording each price with when it was seen, including the one-way, cross-border and driver-age traps. Use for "how do I get from X to Y", "should I rent a car", "trains between the stops", or day trips.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, TodoWrite, mcp__claude-in-chrome__*
---

# Ground Search

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/flight-search/references/`). Tool:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/memory.py`, scope `travel-planner`, tags `ground`.
1. **First:** `memory.py recall --scope travel-planner --tags ground` — apply it, say in one line which items changed what you do, never re-ask what it answers.
2. **User says a preference, rule or correction** → `observe --source user` at once (`--scope shared` if it holds for every agent).
3. **An outcome lands** (a rating (`learn.py rate`), a booking or cancellation, a site that blocked you, a price that moved) → `observe --source outcome` with the evidence, `--match` the item it strengthens.
4. **Last:** at most 3 inferred lessons → `observe --source agent` (saved and used at once, flagged as inferred — the user can edit or remove them); end with *"Learned: …"*.


For each pair of consecutive stops not joined by a flight, and each `daytrip` stop:

1. **Rail first** when a direct or one-change train exists under ~5 hours — it lands in the
   centre. Otherwise a car, a bus or a ferry. Read `references/ground-traps.md` before
   recommending a car.
2. Search the operator (national rail site) or the rental sites in `providers.md` (default
   Sixt, Europcar, Hertz) in the user's browser — ask which browser once per run (not connected →
   `references/browser-setup.md`).
3. Record each option as a leg: write a JSON file and add it.

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/
# leg.json: {"from":"Lisbon","to":"Porto","mode":"train","note":"direct, 3h",
#            "tickets":[{"id":"g1","provider":"national rail","price":36,"currency":"EUR",
#                        "quoted_at":"<ISO now>","source_url":"https://…"}]}
python3 $S/itinerary.py add-leg <trip> --json leg.json
python3 $S/render_brain.py --quiet
```

`from`/`to` are stop place names (or IATA codes); the map draws the leg between them.

## Rules

- Every price has `quoted_at` and a URL, or it is not recorded.
- Name the trap that applies to a car hire (one-way fee, border, age) in the leg's `note`.
- Blocked → one line and a link. Never open a checkout.
