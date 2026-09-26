# `sbl-itinerary/1` — the itinerary object

One per trip at `<travel layer>/trips/<trip_id>/itinerary.json`, edited through
`itinerary.py`. It is the plan (rendered to notes), the Map's data (projected to
`map.geojson` beside it) and the worksheet the shopping skills fill in.

```jsonc
{
  "schema": "sbl-itinerary/1",
  "trip_id": "japan-autumn", "title": "Japan — autumn",
  "status": "draft | shopped | booked | past",
  "window": {"earliest": "YYYY-MM-DD", "latest": "YYYY-MM-DD", "nights": 5, "flex_days": 0},
  "currency": "EUR",
  "budget": {"total": 4000, "flights": 1200, "stay": 1500, "ground": 400, "food": 600, "activities": 300},
  "travelers": [{"id": "me", "label": "me"}],

  "stops": [{
    "id": "s1", "place": "Tokyo", "country": "JP", "lat": 35.68, "lng": 139.76,
    "role": "base | stopover | daytrip",
    "arrive": "YYYY-MM-DD", "depart": "YYYY-MM-DD", "nights": 4,
    "why": "7 saved places, 1 rated ★5, never visited",
    "stay": {"name": "…", "url": "…", "price": 120, "currency": "EUR",
             "quoted_at": "YYYY-MM-DDTHH:MM:SS", "status": "candidate | held | booked",
             "lat": 35.69, "lng": 139.70, "source": "booking site"},
    "days": [{"date": "YYYY-MM-DD", "route": "r1", "items": ["p1", "p7"]}]
  }],

  "legs": [{
    "id": "l2", "from": "ICN", "to": "HND", "mode": "flight | train | car | ferry | bus",
    "segments": [{"id": "f2-s1", "carrier": "KE", "number": "KE719", "from": "ICN", "to": "HND",
                  "dep": "YYYY-MM-DDTHH:MM", "arr": "YYYY-MM-DDTHH:MM", "cabin": "Y", "ticket": "f2"}],
    "tickets": [{"id": "f2", "provider": "carrier site", "covers": ["f2-s1"], "price": 150,
                 "currency": "EUR", "quoted_at": "…", "source_url": "https://…"}],
    "self_transfer": true, "connection_minutes": 1020, "stopover_stop": "s2",
    "risk": {"level": "medium | high", "why": "separate tickets · bags not through-checked · …"}
  }],

  "pois": [{"id": "p1", "stop": "s1", "name": "Kanda Pour-Over Bar", "lat": 35.69, "lng": 139.77,
            "kind": "cafe | restaurant | bar | market | museum | tour | viewpoint | shop | trail | sight | venue | other",
            "from_brain": true, "brain_note": "<places layer>/Kanda Pour-Over Bar.md",
            "why": "on your 'Favourite coffee' list · you rated it ★5",
            "rating": 5, "price_band": "$$",
            "booking": {"url": "…", "status": "link"}}],

  "routes": [{"id": "r1", "stop": "s1", "date": "YYYY-MM-DD",
              "ordered_pois": ["p1", "p7"], "polyline": [[35.69, 139.77]], "walk_minutes": 46}]
}
```

## Invariants (`itinerary.py validate` checks every one)

1. **A stopover is a stop.** `role: "stopover"` needs at least one night and has `days`, a
   `stay` and places like any other stop. A shorter connection stays on its leg as
   `connection_minutes`.
2. **No price without `quoted_at`.** Any object with a non-zero `price` must carry
   `quoted_at`. Rendered notes print the time beside the number.
3. **`from_brain` only when `brain_note` is a real note** in this brain. Set by
   `itinerary.py` from the places layer; never set it by hand.

Also checked: unique ids across stops/legs/pois/routes, every POI on an existing stop with
coordinates, `nights` matching `arrive`..`depart`, a `stopover_stop` pointing at a stopover,
and a `risk.why` on every self-transfer leg.

## `map.geojson` (`sbl-map/1`) — what the Studio Map draws

A GeoJSON FeatureCollection (coordinates `[lng, lat]`), rewritten on every save:

| `properties.feature` | Geometry | Carries |
|---|---|---|
| `stop` | Point | `id`, `label`, `role`, `nights`, `order` |
| `stay` | Point | `stop`, `label`, `status` |
| `poi` | Point | `id`, `label`, `stop`, `kind`, `from_brain`, `day`, `seq`, `note_id`, `why` |
| `leg` | LineString (great circle for flights) | `id`, `mode`, `self_transfer`, `label`, `risk` |
| `route` | LineString | `id`, `stop`, `day`, `walk_minutes` |

`note_id` is the place note's id (its path without `.md`) — Studio opens it only if it is a
note it already knows. `Current Trip.geojson` at the layer root is a copy of the active
trip's map, rewritten by `render_brain.py`.
