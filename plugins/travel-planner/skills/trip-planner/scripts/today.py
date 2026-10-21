#!/usr/bin/env python3
"""
today.py - "a traveller in your own city": today's picks from the user's OWN places, near where
they are. No network, no model. The web half (events this week, new openings, opening hours with
`seen_at`) is the today-scout skill's, through `today.py add`.

Where "here" is - NEVER the device:
    1. the active trip's stop whose dates include today
    2. `profile/traveler.md` `home_city:` (frontmatter) or its "- Home city:" line
    3. what the user said today ("I'm in Porto") - `today.py here --set Porto`, stamped for the day

    today.py here [--set CITY] [--json]      where today's picks are built for, and why
    today.py check                           exit 0 when a "here" is known and today is not snoozed
    today.py picks [--date D] [--city C] [--radius-km 6] [--mix coffee,meal,activity,event,wildcard,social] [--json]
                                             build today's picks from the brain (one per slot), write the
                                             picks ledger, picks/<date>/picks.json, Today.geojson; print the table
    today.py add --name N --kind K --lat --lng --why "…" [--slot S] [--url U] [--seen-at T] [--price P --quoted-at T]
                                             a web pick (marked web only; a price needs quoted_at)
    today.py table [--date D]                the day's table (R2)
    today.py note [--date D]                 write the daily note's per-slot sections (Coffee · Food · …) between markers
    today.py roll [--date D]                 yesterday's unsaved suggestions expire
    today.py geojson [--date D]              rewrite Today.geojson (numbered pins)
    today.py snooze | mark-run               the stamps the routine's only_when reads

The picks ledger: <state root>/picks.jsonl - one row per pick, status suggested → saved → went →
loved / not_for_me / expired; `learn.py went|loved|not-for-me|save --pick ID` moves it (one writer).
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import state_root, render_dir, profile_dir, brain_at_cwd  # noqa: E402
import ledger_base as LB  # noqa: E402
import geo  # noqa: E402
import places as PL  # noqa: E402
import taste  # noqa: E402
import itinerary as itin  # noqa: E402

PICKS = "picks.jsonl"
TODAY_GEOJSON = "Today.geojson"
SLOTS = ("coffee", "meal", "activity", "event", "wildcard", "social")
SLOT_LABEL = {"coffee": "Coffee", "meal": "Lunch / dinner", "activity": "Activity", "event": "Event",
              "wildcard": "New neighbourhood", "social": "Social"}
# which brain categories / place kinds feed each slot
SLOT_CATS = {"coffee": {"coffee", "tea", "bakery"}, "meal": {"ramen", "sushi", "tapas", "seafood", "fine-dining", "pizza", "restaurant", "hotel-breakfast"},
             "activity": {"museum", "viewpoint", "landmark", "garden", "beach", "trail", "bookshop", "design-shop", "market-shop"},
             "event": {"music", "event-venue"}, "social": {"wine-bar", "cocktail-bar", "bar", "market"}}
SLOT_KINDS = {"coffee": {"cafe"}, "meal": {"restaurant"}, "activity": {"museum", "tour", "viewpoint", "sight", "trail", "shop"},
              "event": {"venue"}, "social": {"bar", "market", "venue"}}
RECENT_DAYS = 30
STATUSES = ("suggested", "saved", "went", "loved", "not_for_me", "expired")
TRANSITIONS = {"suggested": {"saved", "went", "not_for_me", "expired"}, "saved": {"went", "not_for_me", "expired"},
               "went": {"loved", "not_for_me"}, "loved": set(), "not_for_me": set(), "expired": {"saved", "went"}}
TODAY = datetime.date.today()


def ledger():
    return LB.Ledger(state_root(), PICKS, key="id", status="status", transitions=TRANSITIONS, events_file="pick-events.jsonl")


def _d(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- where
def _profile_home():
    p = profile_dir() / "traveler.md"
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^home_city:\s*(.+?)\s*$", txt, re.M)
    if m and m.group(1).strip() and not m.group(1).strip().startswith("<"):
        return m.group(1).strip().strip('"')
    m = re.search(r"^-\s*Home city:\s*(.+?)\s*$", txt, re.M)
    if m and m.group(1).strip() and not m.group(1).strip().startswith("<"):
        return m.group(1).strip()
    return None


def _stamp_path():
    return state_root() / "here.json"


def set_here(city, date=None):
    d = (date or TODAY.isoformat())[:10]
    p = _stamp_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"city": city.strip(), "date": d}) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return {"city": city.strip(), "date": d}


def here(date=None):
    """{city, country, lat, lng, source} or None. Never the device."""
    today = _d(date) or TODAY
    # 1. the active trip's stop that covers today
    cur = itin.current()
    if cur:
        try:
            it = itin.load(cur)
            for s in it.get("stops") or []:
                a, b = _d(s.get("arrive")), _d(s.get("depart"))
                if a and b and a <= today <= b:
                    return {"city": s.get("place"), "country": s.get("country") or "", "lat": s.get("lat"), "lng": s.get("lng"),
                            "source": f"trip {cur} · stop {s.get('id')}", "trip": cur, "stop": s.get("id")}
        except (itin.ItineraryError, ValueError):
            pass
    # 3. what the user said today (checked before home: "I'm in Porto" wins over the profile)
    try:
        st = json.loads(_stamp_path().read_text(encoding="utf-8"))
        if st.get("city") and st.get("date") == today.isoformat():
            return _with_centre({"city": st["city"], "country": "", "source": "you said so today"})
    except (OSError, ValueError):
        pass
    # 2. home
    home = _profile_home()
    if home:
        return _with_centre({"city": home, "country": "", "source": "profile/traveler.md home_city"})
    return None


def _with_centre(h):
    c = city_centre(h["city"])
    if c:
        h.update({"lat": c[0], "lng": c[1], "country": c[2] or h.get("country", "")})
    return h


def city_centre(city):
    """The centroid of the brain's places in that city (lat, lng, country), or None."""
    recs = [r for r in PL.load() if (r.get("city") or "").lower() == (city or "").lower() and geo.has_coords(r)]
    if not recs:
        return None
    c = geo.centroid(recs)
    cc = max((r.get("country") or "" for r in recs), key=lambda x: sum(1 for r in recs if r.get("country") == x))
    return (round(c[0], 5), round(c[1], 5), cc)


def check(date=None):
    """0 = run today; 1 = nothing to do (no here, or snoozed)."""
    today = (date or TODAY.isoformat())[:10]
    sn = state_root() / "snooze.txt"
    if sn.is_file() and sn.read_text(encoding="utf-8").strip() == today:
        return 1, "snoozed today"
    h = here(date)
    if not h:
        return 1, "no \"here\" known: set home_city in profile/traveler.md or say where you are"
    return 0, f"here: {h['city']} ({h['source']})"


# ---------------------------------------------------------------- picks
def _recent_names(rows, today, days=RECENT_DAYS):
    cut = (today - datetime.timedelta(days=days)).isoformat()
    return {(r.get("name") or "").lower() for r in rows if str(r.get("date") or "") >= cut and r.get("status") not in ("expired",)}


def _slot_of(rec):
    cat = rec.get("category") or ""
    kind = (rec.get("kind") or "").lower()
    for slot in ("coffee", "meal", "event", "social", "activity"):
        if cat in SLOT_CATS[slot] or kind in SLOT_KINDS[slot]:
            return slot
    return "activity" if geo.has_coords(rec) else ""


def _mix(mix):
    out = [m.strip() for m in (mix or "").split(",") if m.strip() in SLOTS]
    return out or ["coffee", "meal", "activity", "event", "wildcard"]


def build_picks(h, date=None, radius_km=6.0, mix=None, lexicon=None):
    """One candidate per slot from the brain: saved-but-never-visited first, then loved kinds; not
    picked in the last 30 days; within radius; nearest first among equals. Returns (rows, missing)."""
    today = _d(date) or TODAY
    lex = lexicon or taste.load_lexicon()
    centre = (h.get("lat"), h.get("lng")) if h.get("lat") is not None else None
    recs = taste.enrich([r for r in PL.load() if geo.has_coords(r)], lex)
    L = ledger()
    existing = L.load()
    recent = _recent_names(existing, today)
    cands = []
    for r in recs:
        if (r.get("city") or "").lower() != (h.get("city") or "").lower() and centre is None:
            continue
        dist = geo.haversine_km(centre, r) if centre else None
        if dist is not None and dist > radius_km:
            continue
        if (r.get("name") or "").lower() in recent:
            continue
        slot = _slot_of(r)
        if not slot:
            continue
        new = r.get("saved") and not r.get("visited")
        score = (0.4 if new else 0.0) + 0.5 * float(r.get("love") or 0) - (0.02 * dist if dist else 0)
        if r.get("visited") and float(r.get("love") or 0) < 0.75:
            continue         # been there, did not love it: not today
        cands.append((slot, score, dist, r))
    cands.sort(key=lambda x: (-x[1], x[2] if x[2] is not None else 99, x[3]["name"].lower()))
    rows, used, missing = [], set(), []
    areas = {}
    for slot in _mix(mix):
        pick = None
        if slot == "wildcard":
            # a place in a part of town none of today's other picks is in (a new neighbourhood)
            taken_areas = {areas.get(x["name"]) for x in rows}
            for s_, sc, dist, r in cands:
                if r["name"] in used:
                    continue
                area = _area(r, centre)
                if area not in taken_areas and not r.get("visited"):
                    pick, areas[r["name"]] = (s_, sc, dist, r), area
                    break
        else:
            for s_, sc, dist, r in cands:
                if s_ == slot and r["name"] not in used:
                    pick = (s_, sc, dist, r)
                    areas[r["name"]] = _area(r, centre)
                    break
        if not pick:
            missing.append(slot)
            continue
        s_, sc, dist, r = pick
        used.add(r["name"])
        n = len(rows) + 1
        rows.append({"id": f"p-{today.isoformat()}-{n}", "date": today.isoformat(), "city": h.get("city"), "slot": slot,
                     "name": r["name"], "kind": r.get("kind") or s_, "category": r.get("category") or "",
                     "lat": r["lat"], "lng": r["lng"], "distance_km": round(dist, 1) if dist is not None else None,
                     "why": _why(r), "from_brain": True, "brain_note": r.get("note") or "", "source": "brain",
                     "url": r.get("url") or "", "seen_at": "", "status": "suggested", "updated": itin.now_iso(), "history": []})
    return rows, missing


def _area(r, centre):
    if not centre or not geo.has_coords(r):
        return ""
    # a coarse grid cell (~1.5 km) stands in for a neighbourhood: new cell = new part of town
    return f"{round(float(r['lat']) / 0.0135)}:{round(float(r['lng']) / 0.02)}"


def _why(r):
    bits = []
    if r.get("saved") and not r.get("visited"):
        bits.append("saved, never visited")
    if r.get("rating") is not None:
        bits.append(f"you rated it ★{r['rating']:g}")
    elif float(r.get("love") or 0) >= 0.75:
        bits.append("the kind of place you love")
    if r.get("lists"):
        bits.append("on your list " + ", ".join(str(x) for x in r["lists"][:2]))
    return "; ".join(bits) or "in your brain"


def write_picks(rows, date=None):
    """Append today's new picks to the ledger (one writer), write the day's snapshot + Today.geojson."""
    today = (date or TODAY.isoformat())[:10]
    L = ledger()
    with LB.lock(L.root):
        existing = L.load()
        have = {r["id"] for r in existing}
        for r in rows:
            if r["id"] in have:
                continue
            existing.append(r)
            have.add(r["id"])
        LB.write_jsonl(L.record_file, existing)
    for r in rows:
        L.event(r["id"], None, "suggested", "agent", f"{r['slot']} · {r['name']}", kind="suggested")
    snapshot(today)
    return len(rows)


def picks_for(date=None):
    today = (date or TODAY.isoformat())[:10]
    return [r for r in ledger().load() if r.get("date") == today]


def snapshot(date=None):
    today = (date or TODAY.isoformat())[:10]
    rows = picks_for(today)
    d = render_dir() / "picks" / today
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "picks.json.tmp"
    tmp.write_text(json.dumps({"schema": "sbl-picks/1", "date": today, "picks": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, d / "picks.json")
    gj = to_geojson(rows, today)
    for p in (d / TODAY_GEOJSON, render_dir() / TODAY_GEOJSON):
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(gj, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    return d


def to_geojson(rows, date):
    feats = []
    for n, r in enumerate(rows, 1):
        if not geo.has_coords(r):
            continue
        props = {"feature": "pick", "id": r["id"], "label": r["name"], "seq": n, "slot": r.get("slot"), "kind": r.get("kind", "other"),
                 "status": r.get("status"), "from_brain": bool(r.get("from_brain")), "why": r.get("why", ""), "date": date}
        if r.get("url"):
            props["url"] = r["url"]
        if r.get("seen_at"):
            props["seen_at"] = r["seen_at"]
        if r.get("price") not in (None, ""):
            props["price"], props["quoted_at"] = r["price"], r.get("quoted_at") or ""
        if r.get("from_brain") and str(r.get("brain_note") or "").endswith(".md"):
            props["note_id"] = r["brain_note"][:-3]
        feats.append({"type": "Feature", "geometry": itin._pt(r["lat"], r["lng"]), "properties": props})
    return {"type": "FeatureCollection", "properties": {"schema": itin.MAP_SCHEMA, "layer": "today", "date": date,
                                                        "city": (rows[0].get("city") if rows else "")}, "features": feats}


def table(date=None):
    rows = picks_for(date)
    out = []
    for n, r in enumerate(rows, 1):
        open_ = (f"open today ({r['seen_at'][:10]})" if r.get("seen_at") else "")
        price = (f"{r['price']} ({str(r.get('quoted_at') or '')[:10]})" if r.get("price") not in (None, "") else "")
        src = ("[[" + str(r["brain_note"])[:-3].rsplit("/", 1)[-1] + "]]") if r.get("from_brain") and str(r.get("brain_note") or "").endswith(".md") else ("web only" + (f" ([↗]({r['url']}))" if r.get("url") else ""))
        out.append({"n": n, "place": r["name"], "slot": SLOT_LABEL.get(r.get("slot"), r.get("slot")), "why": r.get("why", ""),
                    "src": src, "open": open_, "price": price, "distance": f"{r['distance_km']} km" if r.get("distance_km") is not None else "",
                    "status": r.get("status")})
    return LB.Ledger.table(["n", "place", "slot", "why", "src", "open", "price", "distance", "status"], out,
                           labels=["#", "Place", "Kind", "Why (cited)", "From", "Open today", "Price", "Distance", "Status"],
                           empty="_No picks yet today._")


SECTION_OF = {"coffee": "Coffee", "meal": "Food", "activity": "Activity", "event": "Event", "social": "Social", "wildcard": "Wildcard"}


def slot_sections(date=None):
    """{heading: body} - one structured block per slot for the dated note: the pick(s) with why
    (cited) · open today (seen_at) · price (quoted_at) · distance, and the three feedback words."""
    rows = picks_for(date)
    out = {}
    for slot, heading in SECTION_OF.items():
        mine = [(n, r) for n, r in enumerate(rows, 1) if r.get("slot") == slot]
        if not mine:
            out[heading] = "_Nothing new for this slot today._"
            continue
        lines = []
        for n, r in mine:
            src = ("[[" + str(r["brain_note"])[:-3].rsplit("/", 1)[-1] + "]]") if r.get("from_brain") and str(r.get("brain_note") or "").endswith(".md") \
                else ("web only" + (f" · [page]({r['url']})" if r.get("url") else ""))
            bits = [f"**#{n} {r['name']}** ({r.get('kind') or slot})", r.get("why") or "", src]
            if r.get("seen_at"):
                bits.append(f"open today — seen {str(r['seen_at'])[:16].replace('T', ' ')}")
            if r.get("price") not in (None, ""):
                bits.append(f"{r['price']} — quoted {str(r.get('quoted_at') or '')[:16].replace('T', ' ')}")
            if r.get("distance_km") is not None:
                bits.append(f"{r['distance_km']} km")
            lines.append("- " + " · ".join(b for b in bits if b) + f" — _{r.get('status')}_")
            lines.append(f"  Say *\"save #{n}\"* · *\"I went to #{n}\"* · *\"#{n} not for me\"* (`learn.py save|went|not-for-me --pick {r['id']}`)")
        out[heading] = "\n".join(lines)
    return out


def write_note(date=None, agent="travel-planner"):
    """Put the per-slot sections into the dated note daily.py opened (between markers)."""
    import daily as D  # noqa: PLC0415
    from ledger_base import replace_between  # noqa: PLC0415
    r = D.Run(agent, "", "", date or "")
    note = r.note_path()
    if not note.is_file():
        raise SystemExit("no daily note yet — run `daily.py start --agent travel-planner` first")
    txt = note.read_text(encoding="utf-8")
    for heading, body in slot_sections(date).items():
        key = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
        if re.search(rf"^## {re.escape(heading)}\n", txt, re.M) and f"<!-- {key}:begin -->" not in txt:
            txt = r._set_section(txt, heading, f"<!-- {key}:begin -->\n{body}\n<!-- {key}:end -->")
        else:
            txt = replace_between(txt, key, body, heading=heading)
    tmp = note.with_name(note.name + ".tmp")
    tmp.write_text(txt, encoding="utf-8")
    os.replace(tmp, note)
    return note


def add_web(name, kind, lat, lng, why, slot="", url="", seen_at="", price=None, quoted_at="", date=None, city=""):
    if price not in (None, "") and not quoted_at:
        raise SystemExit("a price needs --quoted-at (the moment it was seen) — a price is a snapshot, never a fact")
    today = (date or TODAY.isoformat())[:10]
    h = here(today) or {}
    rows = picks_for(today)
    n = len(rows) + 1
    r = {"id": f"p-{today}-{n}", "date": today, "city": city or h.get("city") or "", "slot": slot or (_slot_of({"kind": kind}) or "activity"),
         "name": name.strip(), "kind": kind, "category": "", "lat": float(lat), "lng": float(lng),
         "distance_km": round(geo.haversine_km((h["lat"], h["lng"]), (lat, lng)), 1) if h.get("lat") is not None else None,
         "why": "no brain signal — web only" + (f": {why}" if why else ""), "from_brain": False, "brain_note": "", "source": "web",
         "url": url, "seen_at": seen_at, "status": "suggested", "updated": itin.now_iso(), "history": []}
    if price not in (None, ""):
        r["price"], r["quoted_at"] = price, quoted_at
    write_picks([r], today)
    return r


def roll(date=None):
    """Yesterday's (and older) suggestions nobody saved expire at the next run."""
    today = (date or TODAY.isoformat())[:10]
    L = ledger()
    n = 0
    with LB.lock(L.root):
        rows = L.load()
        for r in rows:
            if r.get("status") == "suggested" and str(r.get("date") or "") < today:
                r["status"] = "expired"
                r["updated"] = itin.now_iso()
                r.setdefault("history", []).append({"from": "suggested", "to": "expired", "at": r["updated"], "by": "agent"})
                n += 1
        if n:
            LB.write_jsonl(L.record_file, rows)
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description="today's picks from your own places")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("here"); g.add_argument("--set", dest="set_city", default=""); g.add_argument("--date"); g.add_argument("--json", action="store_true")
    g = sub.add_parser("check"); g.add_argument("--date")
    g = sub.add_parser("picks"); g.add_argument("--date"); g.add_argument("--city"); g.add_argument("--radius-km", type=float, default=6.0)
    g.add_argument("--mix", default=""); g.add_argument("--json", action="store_true")
    g = sub.add_parser("add"); g.add_argument("--name", required=True); g.add_argument("--kind", default="other")
    g.add_argument("--lat", type=float, required=True); g.add_argument("--lng", type=float, required=True); g.add_argument("--why", default="")
    g.add_argument("--slot", default=""); g.add_argument("--url", default=""); g.add_argument("--seen-at", default="")
    g.add_argument("--price"); g.add_argument("--quoted-at", default=""); g.add_argument("--date"); g.add_argument("--city", default="")
    g = sub.add_parser("table"); g.add_argument("--date")
    g = sub.add_parser("note"); g.add_argument("--date"); g.add_argument("--agent", default="travel-planner")
    g = sub.add_parser("roll"); g.add_argument("--date")
    g = sub.add_parser("geojson"); g.add_argument("--date")
    sub.add_parser("snooze"); sub.add_parser("mark-run")
    a = ap.parse_args(argv)
    if a.cmd == "here":
        if a.set_city:
            set_here(a.set_city, a.date)
        h = here(a.date)
        if a.json:
            print(json.dumps(h or {}, ensure_ascii=False))
        else:
            print(f"here: {h['city']} — {h['source']}" if h else "no \"here\" known: set home_city in profile/traveler.md or `today.py here --set <city>`")
        return 0 if h else 1
    if a.cmd == "check":
        rc, why = check(a.date)
        print(why)
        return rc
    if a.cmd in ("snooze", "mark-run"):
        name = {"snooze": "snooze.txt", "mark-run": "today-run.txt"}[a.cmd]
        p = state_root() / name
        p.write_text(TODAY.isoformat() + "\n", encoding="utf-8")
        print(f"{name} = {TODAY.isoformat()}")
        return 0
    if a.cmd == "picks":
        h = here(a.date)
        if a.city:
            h = _with_centre({"city": a.city, "country": "", "source": "--city"}) if not h or h.get("city", "").lower() != a.city.lower() else h
        if not h:
            print("no \"here\" known", file=sys.stderr)
            return 1
        roll(a.date)
        rows, missing = build_picks(h, a.date, a.radius_km, a.mix)
        n = write_picks(rows, a.date)
        if a.json:
            print(json.dumps({"here": h, "picks": rows, "missing": missing}, ensure_ascii=False))
        else:
            print(f"here: {h['city']} ({h['source']}) · {n} pick(s) from your brain" + (f" · slots the brain cannot fill: {', '.join(missing)} (the web half)" if missing else ""))
            print(table(a.date), end="")
        return 0
    if a.cmd == "add":
        r = add_web(a.name, a.kind, a.lat, a.lng, a.why, a.slot, a.url, a.seen_at, a.price, a.quoted_at, a.date, a.city)
        print(json.dumps(r, ensure_ascii=False))
        return 0
    if a.cmd == "table":
        print(table(a.date), end="")
        return 0
    if a.cmd == "note":
        print(write_note(a.date, a.agent))
        return 0
    if a.cmd == "roll":
        print(f"{roll(a.date)} pick(s) expired")
        snapshot(a.date)
        return 0
    if a.cmd == "geojson":
        print(snapshot(a.date) / TODAY_GEOJSON)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
