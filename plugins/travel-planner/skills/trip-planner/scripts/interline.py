#!/usr/bin/env python3
"""
interline.py - virtual interlining: combine separately-sold tickets into one journey, and
turn a long connection into a city worth a night.

No online travel agency will sell you DXB->ICN on one airline and ICN->HND on another as one
trip, with a night in Seoul in between. This does - honestly. It reads fares the
flight-search skill captured (each fare = one ticket covering one or more flights), chains
them origin -> destination, scores each journey on price, time and self-transfer risk, and
can write the chosen one into itinerary.json.

**Self-transfer moves the risk onto the traveller.** Separate tickets mean bags are not
through-checked, the second carrier owes nothing when the first is late, a missed connection
is paid for twice, and changing planes landside means entering the country. So:

  1. A separate-ticket connection shorter than the airport's self-transfer minimum
     (references/airports.json `mct_self`) is REFUSED - never emitted, not merely warned.
  2. Every self-transfer leg carries the risk sentence, which render_brain.py prints where the
     user reads, and the map draws the leg dashed.
  3. Visa: this script knows no visa rules and never claims one is unnecessary. A landside
     transfer into a country the traveller has not listed under `visa_ok:` in traveler.md is
     flagged "entry required - check".

Input (`--fares`): a JSON list of fares, as flight-search writes them:
    {"id": "f1", "provider": "carrier site", "price": 410, "currency": "EUR",
     "quoted_at": "<iso>", "source_url": "https://...",
     "segments": [{"carrier": "EK", "number": "EK322", "from": "DXB", "to": "ICN",
                   "dep": "YYYY-MM-DDTHH:MM", "arr": "YYYY-MM-DDTHH:MM", "cabin": "Y"}]}

    python3 interline.py --fares fares.json --from DXB --to HND            # ranked journeys
    python3 interline.py --fares fares.json --from DXB --to HND --json
    python3 interline.py --fares fares.json --from DXB --to HND --pick 1 --trip <trip_id>
    python3 interline.py --explain-risk                                    # the rules, in words
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import itinerary as itin  # noqa: E402
from paths import profile_dir  # noqa: E402

STOPOVER_MIN_H = 10          # a connection at least this long, spanning a night, becomes a stop
MAX_TICKETS = 3
AIRPORT_CHANGE_MIN = 120     # extra minutes to cross a city between two airports
HOUR_VALUE = 15.0            # currency units per hour of journey time, for ranking only


def _t(s):
    return datetime.datetime.fromisoformat(str(s)[:16])


def _mct(code):
    a = itin.airports()
    rec = a.get(str(code).upper()) or {}
    return int(rec.get("mct_self") or (a.get("_default") or {}).get("mct_self") or 180)


def _city(code):
    code = str(code or "").upper()
    metro = (itin.airports().get("_metro") or {}).get(code)
    if isinstance(metro, list):
        return metro[0], metro[1]
    a = itin.airport(code)
    return (a or {}).get("city", ""), (a or {}).get("country", "")


def traveler_visa_ok(path=None):
    """Countries the traveller has confirmed they may enter (traveler.md `visa_ok:`), plus
    their citizenships. Nothing is ever assumed beyond what the file says."""
    p = pathlib.Path(path) if path else profile_dir() / "traveler.md"
    ok = set()
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return ok
    for key in ("visa_ok", "citizenships"):
        m = re.search(rf"^{key}:\s*\[(.*?)\]\s*$", text, re.M)
        if m:
            ok |= {x.strip().strip('"\'').upper() for x in m.group(1).split(",") if x.strip()}
        for mm in re.finditer(rf"^{key}:\s*\n((?:\s+-\s*.+\n?)+)", text, re.M):
            ok |= {x.strip().strip('"\'').upper() for x in re.findall(r"-\s*(.+)", mm.group(1))}
    return ok


def _fare_ends(f):
    segs = f["segments"]
    return segs[0]["from"].upper(), segs[-1]["to"].upper(), _t(segs[0]["dep"]), _t(segs[-1]["arr"])


def connection(a, b, visa_ok):
    """Assess the self-transfer between fare `a` and fare `b`. Returns a dict, or None when
    the connection is impossible or below the minimum (refused)."""
    _, a_to, _, a_arr = _fare_ends(a)
    b_from, _, b_dep, _ = _fare_ends(b)
    same_airport = a_to == b_from
    ca, cb = _city(a_to), _city(b_from)
    if not same_airport and (not ca[0] or ca != cb):
        return None
    minutes = int((b_dep - a_arr).total_seconds() // 60)
    need = max(_mct(a_to), _mct(b_from)) + (0 if same_airport else AIRPORT_CHANGE_MIN)
    if minutes < need:
        return None                                   # REFUSED: below the self-transfer floor
    why = ["separate tickets", "bags not through-checked — collect and re-check",
           "no protection if the first flight is late", "a missed connection is paid for twice"]
    level = "medium"
    if not same_airport:
        why.append(f"airport change {a_to}→{b_from}")
        level = "high"
    country = ca[1]
    if country and country.upper() not in visa_ok:
        why.append(f"entry to {country} required — check visa rules for your passport")
        level = "high"
    if minutes < need * 1.5:
        why.append(f"tight: {minutes} min against a {need} min floor")
        level = "high"
    return {"at": a_to, "to_airport": b_from, "minutes": minutes, "floor": need,
            "city": ca[0], "country": country, "level": level, "why": why,
            "stopover": minutes >= STOPOVER_MIN_H * 60 and b_dep.date() > a_arr.date()}


def journeys(fares, origin, dest, visa_ok=None, max_tickets=MAX_TICKETS):
    """Every chain of fares origin -> dest, best first."""
    visa_ok = visa_ok or set()
    origin, dest = origin.upper(), dest.upper()
    same_city = lambda x, y: x == y or (_city(x)[0] and _city(x) == _city(y))  # noqa: E731
    fares = [f for f in fares if f.get("segments")]
    for f in fares:
        for s in f["segments"]:
            s["from"], s["to"] = s["from"].upper(), s["to"].upper()
    out = []

    def extend(chain, conns):
        last = chain[-1]
        _, to, _, _ = _fare_ends(last)
        if same_city(to, dest):
            out.append((list(chain), list(conns)))
            return
        if len(chain) >= max_tickets:
            return
        for f in fares:
            if f in chain:
                continue
            c = connection(last, f, visa_ok)
            if c:
                extend(chain + [f], conns + [c])

    for f in fares:
        fr, _, _, _ = _fare_ends(f)
        if same_city(fr, origin):
            extend([f], [])
    ranked = []
    for chain, conns in out:
        price = sum(float(f.get("price") or 0) for f in chain)
        dep, arr = _fare_ends(chain[0])[2], _fare_ends(chain[-1])[3]
        hours = (arr - dep).total_seconds() / 3600
        # a stopover night is time well spent, not dead time: don't charge it as travel time
        stop_h = sum(c["minutes"] / 60 for c in conns if c["stopover"])
        risk = sum({"medium": 60, "high": 180}.get(c["level"], 0) for c in conns)
        score = price + HOUR_VALUE * max(0.0, hours - stop_h) + risk
        ranked.append({"fares": chain, "connections": conns, "price": round(price, 2),
                       "currency": chain[0].get("currency", ""), "hours": round(hours, 1),
                       "self_transfer": bool(conns), "score": round(score, 1),
                       "stopovers": [c["city"] for c in conns if c["stopover"]]})
    ranked.sort(key=lambda j: (j["score"], j["price"]))
    return ranked


def describe(j, i):
    route = " + ".join(f"{s['from']}→{s['to']} {s.get('carrier', '')}{s.get('number', '')[len(s.get('carrier', '')):]}"
                       for f in j["fares"] for s in f["segments"])
    head = f"#{i} {j['currency']} {j['price']:g} · {j['hours']}h · {len(j['fares'])} ticket(s) · {route}"
    lines = [head]
    for c in j["connections"]:
        tag = "STOPOVER NIGHT in " + c["city"] if c["stopover"] else f"self-transfer at {c['at']}"
        lines.append(f"    {tag}: {c['minutes'] // 60}h{c['minutes'] % 60:02d} "
                     f"(floor {c['floor']} min) · risk {c['level']} — {' · '.join(c['why'])}")
    for f in j["fares"]:
        lines.append(f"    ticket {f.get('id')}: {f.get('provider', '?')} {f.get('currency', '')} "
                     f"{f.get('price')} quoted {f.get('quoted_at')} {f.get('source_url', '')}")
    return "\n".join(lines)


def write_to_itinerary(j, trip_id, origin, dest, dest_root=None):
    """The chosen journey -> legs, plus a `stopover` stop for each overnight connection.

    A leg runs until a stopover city (or the destination). Separate tickets joined inside
    one leg make it a self-transfer leg carrying that connection's risk; the leg that
    LEAVES a stopover is a self-transfer too - its tickets were bought apart - and points
    at the stop through `stopover_stop`, which is how the map knows to dash it."""
    it = itin.load(trip_id, dest_root)
    for f in j["fares"]:
        if not f.get("quoted_at"):
            raise itin.ItineraryError(f"fare {f.get('id')} has no quoted_at - re-capture it")
    worst = {"medium": 1, "high": 2}
    leg = {"from": origin.upper(), "segments": [], "tickets": [], "conns": [], "stopover": None}

    def close(to_code):
        conns = leg["conns"] + ([leg["stopover"][1]] if leg["stopover"] else [])
        out = {"from": leg["from"], "to": to_code, "mode": "flight",
               "segments": leg["segments"], "tickets": leg["tickets"],
               "self_transfer": bool(conns)}
        if leg["conns"]:
            out["connection_minutes"] = min(c["minutes"] for c in leg["conns"])
        if conns:
            top = max(conns, key=lambda c: worst.get(c["level"], 0))
            why = []
            for c in conns:
                why += [w for w in c["why"] if w not in why]
            out["risk"] = {"level": top["level"], "why": " · ".join(why)}
        if leg["stopover"]:
            out["stopover_stop"] = leg["stopover"][0]
        itin.add_leg(it, out)

    for k, f in enumerate(j["fares"]):
        tid = f.get("id") or f"t{k + 1}"
        seg_ids = []
        for n, s in enumerate(f["segments"]):
            sid = f"{tid}-s{n + 1}"
            seg_ids.append(sid)
            leg["segments"].append({"id": sid, "carrier": s.get("carrier", ""),
                                    "number": s.get("number", ""), "from": s["from"], "to": s["to"],
                                    "dep": s["dep"], "arr": s["arr"], "cabin": s.get("cabin", ""),
                                    "ticket": tid})
        leg["tickets"].append({"id": tid, "provider": f.get("provider", ""), "covers": seg_ids,
                               "price": f.get("price"), "currency": f.get("currency", ""),
                               "quoted_at": f.get("quoted_at"), "source_url": f.get("source_url", "")})
        conn = j["connections"][k] if k < len(j["connections"]) else None
        if not conn:
            continue
        if not conn["stopover"]:
            leg["conns"].append(conn)
            continue
        arr = _fare_ends(f)[3].date()
        nights = (_fare_ends(j["fares"][k + 1])[2].date() - arr).days
        # the stop sits in the CITY (your pins there, else the gazetteer), not at the
        # airport an hour out of town - the airport is only the last resort
        a = itin.airport(conn["at"]) or {}
        city = conn["city"] or conn["at"]
        bp = [r for r in itin._brain_places() if (r.get("city") or "").lower() == city.lower()]
        c = itin.geo.centroid(bp) if bp else itin._city_centre(city, conn["country"])
        lat, lng = c if c else (a.get("lat"), a.get("lng"))
        stop = itin.add_stop(it, city, arr.isoformat(), nights,
                             role="stopover", country=conn["country"], lat=lat, lng=lng,
                             why=f"{conn['minutes'] // 60}h between tickets — a night in "
                                 f"{conn['city']} instead of an airport")
        close(conn["at"])
        leg = {"from": conn["to_airport"], "segments": [], "tickets": [], "conns": [],
               "stopover": (stop["id"], conn)}
    close(dest.upper())
    if it.get("status") == "draft":
        it["status"] = "shopped"
    itin.save(it, dest_root)
    return it


RISK_TEXT = """Self-transfer (virtual interlining) — what the traveller carries:
  - bags are not through-checked: collect and re-check at every self-transfer
  - no protection when the first flight is late: the second carrier owes nothing
  - a missed connection is paid for twice: the lost ticket and the replacement
  - a landside transfer means entering the country: a visa or transit rule may apply
Enforced: connections below references/airports.json `mct_self` (plus 120 min for an
airport change) are refused, never offered. Every self-transfer leg carries these words in
the trip note and is drawn dashed on the map."""


def main():
    ap = argparse.ArgumentParser(description="virtual interlining with honest risk")
    ap.add_argument("--fares")
    ap.add_argument("--from", dest="origin")
    ap.add_argument("--to", dest="dest")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--pick", type=int, help="1-based journey to write into --trip")
    ap.add_argument("--trip")
    ap.add_argument("--traveler", help="path to traveler.md (default: the profile)")
    ap.add_argument("--explain-risk", action="store_true")
    ap.add_argument("--dest-root", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.explain_risk:
        print(RISK_TEXT)
        return 0
    if not (a.fares and a.origin and a.dest):
        ap.error("--fares, --from and --to are required")
    fares = json.loads(pathlib.Path(a.fares).read_text(encoding="utf-8"))
    if isinstance(fares, dict) and isinstance(fares.get("options"), list):
        fares = fares["options"]           # a quotes.py set (sbl-quotes/1) — same fare shape
        for f in fares:
            f.setdefault("source_url", f.get("url", ""))
    js = journeys(fares, a.origin, a.dest, traveler_visa_ok(a.traveler))
    if a.pick:
        if not a.trip:
            ap.error("--pick needs --trip")
        if not 1 <= a.pick <= len(js):
            print(f"no journey #{a.pick} ({len(js)} found)", file=sys.stderr)
            return 2
        it = write_to_itinerary(js[a.pick - 1], a.trip, a.origin, a.dest, a.dest_root)
        print(itin.summary(it))
        return 0
    if a.json:
        print(json.dumps(js[:a.top], ensure_ascii=False, indent=1))
        return 0
    if not js:
        print("no journey found — none of the fares chain origin→destination above the "
              "self-transfer floor", file=sys.stderr)
        return 1
    for i, j in enumerate(js[:a.top], 1):
        print(describe(j, i))
    return 0


if __name__ == "__main__":
    sys.exit(main())
