# travel-planner — plan a trip from the places already in your brain

> **Developer preview.** Planning works from your brain alone. Shopping reads public sites
> through your own browser and some of them will block it. **Nothing is booked.**

Your Second Brain already knows where you have been, where you said you wanted to go, and
which of it you loved: the places layer holds your saved Google Maps pins and lists, your own
star ratings and review text, visited places, photo spots, check-ins and event venues — each
with real coordinates. This plugin turns that into trips.

- **Trip ideas from your own history** — cities where you saved places and never went, places
  you rated highly, people you know there. Every idea cites the notes behind it.
- **One itinerary object** (`itinerary.json`) — stops, days, places, walking routes, legs — drawn
  on Second Brain Studio's **Map** as the agent builds it.
- **Your places first.** Suggestions from your brain are marked and link to your notes;
  anything from the web says "no brain signal — web only".
- **Virtual interlining with stopover nights.** Two separate tickets with a long layover
  become a night in that city — with the self-transfer risk spelled out, drawn dashed on the
  map, and any connection below a safe floor refused outright.
- **Every price is a snapshot**, stamped with when and where it was seen.

## Surfaces

| Surface | What you get |
|---|---|
| Second Brain Studio | The **Travel Agent**: chat on the right, the trip on the Map in the centre, notes updating live |
| Claude Code | `/travel-planner:trip`, `/plan`, `/places`, `/onboard`, `/report` |
| Codex | Planning, trip ideas, itinerary and links — no browser, so no shopping |

## Install

```bash
python3 packaging/build_plugin.py travel-planner --provider claude --install   # ~/.claude/skills/travel-planner
python3 packaging/build_plugin.py travel-planner --provider openai --install   # ~/.agents/skills/travel-planner
```

One install serves the CLI, the desktop Studio and the browser Studio. Run it from inside a
brain (or with `SECOND_BRAIN_HOME` set) — it writes to that brain's `47-travel/` layer, and
keeps its ledger hidden in `.plugins/travel-planner/`.

## Rules it keeps

Nothing personal ships in the plugin; your data never lives in the plugin folder; no layer
folder is hardcoded outside `paths.py`; stdlib-only Python. See `docs/safety.md` and
`docs/providers.md`.

MIT — see `LICENSE`.

## The daily loop (agent operating model)

*Today near me* (every day 08:10, off until you turn it on) is "a traveller in your own city": where
you are (the active trip's stop, else your profile's `home_city`, else what you said — **never the
device**) → recall → **open `47-travel/reports/Today in <City> <date>.md` first** → the brain half
(`today.py picks`: saved-but-never-visited places first, then the kinds you love, not picked in 30
days, one per slot of the balanced mix: coffee · meal · activity · event · wildcard new neighbourhood ·
social) → the web half (`today-scout`: events and openings this week, each with `seen_at`, marked web
only) → a dated shortlist, one section per slot (the Map, `Today.geojson`, one click away) → nothing booked; you say *"I went to #2"*
(`learn.py went|loved|not-for-me|save`) and the picks funnel counts it toward **Try my city**.
*This weekend* (Fri 16:00) is the weekend edition; *Weekly trip check* (Mon 09:30) re-reads stale
quotes on upcoming trips and runs `kpi.py` → `optimize.py` on the picks (proposals only; nothing
changes a gate). Two funnels on Studio's Runtime — trips (idea → planned → shopped → booked → done;
`render_brain.py --migrate-layout` rewrites the old ids draft / past once) and picks — and a
six-machine Floor. Standard layout: `Travel Dashboard.md` · `Travel KPI.md` · `Travel Lessons.md` ·
`pipeline.json` · `profile/` (+ `home_city`, `radius_km`, `mix`, `stages.json`, `sources.md`) ·
`reports/` · `trips/<id>/` · `picks/<date>/` · the Map files. Contract: `studio.json` (`sbl-agent/1`);
reference `engine/references/agent-contract.md`.
