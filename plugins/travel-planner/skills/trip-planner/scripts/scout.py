#!/usr/bin/env python3
"""
scout.py - where should I go, and when? Answered from the brain alone. Zero web requests.

A city where you saved five places and went to none is a trip you have already planned and
never noticed. This finds those, and cites the notes that justify each one:

  - saved-but-never-visited pins, clustered by city           (the strongest signal)
  - places you rated highly there                              (a return is worth it)
  - people in your network whose notes carry coordinates nearby  ("four people you know")
  - how worn a city is: many visits and nothing left saved     (so it is not proposed again)
  - your home city is never a destination
  - months: the months you have historically travelled, from dated visits/photos/check-ins

Writes the ranked ideas to <state root>/ideas.json, which render_brain.py turns into the
"Trip Ideas" note. `--json` prints them instead.

    python3 scout.py                 # ranked ideas, one line each
    python3 scout.py --top 5 --json
    python3 scout.py --no-write      # do not touch ideas.json
"""
import argparse, collections, datetime, json, os, pathlib, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import places as _places  # noqa: E402
import taste as _taste  # noqa: E402
from paths import brain_at_cwd, layer, state_root  # noqa: E402

PEOPLE_RADIUS_KM = 40
HOME_RADIUS_KM = 50
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _notes_with_coords(brain, key):
    d = pathlib.Path(brain) / layer(brain, key)
    out = []
    if not d.is_dir():
        return out
    for p in sorted(d.rglob("*.md")):
        try:
            fm, _ = _places.parse_front(p.read_text(encoding="utf-8"))
        except OSError:
            continue
        la, ln = _places._num(fm.get("lat")), _places._num(fm.get("lng"))
        if la is None or ln is None:
            continue
        out.append({"title": fm.get("title") or p.stem, "lat": la, "lng": ln,
                    "note": p.relative_to(brain).as_posix()})
    return out


def home(brain):
    got = _notes_with_coords(brain, "root")
    return got[0] if got else None


def travel_months(recs, home_pt):
    """Month histogram of dated visits/photos/check-ins/events away from home."""
    c = collections.Counter()
    for r in recs:
        if not r.get("visited") or not r.get("created"):
            continue
        if home_pt and geo.has_coords(r) and geo.haversine_km(r, home_pt) < HOME_RADIUS_KM:
            continue
        try:
            c[datetime.date.fromisoformat(r["created"][:10]).month] += 1
        except ValueError:
            pass
    return c


def ideas(brain=None, top=10):
    b = pathlib.Path(brain) if brain else brain_at_cwd()
    if b is None:
        return [], {}
    recs = _taste.enrich(_places.load(b))
    home_pt = home(b)
    people = _notes_with_coords(b, "people")
    months = travel_months(recs, home_pt)
    out = []
    for (city, cc), rs in _places.by_city(recs).items():
        if not city:
            continue
        pts = [r for r in rs if geo.has_coords(r)]
        c = geo.centroid(pts)
        if not c:
            continue
        centre = {"lat": c[0], "lng": c[1]}
        if home_pt and geo.haversine_km(centre, home_pt) < HOME_RADIUS_KM:
            continue
        saved_nv = sorted((r for r in rs if r["saved"] and not r["visited"]),
                          key=lambda r: (-r["love"], r["name"]))
        loved = sorted((r for r in rs if r.get("rating") is not None and r["rating"] >= 4),
                       key=lambda r: (-r["rating"], r["name"]))
        visited = [r for r in rs if r["visited"]]
        near = sorted((p for p in people if geo.haversine_km(p, centre) <= PEOPLE_RADIUS_KM),
                      key=lambda p: p["title"])
        worn = len(visited) >= 5 and not saved_nv
        score = 3 * len(saved_nv) + 2 * len(loved) + 1.0 * min(len(near), 5) \
            + sum(r["love"] for r in saved_nv) - (6 if worn else 0)
        if score <= 0:
            continue
        why = []
        if saved_nv:
            why.append(f"{len(saved_nv)} saved place(s) you never visited")
        if loved:
            why.append(f"{len(loved)} place(s) you rated ★4+")
        if near:
            why.append(f"{len(near)} people you know nearby")
        if visited and not worn:
            why.append(f"been before ({len(visited)} visit signal(s))")
        out.append({"city": city, "country": cc, "lat": round(c[0], 5), "lng": round(c[1], 5),
                    "score": round(score, 2), "why": " · ".join(why),
                    "saved_not_visited": [r["note"] for r in saved_nv[:8]],
                    "loved": [r["note"] for r in loved[:5]],
                    "people": [p["note"] for p in near[:6]],
                    "visited": len(visited),
                    "categories": [k for k, _ in collections.Counter(
                        r["category"] for r in rs if r["category"] != "other").most_common(4)]})
    out.sort(key=lambda x: (-x["score"], x["city"]))
    meta = {"generated": datetime.datetime.now().replace(microsecond=0).isoformat(),
            "home": home_pt["title"] if home_pt else "",
            "months": [MONTHS[m - 1] for m, _ in months.most_common(3)],
            "places": len(recs)}
    return out[:top], meta


def write(ideas_list, meta):
    root = state_root()
    root.mkdir(parents=True, exist_ok=True)
    p = root / "ideas.json"
    tmp = p.with_name("ideas.json.tmp")
    tmp.write_text(json.dumps({"meta": meta, "ideas": ideas_list}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    os.replace(tmp, p)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--brain")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    got, meta = ideas(a.brain, a.top)
    if not a.no_write and got:
        write(got, meta)
        try:  # the ideas are pins on the Map too (Suggestions.geojson)
            import suggest
            suggest.project()
        except Exception as e:  # the ideas file is written either way
            print(f"note: could not update the Map's suggestions layer: {e}", file=sys.stderr)
    if a.json:
        print(json.dumps({"meta": meta, "ideas": got}, ensure_ascii=False, indent=1))
        return 0
    if not got:
        print("no trip ideas — the brain has no places with a city away from home", file=sys.stderr)
        return 1
    if meta.get("months"):
        print(f"you usually travel in: {', '.join(meta['months'])}")
    for i, x in enumerate(got, 1):
        print(f"{i}. {x['city']}, {x['country']} — {x['why']} (score {x['score']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
