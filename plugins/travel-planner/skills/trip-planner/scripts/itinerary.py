#!/usr/bin/env python3
"""
itinerary.py - the one object. Load, edit, validate, and project `itinerary.json`.

`<travel layer>/trips/<trip_id>/itinerary.json` (schema "sbl-itinerary/1") is at once the
plan the user reads (rendered to Markdown by render_brain.py), the Map canvas's data source
(projected to `map.geojson` beside it), and the worksheet the shopping skills fill in. Edit
it through this script, not by hand, so the three invariants hold:

  1. A stopover is a real stop. `role: "stopover"` gets nights, days, POIs, a route and a stay
     like any other stop - no special-casing anywhere downstream.
  2. No price without `quoted_at`. Every price is a snapshot: "EUR 410, seen at this time, at
     this URL" - never "the price".
  3. `from_brain` is never inferred. It is true only when `brain_note` resolves to a file in
     the brain.

Every command that changes the trip re-validates it and rewrites `map.geojson`, so a Studio
Map watching the trip redraws mid-run.

    itinerary.py new --id <trip_id> --title "Lisbon - spring" --earliest YYYY-MM-DD --latest YYYY-MM-DD
    itinerary.py add-stop <trip_id> --place Lisbon [--country PT] [--role base|stopover|daytrip]
                          --arrive YYYY-MM-DD --nights 4 [--lat .. --lng ..] [--why "..."]
    itinerary.py add-poi <trip_id> --stop s1 --name "Alfama Tile Café"     (resolved in the brain)
    itinerary.py add-poi <trip_id> --stop s1 --name "X" --lat .. --lng .. --kind cafe --why "web only"
    itinerary.py brain-pois <trip_id> --stop s1 [--radius-km 12] [--max 16]
    itinerary.py plan-days <trip_id> [--stop s1] [--per-day 4]
    itinerary.py set-stay <trip_id> --stop s1 --name "..." [--url ..] [--price 120 --quoted-at <iso>]
    itinerary.py add-leg <trip_id> --json leg.json          (usually written by interline.py)
    itinerary.py validate <trip_id>
    itinerary.py geojson <trip_id>                          (rewrites map.geojson)
    itinerary.py activate <trip_id>                         (the trip the Map opens on)
    itinerary.py show <trip_id>                             (a text summary)
    itinerary.py list
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
from paths import (trip_dir, trips_dir, state_root, surface_root, reference,  # noqa: E402
                   render_dir, TRIP_ID_RE)

SCHEMA = "sbl-itinerary/1"
MAP_SCHEMA = "sbl-map/1"
ROLES = ("base", "stopover", "daytrip")
STATUSES = ("draft", "shopped", "booked", "past")
STAY_STATUSES = ("candidate", "held", "booked")
MODES = ("flight", "train", "car", "ferry", "bus")
POI_KINDS = ("cafe", "restaurant", "bar", "museum", "tour", "viewpoint", "shop", "trail",
             "sight", "market", "venue", "other")

# category (taste.py) -> the POI kind the map colours by
_KIND_OF = {"coffee": "cafe", "tea": "cafe", "bakery": "cafe", "ramen": "restaurant",
            "sushi": "restaurant", "tapas": "restaurant", "seafood": "restaurant",
            "fine-dining": "restaurant", "pizza": "restaurant", "restaurant": "restaurant",
            "hotel-breakfast": "restaurant", "market": "market", "wine-bar": "bar",
            "cocktail-bar": "bar", "bar": "bar", "museum": "museum", "music": "venue",
            "viewpoint": "viewpoint", "landmark": "sight", "garden": "sight", "beach": "sight",
            "trail": "trail", "bookshop": "shop", "design-shop": "shop", "market-shop": "shop",
            "event-venue": "venue"}


class ItineraryError(ValueError):
    pass


# ---------------------------------------------------------------- io
def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _d(s):
    return datetime.date.fromisoformat(str(s)[:10])


def path_of(trip_id, dest=None):
    return trip_dir(trip_id, dest) / "itinerary.json"


def load(trip_id, dest=None):
    p = path_of(trip_id, dest)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ItineraryError(f"no trip {trip_id!r} at {p}")


def _atomic_write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def save(it, dest=None, brain=None, strict=True):
    """Validate, write itinerary.json, and re-project map.geojson beside it."""
    errs = validate(it, brain)
    if errs and strict:
        raise ItineraryError("itinerary invalid:\n  - " + "\n  - ".join(errs))
    it["updated"] = now_iso()
    d = trip_dir(it["trip_id"], dest)
    _atomic_write(d / "itinerary.json", json.dumps(it, ensure_ascii=False, indent=1) + "\n")
    _atomic_write(d / "map.geojson", json.dumps(to_geojson(it), ensure_ascii=False) + "\n")
    project_all(dest)
    return d


# ---------------------------------------------------------------- invariants
def _walk_prices(obj, where="trip"):
    """Yield (where, dict) for every dict carrying a non-empty price."""
    if isinstance(obj, dict):
        if obj.get("price") not in (None, "", 0):
            yield where, obj
        for k, v in obj.items():
            yield from _walk_prices(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_prices(v, f"{where}[{i}]")


def validate(it, brain=None):
    """Every rule broken, as readable sentences. Empty list = valid."""
    errs = []
    brain = pathlib.Path(brain) if brain else surface_root()
    if it.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA!r}")
    if not TRIP_ID_RE.match(str(it.get("trip_id") or "")):
        errs.append("trip_id must be lowercase letters, digits and hyphens")
    if it.get("status") not in STATUSES:
        errs.append(f"status must be one of {STATUSES}")
    ids = {}
    for coll in ("stops", "legs", "pois", "routes"):
        for x in it.get(coll) or []:
            i = x.get("id")
            if not i:
                errs.append(f"{coll}: an entry has no id")
            elif i in ids:
                errs.append(f"duplicate id {i!r} in {coll} and {ids[i]}")
            else:
                ids[i] = coll
    stops = {s["id"]: s for s in it.get("stops") or [] if s.get("id")}
    for s in stops.values():
        if s.get("role") not in ROLES:
            errs.append(f"stop {s['id']}: role must be one of {ROLES}")
        if not geo.has_coords(s):
            errs.append(f"stop {s['id']} ({s.get('place')}): needs lat/lng")
        # invariant 1: a stopover is a stop - it has a night and the same shape as a base
        if s.get("role") == "stopover" and int(s.get("nights") or 0) < 1:
            errs.append(f"stop {s['id']}: a stopover is a real stop - it needs at least one night "
                        "(a shorter layover stays a connection on its leg)")
        for k in ("days",):
            if not isinstance(s.get(k), list):
                errs.append(f"stop {s['id']}: `{k}` must be a list")
        if s.get("arrive") and s.get("depart"):
            try:
                if (_d(s["depart"]) - _d(s["arrive"])).days != int(s.get("nights") or 0):
                    errs.append(f"stop {s['id']}: nights does not match arrive..depart")
            except ValueError:
                errs.append(f"stop {s['id']}: arrive/depart must be YYYY-MM-DD")
        st = s.get("stay") or {}
        if st and st.get("status") not in STAY_STATUSES:
            errs.append(f"stop {s['id']}: stay.status must be one of {STAY_STATUSES}")
    for p in it.get("pois") or []:
        if p.get("stop") not in stops:
            errs.append(f"poi {p.get('id')}: stop {p.get('stop')!r} does not exist")
        if not geo.has_coords(p):
            errs.append(f"poi {p.get('id')} ({p.get('name')}): needs lat/lng")
        # invariant 3: from_brain only when the note really exists
        if p.get("from_brain"):
            bn = p.get("brain_note") or ""
            if not bn or ".." in bn.split("/") or not (brain / bn).is_file():
                errs.append(f"poi {p.get('id')} ({p.get('name')}): from_brain is true but "
                            f"brain_note {bn!r} is not a note in this brain")
    for s in stops.values():
        for day in s.get("days") or []:
            for pid in day.get("items") or []:
                if ids.get(pid) != "pois":
                    errs.append(f"stop {s['id']} {day.get('date')}: item {pid!r} is not a poi")
    for leg in it.get("legs") or []:
        if leg.get("mode") not in MODES:
            errs.append(f"leg {leg.get('id')}: mode must be one of {MODES}")
        so = leg.get("stopover_stop")
        if so and (so not in stops or stops[so].get("role") != "stopover"):
            errs.append(f"leg {leg.get('id')}: stopover_stop {so!r} must be a stop with role stopover")
        if leg.get("self_transfer") and not (leg.get("risk") or {}).get("why"):
            errs.append(f"leg {leg.get('id')}: a self-transfer leg must carry risk.why")
    # invariant 2: no price without a timestamp
    for where, d in _walk_prices(it):
        if not d.get("quoted_at"):
            errs.append(f"{where}: price {d.get('price')} has no quoted_at - every price is a snapshot")
    return errs


# ---------------------------------------------------------------- edits
def new(trip_id, title, earliest=None, latest=None, nights=None, currency="EUR",
        budget=None, travelers=None, dest=None):
    if path_of(trip_id, dest).exists():
        raise ItineraryError(f"trip {trip_id!r} already exists")
    it = {"schema": SCHEMA, "trip_id": trip_id, "title": title, "status": "draft",
          "created": now_iso(), "updated": now_iso(),
          "window": {"earliest": earliest or "", "latest": latest or "",
                     "nights": nights or 0, "flex_days": 0},
          "currency": currency, "budget": budget or {},
          "travelers": travelers or [{"id": "me", "label": "me"}],
          "stops": [], "legs": [], "pois": [], "routes": []}
    return it


def _next_id(it, coll, prefix):
    used = {x.get("id") for x in it.get(coll) or []}
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def _city_centre(place, country=""):
    """Coordinates for a city from the engine's bundled gazetteer when the plugin runs next
    to the engine, else None (the caller passes --lat/--lng)."""
    here = pathlib.Path(__file__).resolve()
    for cand in [d / "engine" / "scripts" for d in here.parents]:
        if (cand / "geocode.py").is_file():
            sys.path.insert(0, str(cand))
            try:
                import geocode
                hit = geocode.resolve(f"{place}, {country}" if country else place)
                return hit
            except Exception:
                return None
    return None


def add_stop(it, place, arrive, nights, role="base", country="", lat=None, lng=None, why="",
             sid=None, brain_places=None):
    if role not in ROLES:
        raise ItineraryError(f"role must be one of {ROLES}")
    nights = int(nights)
    if lat is None or lng is None:
        pts = [r for r in (brain_places or []) if (r.get("city") or "").lower() == place.lower()
               and geo.has_coords(r)]
        c = geo.centroid(pts) if pts else _city_centre(place, country)
        if not c:
            raise ItineraryError(f"no coordinates for {place!r}: pass --lat/--lng")
        lat, lng = c
        if not country and pts:
            country = pts[0].get("country") or ""
    depart = (_d(arrive) + datetime.timedelta(days=nights)).isoformat() if arrive else ""
    s = {"id": sid or _next_id(it, "stops", "s"), "place": place, "country": country.upper(),
         "lat": round(float(lat), 5), "lng": round(float(lng), 5), "role": role,
         "arrive": arrive or "", "depart": depart, "nights": nights, "why": why,
         "stay": {}, "days": []}
    it["stops"].append(s)
    it["stops"].sort(key=lambda x: (x.get("arrive") or "9999", x["id"]))
    _refresh_window(it)
    return s


def _refresh_window(it):
    arr = [s["arrive"] for s in it["stops"] if s.get("arrive")]
    dep = [s["depart"] for s in it["stops"] if s.get("depart")]
    if arr and dep:
        it["window"]["earliest"] = it["window"].get("earliest") or min(arr)
        it["window"]["latest"] = it["window"].get("latest") or max(dep)
        it["window"]["nights"] = sum(int(s.get("nights") or 0) for s in it["stops"])


def _stop(it, sid):
    for s in it["stops"]:
        if s["id"] == sid:
            return s
    raise ItineraryError(f"no stop {sid!r}")


def _find_brain_place(brain_places, name):
    low = name.strip().lower()
    for r in brain_places or []:
        if (r.get("title") or "").lower() == low or (r.get("name") or "").lower() == low:
            return r
    return None


def add_poi(it, stop, name, kind="", lat=None, lng=None, why="", brain_places=None,
            rating=None, price_band="", booking=None, pid=None):
    _stop(it, stop)
    for p in it["pois"]:
        if p["stop"] == stop and p["name"].lower() == name.strip().lower():
            return p                                     # idempotent
    rec = _find_brain_place(brain_places, name)
    p = {"id": pid or _next_id(it, "pois", "p"), "stop": stop, "name": name.strip(),
         "kind": kind or "other", "from_brain": False, "brain_note": "", "why": why}
    if rec:
        # invariant 3: set from the brain's own record, never from the caller's say-so
        p.update({"name": rec["title"], "lat": rec["lat"], "lng": rec["lng"],
                  "from_brain": True, "brain_note": rec["note"]})
        p["kind"] = kind or _KIND_OF.get(rec.get("category", ""), "other")
        if rec.get("rating") is not None:
            p["rating"] = rec["rating"]
        p["why"] = why or brain_why(rec)
    else:
        if lat is None or lng is None:
            raise ItineraryError(f"{name!r} is not a place in this brain - pass --lat/--lng and a "
                                 "`why` saying where it came from (web only, no brain signal)")
        p.update({"lat": float(lat), "lng": float(lng)})
        p["why"] = why or "no brain signal — web only"
    if rating is not None:
        p["rating"] = rating
    if price_band:
        p["price_band"] = price_band
    if booking:
        p["booking"] = booking
    it["pois"].append(p)
    return p


def brain_why(rec):
    """One honest sentence tracing a suggestion to the user's own note."""
    bits = []
    for l in rec.get("lists") or []:
        bits.append(f"on your '{l}' list" + (f" since {rec['created'][:4]}" if rec.get("created") else ""))
    if rec.get("rating") is not None:
        bits.append(f"you rated it ★{rec['rating']:g}")
    if rec.get("visited") and not bits:
        bits.append("you have been before")
    if not bits and rec.get("saved"):
        bits.append("a pin you saved")
    return " · ".join(bits) or "in your places"


def brain_pois(it, stop, brain_places, radius_km=12.0, limit=16, min_love=0.3):
    """Pull the brain's own places around a stop into it, best first: saved-but-never-
    visited, then loved, never anything you rated low. Returns the POIs added."""
    s = _stop(it, stop)
    cands = []
    for r in brain_places or []:
        if not geo.has_coords(r):
            continue
        if geo.haversine_km(s, r) > radius_km:
            continue
        if r.get("rating") is not None and r["rating"] <= 2:
            continue
        if r.get("love", 0.5) < min_love:
            continue
        if r.get("category") in ("transport", "coworking", "event-venue", "hotel-breakfast"):
            continue
        rank = (0 if (r.get("saved") and not r.get("visited")) else 1, -r.get("love", 0.5), r["name"])
        cands.append((rank, r))
    added = []
    for _, r in sorted(cands, key=lambda x: x[0])[:limit]:
        before = len(it["pois"])
        p = add_poi(it, stop, r["title"], brain_places=[r])
        if len(it["pois"]) > before:
            added.append(p)
    return added


def plan_days(it, stop=None, per_day=4):
    """Allocate a stop's POIs to its days by area, and order each day into a walking route.

    Areas come from geo.cluster(); the biggest areas get the earliest days, and a day is
    topped up from the nearest remaining area. Arrival and departure days get half a day.
    A stopover with one night gets its arrival evening and departure morning, like any
    other stop - that is the point of it being a stop."""
    todo = [_stop(it, stop)] if stop else list(it["stops"])
    it["routes"] = [r for r in it.get("routes") or [] if r["stop"] not in {s["id"] for s in todo}]
    for s in todo:
        pois = [p for p in it["pois"] if p["stop"] == s["id"] and geo.has_coords(p)]
        n_days = max(1, int(s.get("nights") or 0) + (1 if s.get("role") != "daytrip" else 0))
        if not s.get("arrive"):
            s["days"] = []
            continue
        dates = [(_d(s["arrive"]) + datetime.timedelta(days=i)).isoformat() for i in range(n_days)]
        cap = [max(1, per_day // 2) if (i == 0 or i == n_days - 1) and n_days > 1 else per_day
               for i in range(n_days)]
        areas = geo.cluster(pois, radius_km=1.5)
        days = [[] for _ in dates]
        # An area stays on one day while that day has room; a new day is the one with the
        # most room left (full days before half days, earlier before later). When every
        # day is full the least-loaded one takes the overflow rather than dropping a place.
        for area in areas:
            cur = None
            for p in area:
                if cur is None or len(days[cur]) >= cap[cur]:
                    cur = max(range(n_days), key=lambda k: (cap[k] - len(days[k]), -k))
                    if cap[cur] - len(days[cur]) <= 0:
                        cur = min(range(n_days), key=lambda k: (len(days[k]) / cap[k], k))
                days[cur].append(p)
        s["days"] = []
        for i, date in enumerate(dates):
            if not days[i]:
                s["days"].append({"date": date, "route": "", "items": []})
                continue
            start = s.get("stay") if geo.has_coords(s.get("stay") or {}) else None
            ordered = geo.order_route(days[i], start)
            rid = _next_id(it, "routes", "r")
            poly = ([[start["lat"], start["lng"]]] if start else []) + \
                [[p["lat"], p["lng"]] for p in ordered]
            it["routes"].append({"id": rid, "stop": s["id"], "date": date,
                                 "ordered_pois": [p["id"] for p in ordered],
                                 "polyline": poly, "walk_minutes": geo.walk_minutes(
                                     ([start] if start else []) + ordered)})
            s["days"].append({"date": date, "route": rid, "items": [p["id"] for p in ordered]})
    return it


def set_stay(it, stop, name, url="", price=None, quoted_at="", status="candidate",
             lat=None, lng=None, source="", nights=None):
    s = _stop(it, stop)
    if price not in (None, "") and not quoted_at:
        raise ItineraryError("a price needs --quoted-at: when was it seen?")
    if status not in STAY_STATUSES:
        raise ItineraryError(f"status must be one of {STAY_STATUSES}")
    st = {"name": name, "url": url, "status": status}
    if price not in (None, ""):
        st.update({"price": float(price), "quoted_at": quoted_at, "currency": it.get("currency")})
    if source:
        st["source"] = source
    if lat is not None and lng is not None:
        st.update({"lat": float(lat), "lng": float(lng)})
    s["stay"] = st
    return st


def add_leg(it, leg):
    leg = dict(leg)
    leg.setdefault("id", _next_id(it, "legs", "l"))
    leg.setdefault("segments", [])
    leg.setdefault("tickets", [])
    leg.setdefault("self_transfer", False)
    it["legs"] = [l for l in it["legs"] if l["id"] != leg["id"]] + [leg]
    return leg


# ---------------------------------------------------------------- airports
_AIRPORTS = None


def airports():
    global _AIRPORTS
    if _AIRPORTS is None:
        try:
            _AIRPORTS = json.loads(reference("airports.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _AIRPORTS = {}
    return _AIRPORTS


def airport(code):
    a = airports().get(str(code or "").upper())
    return a if isinstance(a, dict) and "lat" in a else None


# ---------------------------------------------------------------- projection
def day_numbers(it):
    """{date: 1-based day number} across the whole trip, in date order."""
    dates = sorted({d["date"] for s in it["stops"] for d in s.get("days") or [] if d.get("date")})
    return {d: i + 1 for i, d in enumerate(dates)}


def _pt(lat, lng):
    return {"type": "Point", "coordinates": [round(float(lng), 6), round(float(lat), 6)]}


def _line(path):
    return {"type": "LineString", "coordinates": [[round(p[1], 6), round(p[0], 6)] for p in path]}


def _leg_path(leg, it):
    """[[lat, lng], ...] for a leg: segment airports, or the stops it joins."""
    pts = []
    for seg in leg.get("segments") or []:
        for code in (seg.get("from"), seg.get("to")):
            a = airport(code)
            if a and (not pts or pts[-1] != [a["lat"], a["lng"]]):
                pts.append([a["lat"], a["lng"]])
    if len(pts) < 2:
        for end in ("from", "to"):
            v = leg.get(end)
            a = airport(v)
            s = next((x for x in it["stops"] if x["id"] == v or x["place"] == v), None)
            if a:
                pts.append([a["lat"], a["lng"]])
            elif s:
                pts.append([s["lat"], s["lng"]])
            elif isinstance(leg.get(end + "_lat"), (int, float)):
                pts.append([leg[end + "_lat"], leg[end + "_lng"]])
    return pts


def to_geojson(it):
    """What the Studio Map draws. Coordinates in GeoJSON order ([lng, lat])."""
    days = day_numbers(it)
    poi_day = {}
    for s in it["stops"]:
        for d in s.get("days") or []:
            for n, pid in enumerate(d.get("items") or []):
                poi_day[pid] = (days.get(d["date"]), n + 1)
    feats = []
    for i, s in enumerate(it["stops"]):
        feats.append({"type": "Feature", "geometry": _pt(s["lat"], s["lng"]),
                      "properties": {"feature": "stop", "id": s["id"], "label": s["place"],
                                     "role": s.get("role"), "nights": s.get("nights"),
                                     "order": i + 1, "arrive": s.get("arrive"),
                                     "why": s.get("why", "")}})
        st = s.get("stay") or {}
        if geo.has_coords(st):
            feats.append({"type": "Feature", "geometry": _pt(st["lat"], st["lng"]),
                          "properties": {"feature": "stay", "id": s["id"] + "-stay",
                                         "stop": s["id"], "label": st.get("name", ""),
                                         "status": st.get("status", "")}})
    for p in it["pois"]:
        if not geo.has_coords(p):
            continue
        day, seq = poi_day.get(p["id"], (None, None))
        props = {"feature": "poi", "id": p["id"], "label": p["name"], "stop": p["stop"],
                 "kind": p.get("kind", "other"), "from_brain": bool(p.get("from_brain")),
                 "why": p.get("why", "")}
        if day:
            props.update({"day": day, "seq": seq})
        if p.get("from_brain") and p.get("brain_note", "").endswith(".md"):
            props["note_id"] = p["brain_note"][:-3]
        feats.append({"type": "Feature", "geometry": _pt(p["lat"], p["lng"]), "properties": props})
    for leg in it["legs"]:
        pts = _leg_path(leg, it)
        if len(pts) < 2:
            continue
        path = []
        for a, b in zip(pts, pts[1:]):
            seg = geo.geodesic(a, b, 32) if leg.get("mode") == "flight" else [a, b]
            path.extend(seg if not path else seg[1:])
        feats.append({"type": "Feature", "geometry": _line(path),
                      "properties": {"feature": "leg", "id": leg["id"], "mode": leg.get("mode"),
                                     "self_transfer": bool(leg.get("self_transfer")),
                                     "label": f"{leg.get('from', '')} → {leg.get('to', '')}",
                                     "risk": (leg.get("risk") or {}).get("level", "")}})
    for r in it.get("routes") or []:
        if len(r.get("polyline") or []) >= 2:
            feats.append({"type": "Feature", "geometry": _line(r["polyline"]),
                          "properties": {"feature": "route", "id": r["id"], "stop": r["stop"],
                                         "day": days.get(r.get("date")),
                                         "walk_minutes": r.get("walk_minutes")}})
    return {"type": "FeatureCollection",
            "properties": {"schema": MAP_SCHEMA, "layer": "trip", "trip_id": it["trip_id"],
                           "title": it["title"], "days": len(days), "updated": it.get("updated", "")},
            "features": feats}


# ---------------------------------------------------------------- current trip
def activate(trip_id, dest=None):
    if not path_of(trip_id, dest).exists():
        raise ItineraryError(f"no trip {trip_id!r}")
    root = state_root()
    root.mkdir(parents=True, exist_ok=True)
    _atomic_write(root / "current.json", json.dumps({"trip_id": trip_id, "since": now_iso()}) + "\n")
    project_all(dest)
    return root / "current.json"


def current(dest=None):
    try:
        tid = json.loads((state_root() / "current.json").read_text(encoding="utf-8")).get("trip_id")
    except (OSError, ValueError):
        return None
    return tid if tid and path_of(tid, dest).exists() else None


def list_trips(dest=None):
    d = trips_dir(dest)
    return sorted(p.parent.name for p in d.glob("*/itinerary.json")) if d.is_dir() else []


ALL_TRIPS_GEOJSON = "All Trips.geojson"


def all_trips_geojson(dest=None):
    """Every trip at a glance - its stops and legs, no POIs - so the Map can show the trips
    that are NOT current as an overview. The current one is flagged; Studio draws it in
    full from its own map.geojson and skips it here."""
    cur = current(dest)
    feats = []
    for tid in list_trips(dest):
        try:
            it = load(tid, dest)
        except (ItineraryError, ValueError):
            continue
        base = {"trip_id": tid, "title": it.get("title", tid), "status": it.get("status", ""),
                "current": tid == cur}
        stops = [s for s in it.get("stops") or [] if geo.has_coords(s)]
        for i, s in enumerate(stops):
            feats.append({"type": "Feature", "geometry": _pt(s["lat"], s["lng"]),
                          "properties": dict(base, feature="stop", id=f"{tid}:{s['id']}", label=s["place"],
                                             order=i + 1, role=s.get("role"), nights=s.get("nights"),
                                             arrive=s.get("arrive", ""))})
        drew = False
        for leg in it.get("legs") or []:
            pts = _leg_path(leg, it)
            if len(pts) < 2:
                continue
            path = []
            for a, b in zip(pts, pts[1:]):
                seg = geo.geodesic(a, b, 24) if leg.get("mode") == "flight" else [a, b]
                path.extend(seg if not path else seg[1:])
            feats.append({"type": "Feature", "geometry": _line(path),
                          "properties": dict(base, feature="leg", id=f"{tid}:{leg['id']}",
                                             mode=leg.get("mode"),
                                             self_transfer=bool(leg.get("self_transfer")))})
            drew = True
        if not drew and len(stops) > 1:
            # no flights yet: join the stops in order, so the trip still reads as a trip
            feats.append({"type": "Feature",
                          "geometry": _line([[s["lat"], s["lng"]] for s in stops]),
                          "properties": dict(base, feature="path", id=f"{tid}:path")})
    return {"type": "FeatureCollection",
            "properties": {"schema": MAP_SCHEMA, "layer": "trips", "current": cur or "",
                           "trips": len(list_trips(dest))},
            "features": feats}


def project_all(dest=None):
    """Rewrite All Trips.geojson at the layer root - only when it changed."""
    p = render_dir(dest) / ALL_TRIPS_GEOJSON
    text = json.dumps(all_trips_geojson(dest), ensure_ascii=False) + "\n"
    try:
        if p.is_file() and p.read_text(encoding="utf-8") == text:
            return p
    except OSError:
        pass
    _atomic_write(p, text)
    return p


def summary(it):
    days = day_numbers(it)
    out = [f"{it['title']} ({it['trip_id']}) — {it['status']}, {len(days)} days, "
           f"{len(it['stops'])} stops, {len(it['pois'])} places, {len(it['legs'])} legs"]
    for s in it["stops"]:
        brain = sum(1 for p in it["pois"] if p["stop"] == s["id"] and p.get("from_brain"))
        tot = sum(1 for p in it["pois"] if p["stop"] == s["id"])
        out.append(f"  {s['id']} {s['place']} [{s['role']}] {s.get('arrive')} +{s.get('nights')}n · "
                   f"{tot} places ({brain} from your brain)"
                   + (f" · stay: {s['stay'].get('name')}" if s.get("stay") else ""))
    for l in it["legs"]:
        out.append(f"  {l['id']} {l.get('from')}→{l.get('to')} {l.get('mode')}"
                   + (" · SELF-TRANSFER" if l.get("self_transfer") else ""))
    return "\n".join(out)


# ---------------------------------------------------------------- cli
def _brain_places():
    try:
        import places, taste
        return taste.enrich(places.load())
    except Exception:
        return []


def main(argv=None):
    ap = argparse.ArgumentParser(description="the sbl-itinerary/1 object")
    ap.add_argument("--dest", help="render dir override (tests)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new"); s.add_argument("--id", required=True); s.add_argument("--title", required=True)
    s.add_argument("--earliest"); s.add_argument("--latest"); s.add_argument("--nights", type=int)
    s.add_argument("--currency", default="EUR"); s.add_argument("--budget", help="JSON object")
    s = sub.add_parser("add-stop"); s.add_argument("trip"); s.add_argument("--place", required=True)
    s.add_argument("--country", default=""); s.add_argument("--role", default="base")
    s.add_argument("--arrive", required=True); s.add_argument("--nights", type=int, required=True)
    s.add_argument("--lat", type=float); s.add_argument("--lng", type=float); s.add_argument("--why", default="")
    s = sub.add_parser("add-poi"); s.add_argument("trip"); s.add_argument("--stop", required=True)
    s.add_argument("--name", required=True); s.add_argument("--kind", default="")
    s.add_argument("--lat", type=float); s.add_argument("--lng", type=float); s.add_argument("--why", default="")
    s.add_argument("--rating", type=float); s.add_argument("--price-band", default="")
    s.add_argument("--booking-url", default="")
    s = sub.add_parser("brain-pois"); s.add_argument("trip"); s.add_argument("--stop", required=True)
    s.add_argument("--radius-km", type=float, default=12.0); s.add_argument("--max", type=int, default=16)
    s = sub.add_parser("plan-days"); s.add_argument("trip"); s.add_argument("--stop"); s.add_argument("--per-day", type=int, default=4)
    s = sub.add_parser("set-stay"); s.add_argument("trip"); s.add_argument("--stop", required=True)
    s.add_argument("--name", required=True); s.add_argument("--url", default="")
    s.add_argument("--price", type=float); s.add_argument("--quoted-at", default="")
    s.add_argument("--status", default="candidate"); s.add_argument("--source", default="")
    s.add_argument("--lat", type=float); s.add_argument("--lng", type=float)
    s = sub.add_parser("add-leg"); s.add_argument("trip"); s.add_argument("--json", required=True)
    s = sub.add_parser("set-status"); s.add_argument("trip"); s.add_argument("status", choices=STATUSES)
    for name in ("validate", "geojson", "activate", "show"):
        s = sub.add_parser(name); s.add_argument("trip")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "new":
            it = new(a.id, a.title, a.earliest, a.latest, a.nights, a.currency,
                     json.loads(a.budget) if a.budget else None, dest=a.dest)
            d = save(it, a.dest)
            print(d / "itinerary.json")
            return 0
        if a.cmd == "list":
            cur = current(a.dest)
            for t in list_trips(a.dest):
                print(("* " if t == cur else "  ") + t)
            return 0
        it = load(a.trip, a.dest)
        if a.cmd == "validate":
            errs = validate(it)
            print("\n".join(errs) if errs else "valid")
            return 1 if errs else 0
        if a.cmd == "show":
            print(summary(it))
            return 0
        if a.cmd == "activate":
            print(activate(a.trip, a.dest))
            return 0
        if a.cmd == "add-stop":
            st = add_stop(it, a.place, a.arrive, a.nights, a.role, a.country, a.lat, a.lng, a.why,
                          brain_places=_brain_places())
            print(f"{st['id']} {st['place']} ({st['lat']}, {st['lng']})")
        elif a.cmd == "add-poi":
            p = add_poi(it, a.stop, a.name, a.kind, a.lat, a.lng, a.why, _brain_places(),
                        a.rating, a.price_band,
                        {"url": a.booking_url, "status": "link"} if a.booking_url else None)
            print(f"{p['id']} {p['name']} from_brain={p['from_brain']} — {p['why']}")
        elif a.cmd == "brain-pois":
            added = brain_pois(it, a.stop, _brain_places(), a.radius_km, a.max)
            for p in added:
                print(f"{p['id']} {p['name']} — {p['why']}")
            print(f"{len(added)} place(s) from your brain")
        elif a.cmd == "plan-days":
            plan_days(it, a.stop, a.per_day)
        elif a.cmd == "set-stay":
            set_stay(it, a.stop, a.name, a.url, a.price, a.quoted_at, a.status, a.lat, a.lng, a.source)
        elif a.cmd == "add-leg":
            leg = json.loads(pathlib.Path(a.json).read_text(encoding="utf-8")) if a.json != "-" \
                else json.load(sys.stdin)
            add_leg(it, leg)
        elif a.cmd == "set-status":
            it["status"] = a.status
        # geojson (and every edit) - save re-projects map.geojson
        d = save(it, a.dest)
        if a.cmd in ("plan-days", "geojson"):
            print(summary(it))
        print(f"wrote {d / 'itinerary.json'} + map.geojson", file=sys.stderr)
        return 0
    except ItineraryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
