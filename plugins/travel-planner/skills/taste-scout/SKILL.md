---
name: taste-scout
description: Find the cafés, restaurants, bars, activities and tours that fit the user's own taste — the kinds of places they rated highly in their Second Brain — near each day's route of a planned trip, keeping their own saved places first and marking anything with no brain signal as web only. Use for "where should I eat", "what should we do in X", "find me coffee like the places I love", or to fill a day.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, TodoWrite, WebSearch, mcp__claude-in-chrome__*
---

# Taste Scout

The skill that makes it *their* trip rather than a listicle.

## 1. What they love — from the brain, not from you

Read `taste.md` (confirmed taste wins). Without it, derive it on the spot:

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/
python3 $S/taste.py --json | head -c 20000    # category + love per place
```

Take the categories with the highest love (e.g. `coffee`, `tapas`, `viewpoint`) and the ones
rated low (never suggest those). Quote their own words from reviews when they explain *why*
("single-origin, tiny counter, no laptops").

## 2. Their own places first

Every place already in the brain near the stop is a better suggestion than anything on the
web: `itinerary.py brain-pois <trip> --stop <id>` adds them with their `why`.

## 3. Then the web, for the gaps

For each day with room (fewer than the pace in `travel-criteria.md`), search near that day's
route — Google Maps and Tripadvisor for food, GetYourGuide and Viator for tours
(`references/dining-sources.md`), in the user's browser (ask which once per run), or
`WebSearch` when no browser is available. Match on the loved categories and their own words.

Add each pick with coordinates read from the page and an honest reason:

```bash
python3 $S/itinerary.py add-poi <trip> --stop s1 --name "…" --lat … --lng … --kind cafe \
    --rating 4.6 --price-band '$$' --booking-url "https://…" \
    --why "no brain signal — web only · third-wave, single-origin, like the ★5 places you rated"
python3 $S/itinerary.py plan-days <trip> --stop s1
python3 $S/render_brain.py --quiet
```

The `why` of a web pick **starts with "no brain signal — web only"** and then says which of
their tastes it matches. The rendered notes group "from your own brain" and "web only"
separately; never blur the two.

## Best-reviewed, read against their taste — Google Maps

For "the best X in <place>", search **Google Maps** in the user's browser ("specialty coffee
in Iași"), and do not stop at the star average:

1. Take the candidates with a strong rating **on enough reviews** (4.5 on 12 reviews is
   noise; say how many a rating rests on).
2. Open each promising place and **read its reviews** — the newest and the most relevant,
   ten or so, plus the low ones. Look for what *this* user cares about: their own review
   words and loved categories (`taste.py`, `taste.md`) — e.g. "single origin", "quiet to
   work", "no laptops", "great pastries" — and for their dislikes.
3. Judge the match: `high` when reviewers describe what they love, `low` when the praise is
   for things they do not care about or the complaints hit their dislikes.
4. Record it with the evidence in the reviewers' own words — short quotes, never paraphrase
   dressed as a quote:

```bash
python3 $S/suggest.py add <set> --name "Fika" --lat … --lng … --kind cafe --url "<maps url>" \
    --rating 4.7 --reviews 1203 --match high \
    --evidence "pour-over from a rotating single origin" --evidence "quiet in the mornings" \
    --why "no brain signal — web only · reviewers describe exactly the ★5 places you saved"
```

Never copy a reviewer's name or photo, and never quote more than a sentence.

## No trip yet? A suggestion set — so it is still on the Map

"Where should I get coffee in Iași?" does not need an itinerary, but the answer still goes on
the Map and into a note. Record it as a **suggestion set** instead of only writing prose:

```bash
python3 $S/suggest.py new --id iasi-coffee --title "Specialty coffee in Iași" --near "Iasi" --country RO
python3 $S/suggest.py add iasi-coffee --name "Foundry Cafe 64"        # a place in the brain: linked
python3 $S/suggest.py add iasi-coffee --name "Fika" --lat 47.1702 --lng 27.5756 --kind cafe \
    --url "https://maps.google.com/…" --rating 4.7 \
    --why "no brain signal — web only · bright, specialty, like the cafés you saved"
python3 $S/render_brain.py --quiet
```

- Read coordinates **from the page** — a Google Maps place URL carries `@lat,lng`. Never
  estimate them. `suggest.py` refuses a pick more than 60 km from the set's centre; when it
  does, re-read the page, do not nudge the numbers.
- `--near` resolves the centre from the brain's places there, else the offline gazetteer.
  If neither knows the city, take the centre from the city's own Google Maps page — never
  from memory: a wrong centre makes the radius check refuse the right picks.
- No coordinates to be had (e.g. WebSearch only)? Add the pick without them — it is listed
  in the note as "not on the map", which is honest.
- New set per question; `suggest.py activate <id>` brings an older one back to the Map.
- When the user then plans a trip there, `suggest.py to-trip <set> <trip> --stop s1` moves
  the picks in as POIs.
- In Studio, end the message with the set's fence — `suggest.py fence <set>` prints
  ```` ```places {"set":"<id>"}``` ```` — which renders the picks as cards (rating, reviews,
  the evidence, "Show on map"), and ```` ```map {"fit":"suggestions"}``` ```` to zoom the Map.

## Rules

- Never recreate a place that is already a note — if the name matches a place in the brain,
  `add-poi` without coordinates links it.
- A table reservation is a link (`--booking-url`), never a booking.
- Opening hours and closures change: say "check before going" for anything time-critical.
