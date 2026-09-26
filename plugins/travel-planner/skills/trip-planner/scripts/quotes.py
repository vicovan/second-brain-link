#!/usr/bin/env python3
"""
quotes.py - real flight and stay options, as the user would see them on the sites.

The shopping skills read live prices in the user's own browser (Google Flights, Skyscanner,
Kayak, carriers; Google Hotels, Booking.com, Agoda, Airbnb). A QUOTE SET is one search's
results, kept as a file so Studio can show them as a familiar list - a flights list, a
hotels list - drawn from exactly what was recorded rather than retyped:

    <travel layer>/quotes/<quote_id>.json      (schema "sbl-quotes/1")

and render_brain.py turns each set into a note with the same list as a table.

No trip is needed ("what does Dubai → Iași cost on 12 October?"); with `--trip` a set
belongs to one, and `pick` writes the chosen option into its itinerary.

The honesty rules are itinerary.py's, applied to a price list:

  - Every price has `quoted_at` (when it was read) and `url` (where). No exceptions: a price
    without both is refused. A price is a snapshot, never a promise.
  - Nothing is invented: every field is what the page showed. Unknown stays absent.
  - Nothing is held or booked. `pick` records a choice; the user books through the link.

    quotes.py new flights --id dxb-ias-oct12 --title "Dubai → Iași · 12 Oct" \\
        --from DXB --to IAS --date YYYY-MM-DD [--return YYYY-MM-DD] [--adults 1] [--trip <id>]
    quotes.py new stays --id iasi-oct --title "Iași · 12–19 Oct" --city "Iasi" \\
        --checkin YYYY-MM-DD --checkout YYYY-MM-DD [--guests 2] [--trip <id> --stop s1]
    quotes.py add <quote_id> --json '<one option>'  |  --file options.json   (a list)
    quotes.py show <quote_id>          a text table
    quotes.py fence <quote_id>         the one line to end a Studio reply with
    quotes.py pick <quote_id> <option_id> [--trip <id>] [--stop s1]
    quotes.py list

A flight option (one ticket, or one combined self-transfer result as the site sold it):
    {"provider": "Google Flights", "url": "...", "price": 412, "currency": "EUR",
     "quoted_at": "YYYY-MM-DDT14:05", "bags": "carry-on only", "self_transfer": false,
     "segments": [{"carrier": "TK", "carrier_name": "Turkish Airlines", "number": "TK 873",
                   "from": "DXB", "to": "IST", "dep": "YYYY-MM-DDT07:40", "arr": "YYYY-MM-DDT11:35"}, ...]}
A stay option:
    {"provider": "Booking.com", "url": "...", "name": "Hotel X", "price_total": 540,
     "currency": "EUR", "quoted_at": "...", "stars": 4, "rating": 8.9, "rating_scale": 10,
     "reviews": 1234, "area": "Copou", "lat": 47.17, "lng": 27.57,
     "free_cancellation": true, "breakfast": true, "room": "Double room"}
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import itinerary as itin  # noqa: E402
from paths import render_dir, TRIP_ID_RE  # noqa: E402

SCHEMA = "sbl-quotes/1"
KINDS = ("flights", "stays")
IATA = re.compile(r"^[A-Z]{3}$")
MAX_OPTIONS = 40


class QuoteError(ValueError):
    pass


def quotes_dir(dest=None):
    return render_dir(dest) / "quotes"


def quote_path(qid, dest=None):
    if not TRIP_ID_RE.match(qid or ""):
        raise QuoteError(f"bad quote id {qid!r}: lowercase letters, digits and hyphens only")
    return quotes_dir(dest) / f"{qid}.json"


def load(qid, dest=None):
    try:
        return json.loads(quote_path(qid, dest).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise QuoteError(f"no quote set {qid!r}")


def list_sets(dest=None):
    d = quotes_dir(dest)
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def save(q, dest=None):
    q["updated"] = itin.now_iso()
    itin._atomic_write(quote_path(q["id"], dest), json.dumps(q, ensure_ascii=False, indent=1) + "\n")
    return quote_path(q["id"], dest)


def _date(s, what):
    try:
        return datetime.date.fromisoformat(str(s)[:10]).isoformat()
    except ValueError:
        raise QuoteError(f"{what} must be YYYY-MM-DD, got {s!r}")


def _dt(s, what):
    try:
        return datetime.datetime.fromisoformat(str(s)[:16])
    except ValueError:
        raise QuoteError(f"{what} must be an ISO local time like YYYY-MM-DDT07:40, got {s!r}")


# ---------------------------------------------------------------- new
def new(kind, qid, title, dest=None, **q):
    if kind not in KINDS:
        raise QuoteError(f"kind must be one of {KINDS}")
    if quote_path(qid, dest).exists():
        raise QuoteError(f"quote set {qid!r} exists - add to it, or pick another id")
    s = {"schema": SCHEMA, "id": qid, "kind": kind, "title": title.strip(), "created": itin.now_iso(),
         "updated": "", "query": {}, "options": []}
    if q.get("trip"):
        if not TRIP_ID_RE.match(q["trip"]):
            raise QuoteError(f"bad trip id {q['trip']!r}")
        s["trip"] = q["trip"]
        if q.get("stop"):
            s["stop"] = q["stop"]
    if kind == "flights":
        f, t = (q.get("origin") or "").upper(), (q.get("to") or "").upper()
        if not (IATA.match(f) and IATA.match(t)):
            raise QuoteError("flights need --from and --to as 3-letter IATA codes")
        s["query"] = {"from": f, "to": t, "date": _date(q.get("date"), "--date"), "adults": int(q.get("adults") or 1)}
        if q.get("ret"):
            s["query"]["return"] = _date(q["ret"], "--return")
    else:
        ci, co = _date(q.get("checkin"), "--checkin"), _date(q.get("checkout"), "--checkout")
        nights = (datetime.date.fromisoformat(co) - datetime.date.fromisoformat(ci)).days
        if nights < 1:
            raise QuoteError("--checkout must be after --checkin")
        if not (q.get("city") or "").strip():
            raise QuoteError("stays need --city")
        s["query"] = {"city": q["city"].strip(), "checkin": ci, "checkout": co, "nights": nights,
                      "guests": int(q.get("guests") or 1)}
    return s


# ---------------------------------------------------------------- options
def _num(v, what, allow_none=True):
    if v in (None, "") and allow_none:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise QuoteError(f"{what} must be a number, got {v!r}")


def _common(o, n):
    url = str(o.get("url") or "").strip()
    if not re.match(r"^https?://", url):
        raise QuoteError(f"option {n}: `url` (the page the price was read on) is required")
    qa = str(o.get("quoted_at") or "").strip()
    if not qa:
        raise QuoteError(f"option {n}: `quoted_at` is required - when was this price seen?")
    _dt(qa, f"option {n}: quoted_at")
    cur = str(o.get("currency") or "").strip().upper()
    if not re.match(r"^[A-Z]{3}$", cur):
        raise QuoteError(f"option {n}: `currency` must be a 3-letter code as shown (EUR, USD, AED...)")
    return {"provider": str(o.get("provider") or "").strip() or "site", "url": url,
            "quoted_at": qa[:16], "currency": cur}


def flight_option(o, n):
    out = _common(o, n)
    price = _num(o.get("price"), f"option {n}: price", allow_none=False)
    if price <= 0:
        raise QuoteError(f"option {n}: price must be positive")
    segs = []
    for k, sg in enumerate(o.get("segments") or []):
        fr, to = str(sg.get("from") or "").upper(), str(sg.get("to") or "").upper()
        if not (IATA.match(fr) and IATA.match(to)):
            raise QuoteError(f"option {n} segment {k + 1}: from/to must be IATA codes")
        dep, arr = _dt(sg.get("dep"), f"option {n} segment {k + 1}: dep"), _dt(sg.get("arr"), f"option {n} segment {k + 1}: arr")
        seg = {"from": fr, "to": to, "dep": dep.isoformat()[:16], "arr": arr.isoformat()[:16],
               "carrier": str(sg.get("carrier") or "").upper()[:3],
               "carrier_name": str(sg.get("carrier_name") or ""), "number": str(sg.get("number") or "")}
        if sg.get("duration_min"):
            seg["duration_min"] = int(sg["duration_min"])
        segs.append(seg)
    if not segs:
        raise QuoteError(f"option {n}: at least one segment (from, to, dep, arr, carrier)")
    for a, b in zip(segs, segs[1:]):
        if a["to"] != b["from"] and not o.get("self_transfer"):
            raise QuoteError(f"option {n}: {a['to']} → {b['from']} is an airport change - mark it "
                             "self_transfer, or record the tickets separately")
    out.update({"price": price, "segments": segs, "stops": len(segs) - 1,
                "self_transfer": bool(o.get("self_transfer")),
                "from": segs[0]["from"], "to": segs[-1]["to"],
                "dep": segs[0]["dep"], "arr": segs[-1]["arr"]})
    # total time: the site's own number when given (it knows the time zones), else none -
    # local times in two zones cannot be subtracted honestly
    if o.get("total_min"):
        out["total_min"] = int(o["total_min"])
    layovers = []
    for a, b in zip(segs, segs[1:]):
        try:
            mins = int((datetime.datetime.fromisoformat(b["dep"]) - datetime.datetime.fromisoformat(a["arr"])).total_seconds() // 60)
        except ValueError:
            mins = None
        layovers.append({"at": a["to"], "min": mins})       # same airport: same zone - safe
    if layovers:
        out["layovers"] = layovers
    for k in ("bags", "cabin", "note", "emissions"):
        if o.get(k):
            out[k] = str(o[k])[:160]
    if o.get("return_segments"):
        out["return_segments"] = flight_option({**o, "segments": o["return_segments"], "return_segments": None}, n)["segments"]
    return out


def stay_option(o, n, query):
    out = _common(o, n)
    name = str(o.get("name") or "").strip()
    if not name:
        raise QuoteError(f"option {n}: `name` is required")
    total = _num(o.get("price_total"), f"option {n}: price_total")
    night = _num(o.get("price_night"), f"option {n}: price_night")
    if total is None and night is None:
        raise QuoteError(f"option {n}: price_total or price_night, as the page showed it")
    nights = int(query.get("nights") or 1)
    out.update({"name": name,
                "price_total": round(total if total is not None else night * nights, 2),
                "price_night": round(night if night is not None else total / nights, 2),
                "price_basis": "total" if total is not None else "per night × nights"})
    for k, lim in (("stars", 5), ("rating", 10), ("rating_scale", 10)):
        v = _num(o.get(k), f"option {n}: {k}")
        if v is not None:
            out[k] = v
    if o.get("reviews") not in (None, ""):
        out["reviews"] = int(_num(o.get("reviews"), f"option {n}: reviews"))
    if o.get("lat") not in (None, "") and o.get("lng") not in (None, ""):
        pt = {"lat": float(o["lat"]), "lng": float(o["lng"])}
        if geo.has_coords(pt):
            out.update(pt)
    for k in ("area", "room", "note", "taxes"):
        if o.get(k):
            out[k] = str(o[k])[:160]
    for k in ("free_cancellation", "breakfast"):
        if k in o and o[k] is not None:
            out[k] = bool(o[k])
    return out


def add(q, options):
    if isinstance(options, dict):
        options = [options]
    added = []
    for o in options:
        if len(q["options"]) >= MAX_OPTIONS:
            raise QuoteError(f"a quote set holds at most {MAX_OPTIONS} options")
        n = len(q["options"]) + 1
        opt = flight_option(o, n) if q["kind"] == "flights" else stay_option(o, n, q["query"])
        opt["id"] = ("f" if q["kind"] == "flights" else "h") + str(n)
        q["options"].append(opt)
        added.append(opt)
    rank(q)
    return added


def rank(q):
    """Tags a traveller recognises: cheapest, fastest (flights), best value (stays)."""
    opts = q["options"]
    for o in opts:
        o.pop("tags", None)
    if not opts:
        return
    if q["kind"] == "flights":
        cheap = min(opts, key=lambda o: o["price"])
        cheap.setdefault("tags", []).append("Cheapest")
        timed = [o for o in opts if o.get("total_min")]
        if timed:
            fast = min(timed, key=lambda o: o["total_min"])
            fast.setdefault("tags", []).append("Fastest")
        direct = [o for o in opts if o["stops"] == 0]
        if direct and min(direct, key=lambda o: o["price"]) is not cheap:
            min(direct, key=lambda o: o["price"]).setdefault("tags", []).append("Cheapest direct")
    else:
        cheap = min(opts, key=lambda o: o["price_total"])
        cheap.setdefault("tags", []).append("Cheapest")
        rated = [o for o in opts if o.get("rating")]
        if rated:
            best = max(rated, key=lambda o: o["rating"] / (o.get("rating_scale") or 10))
            best.setdefault("tags", []).append("Top rated")


# ---------------------------------------------------------------- output
def hm(mins):
    if mins in (None, ""):
        return ""
    return f"{int(mins) // 60}h {int(mins) % 60:02d}m"


def hhmm(iso):
    return str(iso)[11:16]


def plus_days(dep, arr):
    try:
        d = (datetime.date.fromisoformat(arr[:10]) - datetime.date.fromisoformat(dep[:10])).days
    except ValueError:
        return ""
    return f"+{d}" if d > 0 else ""


def money(v, cur):
    return f"{cur} {v:,.0f}"


def show(q):
    out = [f"{q['title']} ({q['id']}) — {len(q['options'])} option(s)"]
    for o in q["options"]:
        tags = f" [{', '.join(o['tags'])}]" if o.get("tags") else ""
        if q["kind"] == "flights":
            airl = " + ".join(dict.fromkeys(s["carrier_name"] or s["carrier"] for s in o["segments"]))
            stops = "direct" if o["stops"] == 0 else f"{o['stops']} stop" + ("s" if o["stops"] > 1 else "") + \
                " (" + ", ".join(l["at"] + (f" {hm(l['min'])}" if l.get("min") is not None else "") for l in o.get("layovers", [])) + ")"
            out.append(f"  {o['id']} {hhmm(o['dep'])}–{hhmm(o['arr'])}{plus_days(o['dep'], o['arr'])} "
                       f"{o['from']}–{o['to']} · {airl} · {hm(o.get('total_min')) or '?'} · {stops} · "
                       f"{money(o['price'], o['currency'])} · seen {o['quoted_at'].replace('T', ' ')} · {o['provider']}{tags}")
        else:
            r = f" · {o['rating']:g}/{o.get('rating_scale', 10):g}" + (f" ({o['reviews']:,})" if o.get("reviews") else "") if o.get("rating") else ""
            out.append(f"  {o['id']} {o['name']}{' ' + '★' * int(o['stars']) if o.get('stars') else ''}{r}"
                       f"{' · ' + o['area'] if o.get('area') else ''} · {money(o['price_total'], o['currency'])} total "
                       f"({money(o['price_night'], o['currency'])}/night) · seen {o['quoted_at'].replace('T', ' ')} · {o['provider']}{tags}")
    return "\n".join(out)


def fence(q):
    return "```" + q["kind"] + "\n" + json.dumps({"quotes": q["id"]}) + "\n```"


# ---------------------------------------------------------------- pick
def pick(q, opt_id, trip=None, stop=None, dest=None):
    o = next((x for x in q["options"] if x["id"] == opt_id), None)
    if not o:
        raise QuoteError(f"no option {opt_id!r} in {q['id']}")
    q["picked"] = opt_id
    trip = trip or q.get("trip")
    if not trip:
        return None                        # a choice with no trip is recorded on the set only
    it = itin.load(trip, dest)
    if q["kind"] == "stays":
        stop = stop or q.get("stop")
        if not stop:
            raise QuoteError("pick a stay into a trip needs --stop")
        itin.set_stay(it, stop, o["name"], o["url"], o["price_total"], o["quoted_at"], "candidate",
                      o.get("lat"), o.get("lng"), o["provider"])
    else:
        leg = {"mode": "flight", "from": o["from"], "to": o["to"], "segments": o["segments"],
               "tickets": [{"provider": o["provider"], "price": o["price"], "currency": o["currency"],
                            "quoted_at": o["quoted_at"], "source_url": o["url"]}],
               "self_transfer": o["self_transfer"], "quote": f"{q['id']}:{opt_id}"}
        if o["self_transfer"]:
            import interline
            leg["risk"] = {"level": "high", "why": interline.RISK_TEXT}
        itin.add_leg(it, leg)
    itin.save(it, dest)
    return it


# ---------------------------------------------------------------- cli
def main(argv=None):
    ap = argparse.ArgumentParser(description="real flight and stay options, as a familiar list")
    ap.add_argument("--dest", help="render dir override (tests)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new"); s.add_argument("kind", choices=KINDS)
    s.add_argument("--id", required=True); s.add_argument("--title", required=True)
    s.add_argument("--from", dest="origin"); s.add_argument("--to"); s.add_argument("--date")
    s.add_argument("--return", dest="ret"); s.add_argument("--adults", type=int, default=1)
    s.add_argument("--city"); s.add_argument("--checkin"); s.add_argument("--checkout")
    s.add_argument("--guests", type=int, default=1); s.add_argument("--trip"); s.add_argument("--stop")
    s = sub.add_parser("add"); s.add_argument("quote"); s.add_argument("--json"); s.add_argument("--file")
    for name in ("show", "fence"):
        s = sub.add_parser(name); s.add_argument("quote")
    s = sub.add_parser("pick"); s.add_argument("quote"); s.add_argument("option")
    s.add_argument("--trip"); s.add_argument("--stop")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            for qid in list_sets(a.dest):
                q = load(qid, a.dest)
                print(f"  {qid} [{q['kind']}] {q['title']} — {len(q['options'])} option(s)")
            return 0
        if a.cmd == "new":
            q = new(a.kind, a.id, a.title, a.dest, origin=a.origin, to=a.to, date=a.date, ret=a.ret,
                    adults=a.adults, city=a.city, checkin=a.checkin, checkout=a.checkout,
                    guests=a.guests, trip=a.trip, stop=a.stop)
            save(q, a.dest)
            print(f"{a.id} [{a.kind}] {q['query']}")
            return 0
        q = load(a.quote, a.dest)
        if a.cmd == "show":
            print(show(q))
            return 0
        if a.cmd == "fence":
            print(fence(q))
            return 0
        if a.cmd == "add":
            if a.file:
                data = json.loads(pathlib.Path(a.file).read_text(encoding="utf-8"))
            elif a.json and a.json != "-":
                data = json.loads(a.json)
            else:
                data = json.load(sys.stdin)
            got = add(q, data)
            save(q, a.dest)
            for o in got:
                print(f"{o['id']} recorded — {o.get('name') or o['from'] + '–' + o['to']}")
            print(f"end the reply with:\n{fence(q)}")
            return 0
        if a.cmd == "pick":
            it = pick(q, a.option, a.trip, a.stop, a.dest)
            save(q, a.dest)
            print(f"{a.option} picked" + (f" → {it['trip_id']}" if it else " (no trip - recorded on the set)"))
            return 0
    except (QuoteError, itin.ItineraryError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
