#!/usr/bin/env python3
"""
geo.py - the geometry a trip needs, in pure stdlib. No network, no maps API.

    haversine_km(a, b)            great-circle distance between (lat, lng) pairs
    bbox(points)                  (min_lat, min_lng, max_lat, max_lng)
    centroid(points)              mean position (fine at city scale)
    cluster(points, radius_km)    greedy clusters -> "areas worth a day"
    order_route(points, start)    nearest-neighbour + 2-opt ordering of a day's stops
    walk_minutes(path)            path length at a walking pace, with a detour factor
    geodesic(a, b, n)             points along the great circle, for drawing a flight

`points` everywhere are dicts carrying at least `lat` and `lng`; the functions return the
same dicts (never copies), so callers keep their ids and names.

    python3 geo.py --demo        # prints a worked example
"""
import math, sys

EARTH_KM = 6371.0
WALK_KMH = 4.5          # an unhurried city pace
DETOUR = 1.3            # streets are not straight lines


def _ll(p):
    if isinstance(p, dict):
        return float(p["lat"]), float(p["lng"])
    return float(p[0]), float(p[1])


def haversine_km(a, b):
    (la1, ln1), (la2, ln2) = _ll(a), _ll(b)
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(ln2 - ln1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(h)))


def has_coords(p):
    try:
        la, ln = _ll(p)
    except (KeyError, TypeError, ValueError):
        return False
    return -90 <= la <= 90 and -180 <= ln <= 180 and not (la == 0 and ln == 0)


def bbox(points):
    pts = [_ll(p) for p in points if has_coords(p)]
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def centroid(points):
    pts = [_ll(p) for p in points if has_coords(p)]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def cluster(points, radius_km=1.5):
    """Greedy single-pass clustering, deterministic: points are visited in input order,
    each joins the first cluster whose centroid is within `radius_km`, else starts one.
    Returns a list of lists, largest first (ties keep first-seen order)."""
    groups = []            # [ [points], (clat, clng) ]
    for p in points:
        if not has_coords(p):
            continue
        for g in groups:
            if haversine_km(p, g[1]) <= radius_km:
                g[0].append(p)
                g[1] = centroid(g[0])
                break
        else:
            groups.append([[p], _ll(p)])
    order = sorted(range(len(groups)), key=lambda i: (-len(groups[i][0]), i))
    return [groups[i][0] for i in order]


def _path_len(seq):
    return sum(haversine_km(seq[i], seq[i + 1]) for i in range(len(seq) - 1))


def order_route(points, start=None):
    """Order a day's stops into a short walking route. Nearest neighbour from `start`
    (a point or None = the first given), then 2-opt until no swap helps. Deterministic."""
    pts = [p for p in points if has_coords(p)]
    if len(pts) <= 2:
        return pts
    first = start if start is not None and has_coords(start) else pts[0]
    rest = [p for p in pts if p is not first]
    route = [first] if first in pts else []
    cur = first
    while rest:
        nxt = min(rest, key=lambda p: haversine_km(cur, p))
        route.append(nxt)
        rest.remove(nxt)
        cur = nxt
    improved = True
    while improved:
        improved = False
        for i in range(1, len(route) - 2):
            for j in range(i + 1, len(route) - 1):
                a, b, c, d = route[i - 1], route[i], route[j], route[j + 1]
                if haversine_km(a, c) + haversine_km(b, d) < haversine_km(a, b) + haversine_km(c, d) - 1e-9:
                    route[i:j + 1] = reversed(route[i:j + 1])
                    improved = True
    return route


def walk_minutes(seq):
    return int(round(_path_len([p for p in seq if has_coords(p)]) * DETOUR / WALK_KMH * 60))


def geodesic(a, b, n=24):
    """`n`+1 points along the great circle from a to b, as [lat, lng] pairs."""
    (la1, ln1), (la2, ln2) = _ll(a), _ll(b)
    p1, l1, p2, l2 = map(math.radians, (la1, ln1, la2, ln2))
    d = 2 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 +
                                math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2))
    if d == 0:
        return [[la1, ln1], [la2, ln2]]
    out = []
    for i in range(n + 1):
        f = i / n
        A, B = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
        x = A * math.cos(p1) * math.cos(l1) + B * math.cos(p2) * math.cos(l2)
        y = A * math.cos(p1) * math.sin(l1) + B * math.cos(p2) * math.sin(l2)
        z = A * math.sin(p1) + B * math.sin(p2)
        out.append([round(math.degrees(math.atan2(z, math.hypot(x, y))), 5),
                    round(math.degrees(math.atan2(y, x)), 5)])
    return out


def _demo():
    pts = [{"id": "a", "lat": 38.7117, "lng": -9.1303}, {"id": "b", "lat": 38.7154, "lng": -9.1340},
           {"id": "c", "lat": 38.7110, "lng": -9.1445}, {"id": "d", "lat": 38.6975, "lng": -9.2032}]
    for g in cluster(pts, 1.5):
        print("area:", [p["id"] for p in g])
    r = order_route(pts[:3])
    print("route:", [p["id"] for p in r], walk_minutes(r), "min walk")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
