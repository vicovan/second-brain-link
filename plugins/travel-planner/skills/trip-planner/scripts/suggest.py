#!/usr/bin/env python3
"""
suggest.py - places the Travel Agent suggests, before (or without) a trip.

"Where should I get coffee in Iași?" is a real answer that belongs on the Map, but it is not
an itinerary. A suggestion SET is that answer as a file:

    <travel layer>/suggestions/<set_id>.json      (schema "sbl-suggest/1")

and every change re-projects the one file Studio's Map draws them from:

    <travel layer>/Suggestions.geojson            (the active set + the Trip Ideas)

The same three honesty rules as itinerary.py, applied to a list:

  1. A place in the brain is LINKED, never recreated: a name that matches a place note takes
     that note's own coordinates and `from_brain: true`. Nothing else is ever from_brain.
  2. A web pick needs coordinates read from the page (a Google Maps URL carries `@lat,lng`)
     and they must fall within RADIUS_KM of the set's centre - an invented or mistyped
     coordinate lands in the wrong country, and this refuses it rather than drawing it.
  3. A web pick's `why` starts with "no brain signal — web only". A pick with no coordinates
     at all is kept (it is still a suggestion) and listed as "not on the map".

    suggest.py new --id iasi-coffee --title "Specialty coffee in Iași" --near "Iasi" [--country RO]
    suggest.py add <set_id> --name "Fika" --lat 47.17 --lng 27.57 --kind cafe --why "…" [--url …] [--rating 4.7]
    suggest.py add <set_id> --name "Foundry Cafe 64"          (a place in the brain - linked)
    suggest.py remove <set_id> <pick_id>
    suggest.py activate <set_id>        (the set the Map shows; `new` activates too)
    suggest.py clear                    (show no set - Trip Ideas stay on the Map)
    suggest.py to-trip <set_id> <trip_id> --stop s1 [--picks g1,g3]
    suggest.py geojson                  (re-project Suggestions.geojson)
    suggest.py list | show <set_id>
"""
import argparse, json, os, pathlib, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import itinerary as itin  # noqa: E402
from paths import render_dir, state_root, TRIP_ID_RE  # noqa: E402

SCHEMA = "sbl-suggest/1"
GEOJSON = "Suggestions.geojson"
RADIUS_KM = 60.0
WEB_ONLY = "no brain signal — web only"
MAX_PICKS = 60


class SuggestError(ValueError):
    pass


def sets_dir(dest=None):
    return render_dir(dest) / "suggestions"


def set_path(set_id, dest=None):
    if not TRIP_ID_RE.match(set_id or ""):
        raise SuggestError(f"bad set id {set_id!r}: lowercase letters, digits and hyphens only")
    return sets_dir(dest) / f"{set_id}.json"


def load(set_id, dest=None):
    p = set_path(set_id, dest)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SuggestError(f"no suggestion set {set_id!r} at {p}")


def list_sets(dest=None):
    d = sets_dir(dest)
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def save(s, dest=None):
    s["updated"] = itin.now_iso()
    itin._atomic_write(set_path(s["set_id"], dest), json.dumps(s, ensure_ascii=False, indent=1) + "\n")
    project(dest)
    return set_path(s["set_id"], dest)


# ---------------------------------------------------------------- the active set
def _cur_file():
    return state_root() / "current_suggestions.json"


def activate(set_id, dest=None):
    if set_id and not set_path(set_id, dest).exists():
        raise SuggestError(f"no suggestion set {set_id!r}")
    root = state_root()
    root.mkdir(parents=True, exist_ok=True)
    itin._atomic_write(_cur_file(), json.dumps({"set_id": set_id or "", "since": itin.now_iso()}) + "\n")
    project(dest)


def current(dest=None):
    try:
        sid = json.loads(_cur_file().read_text(encoding="utf-8")).get("set_id")
    except (OSError, ValueError):
        return None
    try:
        return sid if sid and set_path(sid, dest).exists() else None
    except SuggestError:
        return None


# ---------------------------------------------------------------- edits
def _centre(near, country, brain_places):
    pts = [r for r in (brain_places or []) if (r.get("city") or "").lower() == near.lower()
           and geo.has_coords(r)]
    if pts:
        return geo.centroid(pts)
    return itin._city_centre(near, country)


def new(set_id, title, near, country="", lat=None, lng=None, brain_places=None, dest=None):
    if set_path(set_id, dest).exists():
        raise SuggestError(f"set {set_id!r} exists - add to it, or pick another id")
    if lat is None or lng is None:
        c = _centre(near, country, brain_places)
        if not c:
            raise SuggestError(f"no coordinates for {near!r}: pass --lat/--lng for the centre")
        lat, lng = c
    return {"schema": SCHEMA, "set_id": set_id, "title": title.strip(),
            "near": {"place": near, "country": (country or "").upper(),
                     "lat": round(float(lat), 5), "lng": round(float(lng), 5)},
            "created": itin.now_iso(), "updated": "", "picks": []}


def add(s, name, kind="", lat=None, lng=None, why="", url="", rating=None, brain_places=None,
        reviews=None, evidence=None, match=""):
    name = (name or "").strip()
    if not name:
        raise SuggestError("a pick needs a name")
    for p in s["picks"]:
        if p["name"].lower() == name.lower():
            return p                                          # idempotent
    if len(s["picks"]) >= MAX_PICKS:
        raise SuggestError(f"a set holds at most {MAX_PICKS} picks - start another set")
    rec = itin._find_brain_place(brain_places, name)
    p = {"id": itin._next_id({"picks": s["picks"]}, "picks", "g"), "name": name,
         "kind": kind or "other", "from_brain": False, "brain_note": "", "why": why, "url": url}
    if rec:
        # rule 1: from the brain's own record, never from the caller's say-so
        p.update({"name": rec["title"], "from_brain": True, "brain_note": rec["note"]})
        if geo.has_coords(rec):
            p.update({"lat": rec["lat"], "lng": rec["lng"]})
        p["kind"] = kind or itin._KIND_OF.get(rec.get("category", ""), "other")
        if rec.get("rating") is not None:
            p["rating"] = rec["rating"]
        p["why"] = why or itin.brain_why(rec)
    else:
        if (lat is None) != (lng is None):
            raise SuggestError("pass both --lat and --lng, or neither")
        if lat is not None:
            pt = {"lat": float(lat), "lng": float(lng)}
            if not geo.has_coords(pt):
                raise SuggestError(f"{name!r}: {lat}, {lng} is not a coordinate")
            km = geo.haversine_km(pt, s["near"])
            if km > RADIUS_KM:
                # rule 2: a wrong coordinate is refused, not drawn in the wrong country
                raise SuggestError(f"{name!r} is {km:.0f} km from {s['near']['place']} (limit "
                                   f"{RADIUS_KM:.0f}) - re-read the coordinates from the page")
            p.update({"lat": round(pt["lat"], 6), "lng": round(pt["lng"], 6)})
        w = (why or "").strip()
        p["why"] = w if w.startswith(WEB_ONLY) else (WEB_ONLY + (" · " + w if w else ""))
    if rating is not None:
        p["rating"] = rating
    if reviews is not None:
        p["reviews"] = int(reviews)
    # What the reviews actually say, in reviewers' words, where it bears on the user's
    # taste - read on the place's page, never paraphrased into a quote.
    ev = [str(e).strip()[:220] for e in (evidence or []) if str(e).strip()][:4]
    if ev:
        p["evidence"] = ev
    if match:
        if match not in ("high", "medium", "low"):
            raise SuggestError("--match must be high, medium or low")
        p["match"] = match
    s["picks"].append(p)
    return p


def remove(s, pick_id):
    before = len(s["picks"])
    s["picks"] = [p for p in s["picks"] if p["id"] != pick_id]
    if len(s["picks"]) == before:
        raise SuggestError(f"no pick {pick_id!r}")


def to_trip(s, trip_id, stop, picks=None, brain_places=None, dest=None):
    """Move picks into a trip as POIs - through itinerary.add_poi, so its invariants hold."""
    it = itin.load(trip_id, dest)
    want = set(picks or [])
    added = []
    for p in s["picks"]:
        if want and p["id"] not in want:
            continue
        if not p.get("from_brain") and not geo.has_coords(p):
            continue
        added.append(itin.add_poi(it, stop, p["name"], p.get("kind", ""),
                                  None if p.get("from_brain") else p.get("lat"),
                                  None if p.get("from_brain") else p.get("lng"),
                                  p.get("why", ""), brain_places, p.get("rating"), "",
                                  {"url": p["url"], "status": "link"} if p.get("url") else None))
    itin.save(it, dest)
    return added


# ---------------------------------------------------------------- the map
def _ideas():
    try:
        return (json.loads((state_root() / "ideas.json").read_text(encoding="utf-8")).get("ideas") or [])
    except (OSError, ValueError):
        return []


def to_geojson(dest=None):
    sid = current(dest)
    s = None
    if sid:
        try:
            s = load(sid, dest)
        except (SuggestError, ValueError):
            s = None
    feats = []
    for n, p in enumerate((s or {}).get("picks") or [], 1):
        if not geo.has_coords(p):
            continue
        props = {"feature": "suggestion", "id": p["id"], "label": p["name"], "seq": n,
                 "kind": p.get("kind", "other"), "from_brain": bool(p.get("from_brain")),
                 "why": p.get("why", ""), "set": s["set_id"]}
        if p.get("url"):
            props["url"] = p["url"]
        if p.get("rating") is not None:
            props["rating"] = p["rating"]
        for k in ("reviews", "match"):
            if p.get(k) not in (None, ""):
                props[k] = p[k]
        if p.get("from_brain") and str(p.get("brain_note", "")).endswith(".md"):
            props["note_id"] = p["brain_note"][:-3]
        feats.append({"type": "Feature", "geometry": itin._pt(p["lat"], p["lng"]), "properties": props})
    for n, x in enumerate(_ideas(), 1):
        if not geo.has_coords(x):
            continue
        feats.append({"type": "Feature", "geometry": itin._pt(x["lat"], x["lng"]),
                      "properties": {"feature": "idea", "id": f"i{n}", "rank": n,
                                     "label": f"{x['city']}, {x['country']}" if x.get("country") else x["city"],
                                     "city": x["city"], "why": x.get("why", "")}})
    props = {"schema": itin.MAP_SCHEMA, "layer": "suggestions", "set_id": sid or "",
             "title": (s or {}).get("title", ""), "updated": (s or {}).get("updated", "")}
    if s:
        props["near"] = s["near"]["place"]
        props["unmapped"] = sum(1 for p in s["picks"] if not geo.has_coords(p))
    return {"type": "FeatureCollection", "properties": props, "features": feats}


def geojson_text(dest=None):
    return json.dumps(to_geojson(dest), ensure_ascii=False) + "\n"


def project(dest=None):
    """Rewrite Suggestions.geojson - only when it changed, so a watching Map does not
    re-fit on a no-op."""
    p = render_dir(dest) / GEOJSON
    text = geojson_text(dest)
    try:
        if p.is_file() and p.read_text(encoding="utf-8") == text:
            return p
    except OSError:
        pass
    itin._atomic_write(p, text)
    return p


def fence(s):
    return "```places\n" + json.dumps({"set": s["set_id"]}) + "\n```"


def summary(s):
    out = [f"{s['title']} ({s['set_id']}) — near {s['near']['place']}, {len(s['picks'])} pick(s)"]
    for p in s["picks"]:
        where = "" if geo.has_coords(p) else " · NOT ON THE MAP (no coordinates)"
        out.append(f"  {p['id']} {p['name']} [{p.get('kind')}]"
                   + (" · from your brain" if p.get("from_brain") else "") + where + f" — {p.get('why', '')}")
    return "\n".join(out)


# ---------------------------------------------------------------- cli
def main(argv=None):
    ap = argparse.ArgumentParser(description="suggestion sets the Map draws")
    ap.add_argument("--dest", help="render dir override (tests)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new"); s.add_argument("--id", required=True); s.add_argument("--title", required=True)
    s.add_argument("--near", required=True); s.add_argument("--country", default="")
    s.add_argument("--lat", type=float); s.add_argument("--lng", type=float)
    s = sub.add_parser("add"); s.add_argument("set")
    s.add_argument("--name", required=True); s.add_argument("--kind", default="")
    s.add_argument("--lat", type=float); s.add_argument("--lng", type=float)
    s.add_argument("--why", default=""); s.add_argument("--url", default=""); s.add_argument("--rating", type=float)
    s.add_argument("--reviews", type=int, help="how many reviews the rating rests on")
    s.add_argument("--evidence", action="append", default=[],
                   help="a reviewer's own words that bear on the user's taste (repeatable, max 4)")
    s.add_argument("--match", default="", help="high | medium | low — against taste.md")
    s = sub.add_parser("remove"); s.add_argument("set"); s.add_argument("pick")
    s = sub.add_parser("activate"); s.add_argument("set")
    sub.add_parser("clear"); sub.add_parser("list"); sub.add_parser("geojson")
    s = sub.add_parser("show"); s.add_argument("set")
    s = sub.add_parser("fence"); s.add_argument("set")
    s = sub.add_parser("to-trip"); s.add_argument("set"); s.add_argument("trip")
    s.add_argument("--stop", required=True); s.add_argument("--picks", default="")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            cur = current(a.dest)
            for sid in list_sets(a.dest):
                print(("* " if sid == cur else "  ") + sid)
            return 0
        if a.cmd == "clear":
            activate("", a.dest)
            print("no suggestion set on the Map")
            return 0
        if a.cmd == "geojson":
            print(project(a.dest))
            return 0
        if a.cmd == "new":
            st = new(a.id, a.title, a.near, a.country, a.lat, a.lng, itin._brain_places(), a.dest)
            save(st, a.dest)
            activate(a.id, a.dest)
            print(f"{a.id} near {st['near']['place']} ({st['near']['lat']}, {st['near']['lng']}) - active on the Map")
            return 0
        st = load(a.set, a.dest)
        if a.cmd == "show":
            print(summary(st))
            return 0
        if a.cmd == "fence":
            print(fence(st))
            return 0
        if a.cmd == "activate":
            activate(a.set, a.dest)
            print(f"{a.set} active on the Map")
            return 0
        if a.cmd == "to-trip":
            got = to_trip(st, a.trip, a.stop, [x for x in a.picks.split(",") if x], itin._brain_places(), a.dest)
            print(f"{len(got)} pick(s) added to {a.trip} as POIs")
            return 0
        if a.cmd == "add":
            p = add(st, a.name, a.kind, a.lat, a.lng, a.why, a.url, a.rating, itin._brain_places(),
                    a.reviews, a.evidence, a.match)
            print(f"{p['id']} {p['name']} from_brain={p['from_brain']}"
                  + ("" if geo.has_coords(p) else " (not on the map: no coordinates)") + f" — {p['why']}")
        elif a.cmd == "remove":
            remove(st, a.pick)
        save(st, a.dest)
        # a set being worked on is the one the Map shows
        if current(a.dest) != st["set_id"]:
            activate(st["set_id"], a.dest)
        return 0
    except (SuggestError, itin.ItineraryError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
