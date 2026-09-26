#!/usr/bin/env python3
"""
geocode.py — offline, build-time city geocoding for Second Brain Link.

Resolves the free-text locations platform exports carry ("London, England,
United Kingdom", "Dubai", "San Francisco Bay Area") to lat/lng using the
bundled GeoNames-derived gazetteer (engine/mappings/geo/cities.json — CC-BY,
see engine/references/geonames-attribution.md). ZERO network calls — this is
a dictionary lookup, keeping the engine's local-first promise intact.

Precision-biased, same doctrine as entity resolution: a wrong pin is worse
than a missing pin. Resolution order:
  1. city + country match (unique within the country → resolve)
  2. city + admin/region match ("Portland, Oregon")
  3. city alone — only if unambiguous: a single candidate, or one candidate
     ≥10× the population of the runner-up (i.e. THE London, not London Ohio)
Anything still ambiguous returns None; the note simply gets no coordinates.

Used by build_vault.py to stamp lat/lng frontmatter on identity/people/org
notes whose source carried a location string. Places notes already carry real
coordinates from their exports and never pass through here.
"""
import json
import re
from pathlib import Path

_GAZ_PATH = Path(__file__).resolve().parent.parent / "mappings" / "geo" / "cities.json"

_gaz = None            # lazy: {nk(city): [(name, cc, admin, lat, lng, pop), …]}
_country_of = None     # {nk(country name/iso2/iso3): cc}

# noise words LinkedIn-style locations wrap around the city name
_NOISE = re.compile(
    r"\b(greater|metropolitan|metro|area|region|bay area|city|county|district)\b", re.I)

# everyday names → the GeoNames headword (kept tiny and unambiguous on purpose)
_ALIASES = {"newyork": "newyorkcity", "nyc": "newyorkcity", "sf": "sanfrancisco",
            "washingtondc": "washington"}


def _nk(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _load():
    global _gaz, _country_of
    if _gaz is not None:
        return bool(_gaz)
    _gaz, _country_of = {}, {}
    try:
        data = json.loads(_GAZ_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    for cc, names in (data.get("countries") or {}).items():
        for n in names:
            _country_of[_nk(n)] = cc
    for row in data.get("cities") or []:
        name, cc, admin, lat, lng, pop = row
        _gaz.setdefault(_nk(name), []).append((name, cc, admin, lat, lng, pop))
    return bool(_gaz)


def _pick(cands):
    """Resolve a candidate list only when unambiguous (or one dominates 10×)."""
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    ranked = sorted(cands, key=lambda c: -c[5])
    if ranked[0][5] >= 10 * max(ranked[1][5], 1):
        return ranked[0]
    return None


def resolve(location):
    """Resolve a free-text location to (lat, lng) or None. Offline, precision-
    biased; see module docstring for the resolution ladder."""
    if not location or not _load():
        return None
    txt = _NOISE.sub(" ", str(location))
    parts = [p.strip() for p in re.split(r"[,/;·|]", txt) if p.strip()]
    if not parts:
        return None

    # find a country anywhere in the trailing tokens
    cc = None
    for p in reversed(parts[1:]) or []:
        cc = _country_of.get(_nk(p))
        if cc:
            break

    # candidate city tokens: try each comma part as the city (first parts first)
    for city in parts:
        ck = _nk(city)
        cands = _gaz.get(_ALIASES.get(ck, ck))
        if not cands:
            continue
        if cc:
            hit = _pick([c for c in cands if c[1] == cc])
            if hit:
                return (hit[3], hit[4])
            continue  # a country was named but this city isn't in it → next token
        # no country given: try an admin/region qualifier from the other tokens
        admins = {_nk(p) for p in parts if p != city}
        if admins:
            hit = _pick([c for c in cands if _nk(c[2]) in admins])
            if hit:
                return (hit[3], hit[4])
        hit = _pick(cands)
        if hit:
            return (hit[3], hit[4])
    return None


# ---- reverse lookup: coordinates → (city, country) --------------------------
# Used by build_vault.places() to stamp `city:`/`country:` on place notes, which
# carry real coordinates but no city field. Same precision bias: a pin with no
# gazetteer city within `max_km` gets none rather than a wrong one.
_grid = None           # {(int lat, int lng): [(name, cc, lat, lng, pop), …]}


def _load_grid():
    global _grid
    if _grid is not None:
        return bool(_grid)
    _grid = {}
    if not _load():
        return False
    for cands in _gaz.values():
        for name, cc, _admin, lat, lng, pop in cands:
            _grid.setdefault((int(lat // 1), int(lng // 1)), []).append((name, cc, lat, lng, pop))
    return bool(_grid)


def _km(a_lat, a_lng, b_lat, b_lng):
    import math
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def nearest(lat, lng, max_km=30.0):
    """(city, iso2 country UPPER) of the gazetteer city nearest (lat, lng), or None
    beyond `max_km`. A metropolis (≥1M people) within 25 km wins over its own wards and
    suburbs — a pin in Asakusa is in Tokyo, not Taitō; otherwise, among cities within a
    quarter of the nearest distance + 5 km, the most populous wins."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not _load_grid():
        return None
    gy, gx = int(lat // 1), int(lng // 1)
    found = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            for name, cc, clat, clng, pop in _grid.get((gy + dy, gx + dx), ()):
                d = _km(lat, lng, clat, clng)
                if d <= max_km:
                    found.append((d, -pop, name, cc))
    if not found:
        return None
    metro = [f for f in found if f[0] <= 25 and -f[1] >= 1000000]
    if metro:
        _d, _p, name, cc = min(metro)
        return name, cc.upper()
    # a dominant city (≥10× the nearest's population, ≥100k) within 15 km wins too —
    # a pin in Marvila is in Lisbon
    near0 = min(found)
    dom = [f for f in found if f[0] <= 15 and -f[1] >= max(100000, 10 * -near0[1])]
    if dom:
        _d, _p, name, cc = min(dom, key=lambda f: (f[1], f[0]))
        return name, cc.upper()
    best = near0[0]
    close = [f for f in found if f[0] <= best * 1.25 + 5]
    _d, _p, name, cc = min(close, key=lambda f: (f[1], f[0]))
    return name, cc.upper()


def country_code(name):
    """ISO-2 (UPPER) for a country name / iso2 / iso3, from the bundled gazetteer,
    or '' when unknown."""
    if not name or not _load():
        return ""
    return (_country_of.get(_nk(name)) or "").upper()
