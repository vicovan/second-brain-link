---
name: flight-search
description: Shop flights for a planned trip on public sites in the user's own browser — metasearch for the market's shape, then the carriers directly for the fare actually sold — and combine separate tickets through virtual interlining, turning a long connection into a stopover night in a city worth seeing, with the self-transfer risk spelled out. Use for "find flights", "how do I get there", "is there a cheaper way with a stopover", once a trip exists.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, TodoWrite, mcp__claude-in-chrome__*
---

# Flight Search

Works with a trip (`itinerary.py show <trip>`) **or without one** — "what does Dubai → Iași
cost on 12 October?" is a real question. `traveler.md` gives home airports and citizenships;
without it, ask for the origin — never guess one.

## 1. The browser

`list_connected_browsers` → **ask which browser, once per run** (the extension requires the
user to choose even when one is connected) → `select_browser` → `tabs_context_mcp`.
No browser tools at all → say which (absent, not connected, errored) and stop this skill;
the plan is still complete without it.

## 2. The market's shape — metasearch

Search the trip's origin → first stop and last stop → origin on the dates in the itinerary,
on the sites in `providers.md` (default order: Google Flights, Skyscanner, Kayak — see
`references/flight-sources.md`). Read the results page; note the cheapest direct, the
cheapest one-stop, and **which carriers and hubs appear**.

## 3. Candidate hubs for separate tickets

From what the market showed, plus **cities the user has saved places in** that lie roughly
on the way (`places.py` — the brain picks the layover), list 2–4 hubs. For each hub, search
origin → hub and hub → destination as **separate one-way trips**, favouring a next-day second
flight when the user's criteria welcome stopover nights.

## 4. The fare actually sold — carrier sites

For each promising segment, open the **carrier's own site** and read the real fare for that
flight. Metasearch prices are routinely stale.

## 5. Record what you saw — a quote set (the list the user sees)

Every search you present becomes a **quote set**: the options exactly as the page showed
them, each with its price, currency, `quoted_at` (now, to the minute) and the URL you read
it on. Studio draws it as a flights list — times, airline, duration, stops, price, when seen —
and `render_brain.py` writes the same list as a note.

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/
python3 $S/quotes.py new flights --id dxb-ias-oct12 --title "Dubai → Iași · 12 Oct" \
    --from DXB --to IAS --date YYYY-MM-DD [--return YYYY-MM-DD] [--adults 1] [--trip <trip_id>]
python3 $S/quotes.py add dxb-ias-oct12 --file options.json     # a list; the shape is in quotes.py
python3 $S/render_brain.py --quiet
```

Read from the results: each segment's carrier code and name, flight number, airports (IATA),
local departure and arrival times (with the date — overnight flights shift it), the site's
**total duration** (`total_min`; never compute it across time zones), bags, and the price as
shown. 5–8 options: the cheapest, the fastest, the cheapest direct, and the best-timed ones.
`quotes.py` refuses an option without `url`/`quoted_at`/`currency`, and marks Cheapest /
Fastest / Cheapest direct itself.

**In Studio, end the reply with the set's fence** (`quotes.py fence <id>` prints it) — the
list renders as cards the user can compare and click; do not also retype the list as prose.
Say in a sentence or two what stands out (the trade-off, the catch).

### Separate tickets

Write the separate one-way fares to the ledger, one file per search, then combine:

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/
# <state root>/trips/<trip_id>/quotes/flights-<YYYYMMDDTHHMM>.json — a JSON list of fares:
# {"id","provider","price","currency","quoted_at","source_url","segments":[{"carrier","number","from","to","dep","arr","cabin"}]}
python3 $S/interline.py --fares <that file> --from DXB --to TYO --top 5
```

Every fare carries `quoted_at` (now, ISO, to the minute) and the URL it was read on. The
paths come from `paths.py` — the ledger is under the state root, never inside the plugin.

## 6. Present, then write the choice

A plain option the user picks from a quote set (they click "Choose" on the card, or say
"f2"): `quotes.py pick <id> f2 [--trip <trip_id>]` — with a trip it becomes the trip's leg.
For a separate-ticket journey from `interline.py`:

Show the top three journeys: price, total time, tickets, and — **verbatim** — each
self-transfer's risk line from `interline.py`. A connection below the airport's self-transfer
floor never appears: `interline.py` refuses it. Ask which one (`AskUserQuestion`), then:

```bash
python3 $S/interline.py --fares <file> --from DXB --to TYO --pick <n> --trip <trip_id>
python3 $S/itinerary.py plan-days <trip_id>      # a new stopover stop gets its own day plan
python3 $S/render_brain.py --quiet
```

A stopover night becomes a stop: offer to fill it with the user's own places there
(`itinerary.py brain-pois <trip> --stop <id>`) and a stay (`stay-search`).

## Rules

- **Blocked, CAPTCHA, login wall:** stop on that site, one line saying which, hand over a
  pre-filled search link (formats in `references/flight-sources.md`). Never solve a CAPTCHA,
  never log in, never retry more than once.
- **Never open a checkout.** Nothing is booked in this version.
- **Visa:** never tell the user a transit visa is not needed. `interline.py` flags every
  landside transfer into a country not in their `visa_ok`.
