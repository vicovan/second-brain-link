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
