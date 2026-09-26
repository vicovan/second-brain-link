#!/usr/bin/env python3
"""
render_brain.py - render trips as a Second Brain layer the user reads, searches and graphs.

    python3 render_brain.py            # render this surface's travel layer
    python3 render_brain.py --quiet    # after every change - identical files are not rewritten
    python3 render_brain.py --dest <dir>

Writes into the travel layer (resolved through paths.py):

    Travel Dashboard.md          trips, the current one, what the profile still lacks
    Trip Ideas.md                scout.py's ideas, each citing the notes behind it
    Places I Love.md             the taste summary, linking out to the places layer
    Current Trip.geojson         the active trip's map - the stable path Studio opens
    All Trips.geojson            every trip's stops and legs - the Map's overview of the others
    Suggestions.geojson          the active suggestion set + the trip ideas (suggest.py)
    suggestions/<Title>.md       one note per suggestion set
    quotes/<Title>.md            one note per flight / stay search - the familiar list, as a table
    trips/<id>/<Title>.md                    the trip note
    trips/<id>/<Title> — Itinerary.md        day by day
    trips/<id>/<Title> — Flights.md | Stays.md | Ground.md | Activities.md | Dining.md
    trips/<id>/<Title> — Day N — <City>.md

Every per-trip note is prefixed with the trip title. Obsidian resolves [[Itinerary]] by
title OR filename, so a bare `Itinerary.md` in every trip folder would make every such link
ambiguous - the same shadowing failure as recreating a place note.

## What it will not do

- It never writes `profile/` - that is onboarding's.
- It never deletes. A note that stops being produced is listed in the build report.
- It never touches the engine's `_GENERATED.json`; its own manifest is `_TRAVEL_GENERATED.json`
  in the ledger, so `build_vault.py --refresh` treats these notes as user files.
- It never creates a note named like a place. It links to the places layer instead - which is
  what finally gives those notes inbound edges in the graph.
- It never prints a price without the moment it was seen.
"""
import argparse, datetime, hashlib, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import itinerary as itin  # noqa: E402
import suggest as sug  # noqa: E402
import quotes as qts  # noqa: E402
from paths import (render_dir, state_root, machinery_dir, surface_root, is_brain,  # noqa: E402
                   profile_dir, places_dir)

MANIFEST = "_TRAVEL_GENERATED.json"
BUILD_REPORT = "_TRAVEL_BUILD_REPORT.md"
DASHBOARD = "Travel Dashboard.md"
IDEAS = "Trip Ideas.md"
LOVE = "Places I Love.md"
CURRENT_GEOJSON = "Current Trip.geojson"
PROFILE_FILES = ("traveler.md", "travel-criteria.md", "taste.md", "booking-answers.md", "providers.md")
DINING_KINDS = {"cafe", "restaurant", "bar", "market"}
RISK_SENTENCE = ("**Self-transfer — separate tickets.** Bags are not through-checked: collect and "
                 "re-check. If the first flight is late the second carrier owes you nothing, and a "
                 "missed connection is paid for twice. Changing planes landside means entering the "
                 "country — check the visa rules for your passport.")
TODAY = datetime.date.today().isoformat()


# ---------------------------------------------------------------- helpers
def safe(name):
    name = re.sub(r"[/\\:*?\"<>|#^\[\]]", "-", str(name)).strip().rstrip(".")
    return re.sub(r"\s+", " ", name)[:120]


def yaml_scalar(v):
    s = "" if v is None else str(v)
    if s == "" or s != s.strip() or s[0] in "&*!|>%@`'\"[]{}#-?" or ": " in s or s.endswith(":") \
            or s[0] == "+" or s.startswith("[["):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def frontmatter(pairs, tags):
    out = ["---"]
    for k, v in pairs:
        if isinstance(v, list):
            out.append(f"{k}:" + ("" if v else " []"))
            out += [f"  - {yaml_scalar(x)}" for x in v]
        else:
            out.append(f"{k}: {yaml_scalar(v)}")
    out.append("tags: [" + ", ".join(tags) + "]")
    out.append("---")
    return "\n".join(out) + "\n\n"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Writer:
    """Writes only what changed, and remembers what it wrote."""

    def __init__(self, root, quiet=False):
        self.root, self.quiet, self.man, self.wrote, self.same = pathlib.Path(root), quiet, {}, 0, 0

    def text(self, rel, body):
        p = self.root / rel
        self.man[str(rel)] = sha(body)
        try:
            if p.is_file() and p.read_text(encoding="utf-8") == body:
                self.same += 1
                return False
        except OSError:
            pass
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, p)
        self.wrote += 1
        if not self.quiet:
            print(f"  + {rel}", file=sys.stderr)
        return True


def money(v, cur, quoted_at):
    if v in (None, ""):
        return "—"
    if not quoted_at:
        return "— (price withheld: no quote time)"       # invariant 2, in the renderer too
    return f"{cur} {float(v):,.0f} · seen {str(quoted_at).replace('T', ' ')[:16]}"


class Links:
    """Which notes exist, so a link is only ever written to a real note."""

    def __init__(self, surface):
        self.surface = pathlib.Path(surface)

    def place(self, brain_note):
        """[[<filename stem>]] for a place note that exists, else None."""
        if not brain_note or ".." in brain_note.split("/"):
            return None
        p = self.surface / brain_note
        return f"[[{p.stem}]]" if p.is_file() else None


def poi_line(p, links):
    link = links.place(p.get("brain_note")) if p.get("from_brain") else None
    name = link or f"**{p['name']}**"
    bits = [p.get("kind", "")]
    if p.get("rating") is not None:
        bits.append(f"★{p['rating']:g}")
    if p.get("price_band"):
        bits.append(p["price_band"])
    b = (p.get("booking") or {}).get("url")
    tail = f" · [book]({b})" if b else ""
    return f"{name} — {' · '.join(x for x in bits if x)} — _{p.get('why', '')}_{tail}"


# ---------------------------------------------------------------- per-trip notes
def trip_titles(it):
    t = safe(it["title"])
    return {"trip": t, "itin": f"{t} — Itinerary", "flights": f"{t} — Flights",
            "stays": f"{t} — Stays", "ground": f"{t} — Ground",
            "acts": f"{t} — Activities", "dining": f"{t} — Dining"}


def day_title(it, n, city):
    return f"{safe(it['title'])} — Day {n} — {safe(city)}"


def render_trip(w, it, links, current_id):
    base = f"trips/{it['trip_id']}"
    T = trip_titles(it)
    days = itin.day_numbers(it)
    stops = {s["id"]: s for s in it["stops"]}
    pois = {p["id"]: p for p in it["pois"]}
    cur = it.get("currency", "")
    countries = sorted({s.get("country") for s in it["stops"] if s.get("country")})
    start = min((s["arrive"] for s in it["stops"] if s.get("arrive")), default="")
    end = max((s["depart"] for s in it["stops"] if s.get("depart")), default="")
    common = [("trip_id", it["trip_id"]), ("trip", f"[[{T['trip']}]]")]
    tag = f"trip/{it['trip_id']}"

    # --- the trip note
    L = [f"# {it['title']}", ""]
    if it["trip_id"] == current_id:
        L += ["> [!info] The current trip — Studio's Map opens on it (`Current Trip.geojson`).", ""]
    L += [f"**{it['status']}** · {start or '?'} → {end or '?'} · {len(days)} day(s) · "
          f"{len(it['stops'])} stop(s) · {len(it['pois'])} place(s)", ""]
    L += ["## Stops", "", "| # | Stop | Role | Dates | Nights | Stay |", "|---|---|---|---|---|---|"]
    for i, s in enumerate(it["stops"], 1):
        st = s.get("stay") or {}
        stay = st.get("name", "—") + (f" ({st.get('status')})" if st.get("status") else "")
        role = "**stopover**" if s["role"] == "stopover" else s["role"]
        L.append(f"| {i} | {s['place']}, {s.get('country', '')} | {role} | {s.get('arrive', '')} → "
                 f"{s.get('depart', '')} | {s.get('nights', 0)} | {stay} |")
    L.append("")
    for s in it["stops"]:
        if s.get("why"):
            L.append(f"- **{s['place']}** — {s['why']}")
    selfx = [l for l in it["legs"] if l.get("self_transfer")]
    if selfx:
        L += ["", "> [!warning] " + RISK_SENTENCE]
        for l in selfx:
            L.append(f"> - {l.get('from')} → {l.get('to')}: {(l.get('risk') or {}).get('why', '')}")
    L += ["", "## Notes", "", f"- [[{T['itin']}]] — day by day",
          f"- [[{T['flights']}]] · [[{T['stays']}]] · [[{T['ground']}]]",
          f"- [[{T['acts']}]] · [[{T['dining']}]]", "",
          "The map: `map.geojson` in this folder — Studio draws it on the Map canvas.", ""]
    w.text(f"{base}/{T['trip']}.md", frontmatter(
        [("type", "trip"), ("title", T["trip"]), ("trip_id", it["trip_id"]),
         ("status", it["status"]), ("start", start), ("end", end), ("nights", it["window"].get("nights", 0)),
         ("countries", countries), ("stops", [s["place"] for s in it["stops"]]),
         ("updated", it.get("updated", ""))],
        ["travel", "trip", tag]) + "\n".join(L))

    # --- itinerary + day notes
    L = [f"# {it['title']} — itinerary", ""]
    for s in it["stops"]:
        for d in s.get("days") or []:
            n = days.get(d["date"])
            dt = day_title(it, n, s["place"])
            route = next((r for r in it.get("routes") or [] if r["id"] == d.get("route")), None)
            L.append(f"## Day {n} — {d['date']} — {s['place']}" + (" (stopover)" if s["role"] == "stopover" else ""))
            L.append(f"[[{dt}]]" + (f" · ~{route['walk_minutes']} min walking" if route else ""))
            L.append("")
            for k, pid in enumerate(d.get("items") or [], 1):
                if pid in pois:
                    L.append(f"{k}. {poi_line(pois[pid], links)}")
            if not d.get("items"):
                L.append("_Free — travel or rest._")
            L.append("")
            DL = [f"# Day {n} — {s['place']}", "", f"{d['date']} · stop **{s['place']}** "
                  f"({s['role']}) · back to [[{T['trip']}]]", ""]
            for k, pid in enumerate(d.get("items") or [], 1):
                if pid in pois:
                    DL.append(f"{k}. {poi_line(pois[pid], links)}")
            if route:
                DL += ["", f"Walking route: ~{route['walk_minutes']} min, in this order."]
            w.text(f"{base}/{dt}.md", frontmatter(
                common + [("type", "trip-day"), ("title", dt), ("date", d["date"]), ("day", n),
                          ("stop", s["place"])], ["travel", "trip-day", tag]) + "\n".join(DL) + "\n")
    w.text(f"{base}/{T['itin']}.md", frontmatter(
        common + [("type", "trip-itinerary"), ("title", T["itin"])],
        ["travel", "itinerary", tag]) + "\n".join(L))

    # --- flights
    L = [f"# {it['title']} — flights", "", f"Back to [[{T['trip']}]]. Every price is a snapshot, "
         "stamped with when it was seen.", ""]
    flights = [l for l in it["legs"] if l.get("mode") == "flight"]
    if not flights:
        L.append("_Not shopped yet._")
    for l in flights:
        L.append(f"## {l.get('from')} → {l.get('to')}" + (" — self-transfer" if l.get("self_transfer") else ""))
        if l.get("stopover_stop") in stops:
            L.append(f"Leaves the stopover in **{stops[l['stopover_stop']]['place']}**.")
        if l.get("self_transfer"):
            L += ["", "> [!warning] " + RISK_SENTENCE, f"> {(l.get('risk') or {}).get('why', '')}"]
        L += ["", "| Flight | From | To | Departs | Arrives | Ticket |", "|---|---|---|---|---|---|"]
        for sg in l.get("segments") or []:
            L.append(f"| {sg.get('number', '')} | {sg.get('from')} | {sg.get('to')} | "
                     f"{str(sg.get('dep', '')).replace('T', ' ')} | {str(sg.get('arr', '')).replace('T', ' ')} | {sg.get('ticket', '')} |")
        L += ["", "| Ticket | Sold by | Price | Link |", "|---|---|---|---|"]
        for t in l.get("tickets") or []:
            link = f"[open]({t['source_url']})" if t.get("source_url") else ""
            L.append(f"| {t.get('id')} | {t.get('provider', '')} | "
                     f"{money(t.get('price'), t.get('currency') or cur, t.get('quoted_at'))} | {link} |")
        L.append("")
    w.text(f"{base}/{T['flights']}.md", frontmatter(
        common + [("type", "trip-flights"), ("title", T["flights"])], ["travel", "flights", tag]) + "\n".join(L) + "\n")

    # --- stays
    L = [f"# {it['title']} — stays", "", f"Back to [[{T['trip']}]].", "",
         "| Stop | Nights | Stay | Status | Price | Link |", "|---|---|---|---|---|---|"]
    for s in it["stops"]:
        st = s.get("stay") or {}
        link = f"[open]({st['url']})" if st.get("url") else ""
        L.append(f"| {s['place']}{' (stopover)' if s['role'] == 'stopover' else ''} | {s.get('nights', 0)} | "
                 f"{st.get('name', '—')} | {st.get('status', '—')} | "
                 f"{money(st.get('price'), st.get('currency') or cur, st.get('quoted_at'))} | {link} |")
    w.text(f"{base}/{T['stays']}.md", frontmatter(
        common + [("type", "trip-stays"), ("title", T["stays"])], ["travel", "stays", tag]) + "\n".join(L) + "\n")

    # --- ground
    L = [f"# {it['title']} — ground", "", f"Back to [[{T['trip']}]].", ""]
    ground = [l for l in it["legs"] if l.get("mode") != "flight"]
    if not ground:
        L.append("_No trains, cars or ferries planned yet._")
    for l in ground:
        t = (l.get("tickets") or [{}])[0]
        L.append(f"- **{l.get('mode')}** {l.get('from')} → {l.get('to')} — "
                 f"{money(t.get('price'), t.get('currency') or cur, t.get('quoted_at'))}"
                 + (f" · [open]({t['source_url']})" if t.get("source_url") else "")
                 + (f" — {l['note']}" if l.get("note") else ""))
    w.text(f"{base}/{T['ground']}.md", frontmatter(
        common + [("type", "trip-ground"), ("title", T["ground"])], ["travel", "ground", tag]) + "\n".join(L) + "\n")

    # --- activities + dining: brain first, web only second, never blurred
    for key, kinds, label in (("acts", None, "activities"), ("dining", DINING_KINDS, "dining")):
        sel = [p for p in it["pois"] if (p.get("kind") in kinds) == (kinds is not None)] if kinds \
            else [p for p in it["pois"] if p.get("kind") not in DINING_KINDS]
        L = [f"# {it['title']} — {label}", "", f"Back to [[{T['trip']}]].", ""]
        mine = [p for p in sel if p.get("from_brain")]
        web = [p for p in sel if not p.get("from_brain")]
        L += ["## From your own brain", ""] + ([f"- {poi_line(p, links)} ({stops.get(p['stop'], {}).get('place', '')})"
                                               for p in mine] or ["_None yet._"])
        L += ["", "## Web only — no signal from you", ""] + ([f"- {poi_line(p, links)} ({stops.get(p['stop'], {}).get('place', '')})"
                                                              for p in web] or ["_None._"])
        w.text(f"{base}/{T[key]}.md", frontmatter(
            common + [("type", f"trip-{label}"), ("title", T[key])], ["travel", label, tag]) + "\n".join(L) + "\n")
    return T["trip"]


# ---------------------------------------------------------------- suggestion sets
def set_title(sset, surface):
    """The note's name: the set's title - unless a place note already has that name, which
    would shadow it (the same rule as trips)."""
    t = safe(sset["title"]) or sset["set_id"]
    pd = places_dir(surface) if is_brain(surface) else None
    if pd and pd.is_dir() and any(p.stem.lower() == t.lower() for p in pd.glob("*.md")):
        t = f"{t} — Suggestions"
    return t


def render_suggestions(w, links, sets, current_set, surface):
    for st in sets:
        near = st.get("near") or {}
        mine = [p for p in st["picks"] if p.get("from_brain")]
        web = [p for p in st["picks"] if not p.get("from_brain")]
        L = [f"# {st['title']}", "",
             f"Suggestions near **{near.get('place', '')}**"
             + (" — on Studio's Map now." if st["set_id"] == current_set else "."), ""]

        def line(p):
            link = links.place(p.get("brain_note")) if p.get("from_brain") else None
            bits = [p.get("kind", "")]
            if p.get("rating") is not None:
                bits.append(f"★{p['rating']:g}" + (f" ({p['reviews']:,} reviews)" if p.get("reviews") else ""))
            if p.get("match"):
                bits.append(f"{p['match']} match")
            tail = f" · [page]({p['url']})" if p.get("url") else ""
            off = "" if itin.geo.has_coords(p) else " · _not on the map (no coordinates)_"
            ev = "".join(f"\n  > “{e}”" for e in p.get("evidence") or [])
            return (f"- {link or '**' + p['name'] + '**'} — {' · '.join(b for b in bits if b)} — "
                    f"_{p.get('why', '')}_{tail}{off}{ev}")

        if mine:
            L += ["## From your own brain", ""] + [line(p) for p in mine] + [""]
        if web:
            L += ["## Web only — no brain signal", ""] + [line(p) for p in web] + [""]
        if not st["picks"]:
            L += ["_No picks yet._", ""]
        L += ["> [!info] Opening hours and prices change — check before going. Nothing here is booked.",
              "", "Back to [[Travel Dashboard]].", ""]
        w.text(f"suggestions/{set_title(st, surface)}.md",
               frontmatter([("type", "travel-suggestions"), ("title", st["title"]),
                            ("near", near.get("place", "")), ("picks", len(st["picks"])),
                            ("updated", str(st.get("updated", ""))[:10])], ["travel", "suggestions"])
               + "\n".join(L))


# ---------------------------------------------------------------- quote sets
def quote_title(q, surface):
    t = safe(q["title"]) or q["id"]
    pd = places_dir(surface) if is_brain(surface) else None
    if pd and pd.is_dir() and any(p.stem.lower() == t.lower() for p in pd.glob("*.md")):
        t = f"{t} — {q['kind'].title()}"
    return t


def _cell(v):
    return str(v).replace("|", "/").replace("\n", " ")


def render_quotes(w, sets, surface, trips_by_id):
    for q in sets:
        opts, cur = q.get("options") or [], (q.get("options") or [{}])[0].get("currency", "")
        L = [f"# {q['title']}", ""]
        qy = q.get("query") or {}
        if q["kind"] == "flights":
            L.append(f"**{qy.get('from')} → {qy.get('to')}** · {qy.get('date')}"
                     + (f" – {qy['return']}" if qy.get("return") else " · one way")
                     + f" · {qy.get('adults', 1)} adult(s)")
        else:
            L.append(f"**{qy.get('city')}** · {qy.get('checkin')} → {qy.get('checkout')} "
                     f"({qy.get('nights')} nights) · {qy.get('guests', 1)} guest(s)")
        if q.get("trip") and q["trip"] in trips_by_id:
            L.append(f"For [[{trip_titles(trips_by_id[q['trip']])['trip']}]].")
        L += ["", "> [!info] Real prices read on the sites — each with the moment it was seen. They change; "
              "the link is where to check and book. Nothing here is held or booked.", ""]
        if not opts:
            L.append("_No options recorded yet._")
        elif q["kind"] == "flights":
            L += ["| # | Depart → Arrive | Airline | Duration | Stops | Price | Seen | |",
                  "|---|---|---|---|---|---|---|---|"]
            for o in opts:
                airl = " + ".join(dict.fromkeys(sg.get("carrier_name") or sg.get("carrier") for sg in o["segments"]))
                stops = "Direct" if o["stops"] == 0 else f"{o['stops']} stop" + ("s" if o["stops"] > 1 else "") + \
                    " · " + ", ".join(l["at"] + (f" {qts.hm(l['min'])}" if l.get("min") is not None else "")
                                    for l in o.get("layovers") or [])
                if o.get("self_transfer"):
                    stops += " · **self-transfer**"
                tag = f" **{', '.join(o['tags'])}**" if o.get("tags") else ""
                pick = " ✔ picked" if q.get("picked") == o["id"] else ""
                L.append(f"| {o['id']}{pick} | {qts.hhmm(o['dep'])} → {qts.hhmm(o['arr'])}"
                         f"{qts.plus_days(o['dep'], o['arr'])} · {o['from']}–{o['to']} | {_cell(airl)} | "
                         f"{qts.hm(o.get('total_min')) or '—'} | {_cell(stops)} | "
                         f"{qts.money(o['price'], o['currency'])}{tag} | {o['quoted_at'].replace('T', ' ')} · "
                         f"{_cell(o['provider'])} | [open]({o['url']}) |")
            if any(o.get("self_transfer") for o in opts):
                L += ["", RISK_SENTENCE]
            if any(o.get("bags") for o in opts):
                L += ["", "Bags: " + "; ".join(f"{o['id']} {o['bags']}" for o in opts if o.get("bags"))]
        else:
            L += ["| # | Stay | Rating | Area | Total | Per night | Terms | Seen | |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for o in opts:
                stars = ("★" * int(o["stars"])) if o.get("stars") else ""
                rating = (f"{o['rating']:g}/{o.get('rating_scale', 10):g}" +
                          (f" ({o['reviews']:,})" if o.get("reviews") else "")) if o.get("rating") else "—"
                terms = ", ".join(t for t, on in (("free cancellation", o.get("free_cancellation")),
                                                  ("breakfast", o.get("breakfast"))) if on) or "—"
                tag = f" **{', '.join(o['tags'])}**" if o.get("tags") else ""
                pick = " ✔ picked" if q.get("picked") == o["id"] else ""
                L.append(f"| {o['id']}{pick} | **{_cell(o['name'])}** {stars} | {rating} | {_cell(o.get('area', '—'))} | "
                         f"{qts.money(o['price_total'], o['currency'])}{tag} | {qts.money(o['price_night'], o['currency'])} | "
                         f"{terms} | {o['quoted_at'].replace('T', ' ')} · {_cell(o['provider'])} | [open]({o['url']}) |")
        L += ["", "Back to [[Travel Dashboard]].", ""]
        w.text(f"quotes/{quote_title(q, surface)}.md",
               frontmatter([("type", f"travel-{q['kind']}"), ("title", q["title"]),
                            ("options", len(opts)), ("updated", str(q.get("updated", ""))[:10])],
                           ["travel", q["kind"]]) + "\n".join(L))


# ---------------------------------------------------------------- layer root
def render_ideas(w, links):
    try:
        data = json.loads((state_root() / "ideas.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"ideas": [], "meta": {}}
    meta = data.get("meta") or {}
    L = ["# Trip ideas", "", "Where your own brain says you have been meaning to go — every line cites "
         "the notes behind it. Made by the Travel Agent's scout from your places alone; no web.", ""]
    if meta.get("months"):
        L += [f"You usually travel in **{', '.join(meta['months'])}**.", ""]
    if not data.get("ideas"):
        L.append("_No ideas yet — ask the Travel Agent where you should go._")
    for i, x in enumerate(data.get("ideas") or [], 1):
        L += [f"## {i}. {x['city']}, {x['country']}", "", x.get("why", ""), ""]
        saved = [links.place(n) for n in x.get("saved_not_visited") or []]
        loved = [links.place(n) for n in x.get("loved") or []]
        ppl = [f"[[{pathlib.Path(n).stem}]]" for n in x.get("people") or [] if (links.surface / n).is_file()]
        if any(saved):
            L.append("- Saved, never visited: " + ", ".join(s for s in saved if s))
        if any(loved):
            L.append("- You rated highly: " + ", ".join(s for s in loved if s))
        if ppl:
            L.append("- People you know there: " + ", ".join(ppl))
        if x.get("categories"):
            L.append("- What you keep there: " + ", ".join(x["categories"]))
        L.append("")
    w.text(IDEAS, frontmatter([("type", "travel-ideas"), ("title", "Trip Ideas"),
                               ("updated", meta.get("generated", ""))], ["travel"]) + "\n".join(L))


def render_love(w, links, surface):
    try:
        import places as _places, taste as _taste
        recs = _taste.enrich(_places.load(surface))
    except Exception:
        recs = []
    loved = sorted((r for r in recs if r.get("rating") is not None and r["rating"] >= 4),
                   key=lambda r: (r["category"], -r["rating"], r["name"]))
    L = ["# Places I love", "", "Everything you rated ★4 or more, grouped by what it is. The categories are "
         "the plugin's guess from names, lists and your own words — `profile/taste.md` is where you "
         "correct them.", ""]
    cat = None
    for r in loved:
        if r["category"] != cat:
            cat = r["category"]
            L += ["", f"## {cat}", ""]
        link = links.place(r["note"]) or r["name"]
        L.append(f"- {link} — ★{r['rating']:g} · {r.get('city') or '?'}"
                 + (f" — “{r['review'][:100]}”" if r.get("review") else ""))
    if not loved:
        L.append("_No rated places in this brain yet._")
    w.text(LOVE, frontmatter([("type", "travel-taste"), ("title", "Places I Love"),
                              ("count", len(loved))], ["travel"]) + "\n".join(L) + "\n")


def render_dashboard(w, trips, current_id, surface, sets=(), current_set=None, quote_sets=()):
    L = ["# Travel dashboard", "", f"_Rendered {TODAY} from "
         f"{'this brain' if is_brain(surface) else 'the working folder'}._", ""]
    if current_id:
        cur = next((t for t in trips if t["trip_id"] == current_id), None)
        if cur:
            L += [f"**Current trip:** [[{trip_titles(cur)['trip']}]] — Studio's Map opens on it.", ""]
    L += ["## Trips", ""]
    if not trips:
        L.append("_None yet. Ask the Travel Agent for trip ideas, or to plan somewhere._")
    else:
        L += ["| Trip | Status | Dates | Stops | Places (from your brain) |", "|---|---|---|---|---|"]
        for it in sorted(trips, key=lambda t: min((s.get("arrive") or "9" for s in t["stops"]), default="9")):
            start = min((s["arrive"] for s in it["stops"] if s.get("arrive")), default="")
            mine = sum(1 for p in it["pois"] if p.get("from_brain"))
            L.append(f"| [[{trip_titles(it)['trip']}]] | {it['status']} | {start} | "
                     f"{', '.join(s['place'] for s in it['stops'])} | {len(it['pois'])} ({mine}) |")
    if sets:
        L += ["", "## Suggestions", ""]
        for st in sets:
            L.append(f"- [[{set_title(st, surface)}]] — {len(st['picks'])} pick(s) near "
                     f"{(st.get('near') or {}).get('place', '')}"
                     + (" · on the Map" if st["set_id"] == current_set else ""))
    if quote_sets:
        L += ["", "## Flights and stays found", ""]
        for q in sorted(quote_sets, key=lambda x: x.get("updated", ""), reverse=True):
            L.append(f"- [[{quote_title(q, surface)}]] — {len(q.get('options') or [])} {q['kind']} option(s)")
    L += ["", "## Also here", "", f"- [[Trip Ideas]] — where your brain says to go",
          f"- [[Places I Love]] — your taste, from your own ratings", ""]
    pdir = profile_dir()
    missing = [f for f in PROFILE_FILES if not (pdir / f).is_file()]
    L += ["## Profile", ""]
    if missing:
        L.append("Missing: " + ", ".join(f"`{m}`" for m in missing) + " — ask the Travel Agent to set you up.")
    else:
        L.append("All five profile files are present.")
    L += ["", "> [!info] Prices are snapshots, never promises. The planner drives public travel sites "
          "through your own browser; some block automation, and then you get a pre-filled link "
          "instead. Nothing is booked in this version.", ""]
    w.text(DASHBOARD, frontmatter([("type", "travel-dashboard"), ("title", "Travel Dashboard"),
                                   ("updated", TODAY), ("trips", len(trips))], ["travel", "dashboard"])
           + "\n".join(L))


# ---------------------------------------------------------------- main
def render(dest=None, quiet=False):
    out = render_dir(dest)
    surface = surface_root() if not dest else out.parent
    links = Links(surface)
    w = Writer(out, quiet)
    trips = []
    for tid in itin.list_trips(dest):
        try:
            trips.append(itin.load(tid, dest))
        except (itin.ItineraryError, ValueError) as e:
            print(f"skip {tid}: {e}", file=sys.stderr)
    current_id = itin.current(dest)
    for it in trips:
        render_trip(w, it, links, current_id)
    sets = []
    for sid in sug.list_sets(dest):
        try:
            sets.append(sug.load(sid, dest))
        except (sug.SuggestError, ValueError) as e:
            print(f"skip suggestions {sid}: {e}", file=sys.stderr)
    current_set = sug.current(dest)
    render_suggestions(w, links, sets, current_set, surface)
    quote_sets = []
    for qid in qts.list_sets(dest):
        try:
            quote_sets.append(qts.load(qid, dest))
        except (qts.QuoteError, ValueError) as e:
            print(f"skip quotes {qid}: {e}", file=sys.stderr)
    render_quotes(w, quote_sets, surface, {t["trip_id"]: t for t in trips})
    render_ideas(w, links)
    render_love(w, links, surface)
    render_dashboard(w, trips, current_id, surface, sets, current_set, quote_sets)
    # the stable path Studio's Map opens: the active trip's map, or an empty collection
    geo_text = json.dumps({"type": "FeatureCollection", "properties": {"schema": itin.MAP_SCHEMA,
                                                                       "trip_id": ""}, "features": []}) + "\n"
    if current_id:
        p = itin.trip_dir(current_id, dest) / "map.geojson"
        if p.is_file():
            geo_text = p.read_text(encoding="utf-8")
    w.text(CURRENT_GEOJSON, geo_text)
    # the Map's other two layers - the same bytes suggest.py / itinerary.py write mid-run
    w.text(itin.ALL_TRIPS_GEOJSON, json.dumps(itin.all_trips_geojson(dest), ensure_ascii=False) + "\n")
    w.text(sug.GEOJSON, sug.geojson_text(dest))
    # machinery: own manifest + report, in the hidden ledger
    mdir = machinery_dir(state_root(), out)
    prev = {}
    try:
        prev = json.loads((mdir / MANIFEST).read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError):
        pass
    stale = sorted(set(prev) - set(w.man))
    (mdir / MANIFEST).write_text(json.dumps({"schema": 1, "generated": TODAY, "layer": str(out),
                                             "files": w.man}, indent=1, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
    rep = [f"# Travel layer build — {TODAY}", "", f"- layer: `{out}`", f"- written: {w.wrote}",
           f"- unchanged: {w.same}", f"- trips: {len(trips)}"]
    if stale:
        rep += ["", "## No longer produced (left in place — delete by hand if unwanted)", ""] + \
               [f"- `{s}`" for s in stale]
    (mdir / BUILD_REPORT).write_text("\n".join(rep) + "\n", encoding="utf-8")
    return out, w


def main():
    ap = argparse.ArgumentParser(description="render the travel layer")
    ap.add_argument("--dest")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    out, w = render(a.dest, a.quiet)
    if not a.quiet:
        print(f"{out}: {w.wrote} written, {w.same} unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
