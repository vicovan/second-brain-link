---
name: stay-search
description: Find places to stay for each stop of a planned trip on public sites in the user's own browser, in the neighbourhood where that stop's places actually cluster and matched to the user's hotel style, recording each price with the moment it was seen. Use for "find a hotel", "where should I stay", "find stays for the trip", including a stopover night.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, TodoWrite, mcp__claude-in-chrome__*
---

# Stay Search

Per stop in the itinerary — stopovers included, they are stops — **or for a city and dates
with no trip at all** ("hotels in Iași 12–19 Oct").

1. **Where.** The best base is walking distance from that stop's places. Get the cluster:
   `itinerary.py show <trip>` for the stops, and the centre of each stop's POIs from
   `itinerary.json` (average their `lat`/`lng`). Name the neighbourhood from the places'
   addresses. For a stopover, stay near the airport-train line into town.
2. **What.** Read `taste.md` (hotel style, neighbourhood) and `travel-criteria.md` (budget per
   night). No profile → ask the one question that matters (budget), not all of them.
3. **Search** in the browser (ask which browser once per run — see `flight-search` §1), in the
   order `providers.md` gives (default **Google Hotels** for the market and real availability
   across sites, then Booking.com, Agoda, Airbnb for the rate actually sold —
   `references/stay-sources.md`), for the dates, guests from `traveler.md`. A place that shows
   "sold out" or no rooms for the dates is **not** an option.
4. **Record 5–8 as a quote set** — within budget, closest to the cluster, best matching the
   style — each with name, URL, the price as shown (`price_total` or `price_night`, and which),
   currency, `quoted_at` (now), stars, the guest rating and its scale and review count, area,
   coordinates if the page shows the map, free cancellation and breakfast:

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/
python3 $S/quotes.py new stays --id iasi-oct --title "Iași · 12–19 Oct" --city "Iasi" \
    --checkin YYYY-MM-DD --checkout YYYY-MM-DD --guests 2 [--trip <trip_id> --stop s1]
python3 $S/quotes.py add iasi-oct --file options.json
python3 $S/render_brain.py --quiet
```

5. **Present**: in Studio end the reply with `quotes.py fence <id>` — a hotels list the user
   compares and clicks — and add what stands out in a sentence or two (their taste, the
   catch). Read a few recent reviews of the top two for what the user cares about
   (`taste.md`: quiet, breakfast, walkability…) and say what they say, quoted.
6. **The choice** (the card's "Choose", or "h2"): `quotes.py pick <id> h2 [--trip <t> --stop s1]`
   sets the trip's stay; then `itinerary.py plan-days <trip> --stop s1` (routes start from the
   stay) and `render_brain.py --quiet`.

## Rules

- `status` stays `candidate`. Nothing is held or booked in this version; never open a checkout.
- Blocked or CAPTCHA → one line, a pre-filled link (`references/stay-sources.md`), move on.
- A price is total for the stay unless the page says otherwise — write which it is.
