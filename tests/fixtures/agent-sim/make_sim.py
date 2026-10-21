#!/usr/bin/env python3
"""make_sim.py - the fictional sim ledgers every agent's daily is dry-run against (tests/run.py
test_agent_dailies) and the sim data Studio's scenes read (SBL_KEEP_PIPELINES).

Deterministic (seeded), fictional names only (Northwind, Globex, Acme, Initech, Tidewater,
Vandelay … and generated word pairs), generic places (Lisbon, Madrid, Tokyo, Paris, Berlin).
Writes, beside this file:

    ../fundraising-sim/   targets.jsonl + events.jsonl   300 targets over every status and both kinds:
                          40 deadlines, 25 stale claims, 12 due follow-ups, 20 applications, 15 drafts
    ../sales-sim/         accounts.jsonl + events.jsonl  120 accounts over every stage incl. trial; 60 sends; 14 replies
    ../travel-sim/        47-travel/trips/<id>/itinerary.json (6 trips over every stage) + picks.jsonl (40 picks / 10 days)
    ../jobs-sim/          outcomes.jsonl + seen.json       60 applications over every status, 40 seen postings

    python3 tests/fixtures/agent-sim/make_sim.py            # regenerate (byte-identical for the same seed)
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
import os as _os
# SBL_SIM_OUT / SBL_SIM_TODAY: the dailies test regenerates the sims into a temp folder dated today, so it never
# depends on the day the checked-in copies were written (it failed the morning after they were made)
FIX = pathlib.Path(_os.environ['SBL_SIM_OUT']) if _os.environ.get('SBL_SIM_OUT') else HERE.parent
BASE = _dt.date.fromisoformat(_os.environ['SBL_SIM_TODAY']) if _os.environ.get('SBL_SIM_TODAY') else _dt.date(2026, 10, 20)        # the sim's "today"; tests pass --today / --date where it matters
ORGS = ["Northwind", "Globex", "Acme", "Initech", "Tidewater", "Vandelay", "Umbrella", "Hooli", "Wayne", "Stark",
        "Wonka", "Dunder", "Pied Piper", "Soylent", "Oscorp", "Cyberdyne", "Massive Dynamic", "Gringotts", "Aperture", "Monarch"]
WORDS = ["Harbor", "Summit", "Meridian", "Lantern", "Quarry", "Orchard", "Beacon", "Granite", "Juniper", "Ember",
         "Fathom", "Kestrel", "Marlin", "Saffron", "Tundra", "Verdant", "Willow", "Zenith", "Atlas", "Basalt"]
SUFFIX_FUND = ["Capital", "Ventures", "Partners", "Seed", "Labs Fund", "Angels", "Syndicate", "Growth"]
SUFFIX_PROG = ["Accelerator", "Fellowship", "Grant", "Foundry", "Launchpad", "Residency"]
CITIES = [("Lisbon", "PT", 38.7223, -9.1393), ("Madrid", "ES", 40.4168, -3.7038), ("Tokyo", "JP", 35.6762, 139.6503),
          ("Paris", "FR", 48.8566, 2.3522), ("Berlin", "DE", 52.52, 13.405)]
PEOPLE = ["Jane Doe", "Alex Rivera", "Sam Chen", "Priya Nair", "Dana Reyes", "Lee Park", "Mo Haddad", "Kim Novak",
          "Ana Costa", "Tom Baker", "Eva Lind", "Omar Said", "Yuki Sato", "Noa Levi", "Ravi Mehta", "Zoe Grant"]


def d(n):
    return (BASE - _dt.timedelta(days=n)).isoformat()


def write_jsonl(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


# ---------------------------------------------------------------- fundraising
FR_STATUSES = ["screened", "verified", "out", "queued", "drafted", "draft_ready", "filed", "contacted", "no_reply",
               "replied", "meeting", "passed", "accepted", "rejected", "term_sheet", "withdrawn"]


def fundraising(rng):
    recs, evs = [], []
    kinds = ["fund"] * 120 + ["angel"] * 40 + ["strategic"] * 20 + ["syndicate"] * 20 + ["program"] * 70 + ["grant"] * 30
    rng.shuffle(kinds)
    used = set()
    deadlines = stale = due = apps = drafts = 0
    for i in range(300):
        kind = kinds[i]
        name = f"{rng.choice(WORDS)} {rng.choice(SUFFIX_PROG if kind in ('program', 'grant') else SUFFIX_FUND)}"
        while name in used:
            name = f"{rng.choice(WORDS)} {rng.choice(ORGS).split()[0]} {rng.choice(SUFFIX_PROG if kind in ('program', 'grant') else SUFFIX_FUND)}"
        used.add(name)
        key = name.lower().replace(" ", "-")
        prog = kind in ("program", "grant")
        pool = (["screened"] * 6 + ["verified"] * 5 + ["out"] * 4 + ["queued"] * 4 + ["drafted"] * 3 + ["filed"] * 4
                + ["accepted"] * 1 + ["rejected"] * 2 + ["withdrawn"] * 1 + ["replied"] * 1 + ["meeting"] * 1) if prog else \
               (["screened"] * 6 + ["verified"] * 5 + ["out"] * 3 + ["queued"] * 4 + ["drafted"] * 3 + ["draft_ready"] * 3
                + ["contacted"] * 4 + ["no_reply"] * 3 + ["replied"] * 3 + ["meeting"] * 3 + ["passed"] * 3
                + ["term_sheet"] * 1 + ["withdrawn"] * 1 + ["accepted"] * 1)
        status = rng.choice(pool)
        created = d(rng.randint(1, 120))
        claims = {"thesis": {"v": rng.choice(["ai", "developer tools", "data", "fintech", "climate"]), "stamp": rng.choice(["✅", "3P", "📋"]),
                             "src": f"https://{key}.example", "at": d(rng.randint(0, 40))}}
        rec = {"key": key, "kind": kind, "name": name, "url": f"https://{key}.example", "people": [], "claims": claims, "verdicts": {},
               "overrides": {}, "fit": rng.randint(40, 95) if status != "screened" else None,
               "tier": rng.choice([1, 2, 3, 4]) if status not in ("screened", "out") else None,
               "why": rng.choice(["thesis names what we build", "a portfolio neighbour", "a dated cohort door", "a warm path"]),
               "status": status, "origin": [rng.choice(["directory", "pasted list", "brain", "news"])], "origin_text": [],
               "apps": [], "drafts": [], "next": None, "created": created, "updated": d(rng.randint(0, 10)), "angle": ""}
        if status == "out":
            rec["out_reason"] = rng.choice(["floor: cheque below the minimum", "geo: us only", "thesis: consumer"])
        if prog and deadlines < 40:
            rec["claims"]["deadline"] = {"v": (BASE + _dt.timedelta(days=rng.randint(2, 60))).isoformat(), "stamp": "✅", "src": rec["url"], "at": d(rng.randint(0, 5))}
            deadlines += 1
        if stale < 25 and status not in ("screened", "out"):
            rec["claims"]["status_open"] = {"v": "open", "stamp": "✅", "src": rec["url"], "at": d(rng.randint(20, 60))}   # past DATED_DAYS
            stale += 1
        if due < 12 and status in ("contacted", "no_reply", "filed"):
            rec["next"] = {"action": "follow-up", "due": d(rng.randint(0, 3))}
            due += 1
        if apps < 20 and status in ("drafted", "filed", "accepted", "rejected") and prog:
            day = d(rng.randint(1, 30))
            rec["apps"].append(f"applications/{day}/{key}")
            apps += 1
        if drafts < 15 and status in ("draft_ready", "contacted", "no_reply", "replied", "meeting"):
            rec["drafts"].append({"path": f"outreach/{d(rng.randint(1, 30))}/{key}.md", "channel": rng.choice(["email", "intro", "form"]), "at": d(rng.randint(1, 30))})
            drafts += 1
        if not prog and status in ("queued", "drafted", "draft_ready", "contacted"):
            rec["angle"] = rng.choice(["their new fund + our verified traction", "a portfolio gap we fill", "the partner's own post"])
        recs.append(rec)
        # events: the path from screened to the current status
        path = ["screened"]
        chain = ["verified", "queued", "drafted", "draft_ready", "contacted", "no_reply", "replied", "meeting", "term_sheet"] if not prog \
            else ["verified", "queued", "drafted", "filed", "replied", "meeting", "accepted"]
        if status in chain:
            path += chain[: chain.index(status) + 1]
        elif status in ("out", "passed", "rejected", "withdrawn", "accepted", "term_sheet"):
            path += [rng.choice(chain[:3]), status]
        when = _dt.date.fromisoformat(created)
        prev = None
        for st in path:
            evs.append({"key": key, "from": prev, "to": st, "by": "founder" if st == "contacted" else "agent", "at": when.isoformat() + "T09:00:00", "note": ""})
            prev = st
            when = min(BASE, when + _dt.timedelta(days=rng.randint(1, 6)))
    out = FIX / "fundraising-sim"
    write_jsonl(out / "targets.jsonl", recs)
    write_jsonl(out / "events.jsonl", evs)
    (out / "lessons.md").write_text("# Lessons\n\n- 2026-10-01 — cold forms to syndicates never answered; prefer warm intros there\n", encoding="utf-8")
    return len(recs), len(evs)


# ---------------------------------------------------------------- sales
SALES_STAGES = ["lead", "researched", "sequenced", "contacted", "replied", "meeting", "trial", "won", "lost", "nurture", "out"]


def sales(rng):
    accs, evs = [], []
    pool = ["lead"] * 30 + ["researched"] * 18 + ["sequenced"] * 15 + ["contacted"] * 20 + ["replied"] * 10 + ["meeting"] * 8 \
        + ["trial"] * 6 + ["won"] * 3 + ["lost"] * 4 + ["nurture"] * 4 + ["out"] * 2
    rng.shuffle(pool)
    sends = replies = 0
    for i in range(120):
        org = f"{rng.choice(WORDS)} {rng.choice(ORGS)}"
        key = org.lower().replace(" ", "")
        stage = pool[i]
        first = d(rng.randint(1, 60))
        market = rng.choice(CITIES)[0]
        contact = rng.choice(PEOPLE)
        a = {"key": key, "name": org, "domain": f"{key}.example", "stage": stage, "first_seen": first, "last_seen": d(rng.randint(0, 5)),
             "stage_since": d(rng.randint(0, 20)), "sources": [rng.choice(["careers board", "news", "directory", "brain", "event"])],
             "signals": [{"kind": rng.choice(["hiring", "funding", "exec_hire", "migration", "intent"]), "what": "a public signal", "url": f"https://{key}.example/news", "seen": d(rng.randint(0, 20))}],
             "contacts": [{"name": contact, "role": rng.choice(["VP Operations", "Head of RevOps", "COO", "CTO"]), "channels": rng.sample(["email", "linkedin_dm", "form"], 2),
                           "email": f"{contact.split()[0].lower()}@{key}.example", "email_source": rng.choice(["public-page", "brain", "pattern-unverified"]), "role_source": f"https://{key}.example/team"}],
             "markets": [market], "origin": rng.choice(["revival", "warm", "dormant", "intro", "cold"]), "segment": rng.choice(["mid-market ops", "data teams", "agencies", "fintech"]),
             "score": rng.randint(30, 95), "fit": rng.randint(30, 95), "warmth": round(rng.random(), 2), "reach": rng.choice(["warm", "intro", "public", "form", "handoff"]),
             "why": "hiring for the role we help", "strategy": rng.choice(["try", "use", "buy", "partner", ""]), "angle": "", "offer": "", "channels": []}
        if a["strategy"]:
            a["angle"] = rng.choice(["their hiring post → our onboarding", "a lost deal worth reopening", "a public question we answer"])
            a["offer"] = {"try": "Free pilot on one export", "use": "Done-for-you onboarding", "buy": "Team plan", "partner": "Integration partnership"}[a["strategy"]]
            a["channels"] = rng.sample(["intro", "email", "form", "linkedin_dm"], 2)
        if stage == "out":
            a["knocked_out"] = "a competitor's customer"
        if stage == "lead" and a["score"] < 60:
            a["knocked_out"] = ""
        accs.append(a)
        order = ["lead", "researched", "sequenced", "contacted", "replied", "meeting", "trial", "won"]
        if stage in order:
            path = order[: order.index(stage) + 1]
        else:
            path = ["lead", "researched", stage]
        when = _dt.date.fromisoformat(first)
        prev = None
        for st in path[1:]:
            evs.append({"kind": "stage", "account": key, "from": prev or "lead", "to": st, "by": "user" if st in ("won", "lost") else "agent", "ts": when.isoformat() + "T08:30:00"})
            prev = st
            when = min(BASE, when + _dt.timedelta(days=rng.randint(1, 5)))
        if stage in ("contacted", "replied", "meeting", "trial", "won", "lost") and sends < 60:
            for step in (1, 2):
                if sends >= 60:
                    break
                evs.append({"kind": "sent", "account": key, "contact": contact, "channel": rng.choice(["email", "email", "form", "linkedin_dm"]),
                            "ts": d(rng.randint(0, 25)) + "T10:00:00", "step": step, "batch": f"b{rng.randint(1, 9)}", "message_id": f"<sim-{key}-{step}@example>"})
                sends += 1
        if stage in ("replied", "meeting", "trial", "won") and replies < 14:
            evs.append({"kind": "replied", "account": key, "contact": contact, "channel": "email", "ts": d(rng.randint(0, 10)) + "T15:00:00",
                        "reply_class": rng.choice(["interested", "meeting-ask", "not-now", "question"])})
            replies += 1
        if stage in ("meeting", "trial", "won"):
            evs.append({"kind": "meeting_booked", "account": key, "contact": contact, "ts": d(rng.randint(0, 8)) + "T16:00:00"})
    evs.sort(key=lambda e: e["ts"])
    out = FIX / "sales-sim"
    write_jsonl(out / "accounts.jsonl", accs)
    write_jsonl(out / "events.jsonl", evs)
    (out / "last_shortlist.json").write_text(json.dumps({"floor": 60, "target": 10, "merged_at": BASE.isoformat(),
                                                         "shortlist": [{"key": a["key"], "name": a["name"], "score": a["score"], "markets": a["markets"], "reach": a["reach"],
                                                                        "origin": a["origin"], "new": True, "why": a["why"]} for a in accs if a["stage"] == "lead" and a["score"] >= 60][:10]},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
    return len(accs), len(evs)


# ---------------------------------------------------------------- travel
def travel(rng):
    out = FIX / "travel-sim"
    sys.path.insert(0, str(HERE.parent.parent.parent / "plugins" / "travel-planner" / "skills" / "trip-planner" / "scripts"))
    import itinerary as itin  # noqa: E402
    layer = out / "47-travel"
    statuses = ["planned", "planned", "shopped", "booked", "done", "shopped"]
    trips = []
    for n, (city, cc, lat, lng) in enumerate(CITIES + [CITIES[0]]):
        tid = f"{city.lower()}-{'spring' if n < 3 else 'autumn'}-{n + 1}"
        it = {"schema": itin.SCHEMA, "trip_id": tid, "title": f"{city} {'in spring' if n < 3 else 'in autumn'}", "status": statuses[n],
              "created": d(60 - n * 5) + "T09:00:00", "updated": d(2) + "T09:00:00",
              "window": {"earliest": "", "latest": "", "nights": 3, "flex_days": 0}, "currency": "EUR", "budget": {},
              "travelers": [{"id": "me", "label": "me"}], "stops": [], "legs": [], "pois": [], "routes": []}
        start = BASE + _dt.timedelta(days=(n - 2) * 20)     # one past, one current-ish, the rest upcoming
        it["stops"].append({"id": "s1", "place": city, "country": cc, "lat": lat, "lng": lng, "role": "base", "arrive": start.isoformat(),
                            "depart": (start + _dt.timedelta(days=3)).isoformat(), "nights": 3, "why": "saved, never visited", "days": [], "stay": {}})
        it["window"]["earliest"], it["window"]["latest"] = start.isoformat(), (start + _dt.timedelta(days=3)).isoformat()
        for k in range(3):
            it["pois"].append({"id": f"p{k + 1}", "stop": "s1", "name": f"{rng.choice(WORDS)} {rng.choice(['Cafe', 'Museum', 'Market'])}",
                               "kind": rng.choice(["cafe", "museum", "market"]), "lat": lat + rng.uniform(-0.02, 0.02), "lng": lng + rng.uniform(-0.02, 0.02),
                               "why": "the kind of place you love", "from_brain": False, "brain_note": "", "rating": None, "price_band": "", "booking": None})
        it["stops"][0]["days"] = [{"date": start.isoformat(), "route": "", "items": ["p1", "p2"]},
                                  {"date": (start + _dt.timedelta(days=1)).isoformat(), "route": "", "items": ["p3"]}]
        it["stops"][0]["stay"] = {}
        p = layer / "trips" / tid / "itinerary.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(it, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        p.with_name("map.geojson").write_text(json.dumps(itin.to_geojson(it), ensure_ascii=False) + "\n", encoding="utf-8")
        trips.append(tid)
    picks = []
    slots = ["coffee", "meal", "activity", "event", "wildcard", "social"]
    for day in range(10):
        date = d(9 - day)
        city, cc, lat, lng = CITIES[0]
        for k in range(4):
            n = len([x for x in picks if x["date"] == date]) + 1
            st = "suggested" if day == 9 else rng.choice(["expired", "expired", "saved", "went", "went", "loved", "not_for_me"])
            picks.append({"id": f"p-{date}-{n}", "date": date, "city": city, "slot": slots[(day + k) % len(slots)],
                          "name": f"{rng.choice(WORDS)} {rng.choice(['Cafe', 'Bistro', 'Gallery', 'Market', 'Bar', 'Garden'])}",
                          "kind": rng.choice(["cafe", "restaurant", "museum", "market", "bar", "sight"]), "category": "", "lat": lat + rng.uniform(-0.03, 0.03),
                          "lng": lng + rng.uniform(-0.03, 0.03), "distance_km": round(rng.uniform(0.3, 5.5), 1), "why": rng.choice(["saved, never visited", "you rated it ★5", "no brain signal — web only"]),
                          "from_brain": k % 2 == 0, "brain_note": "", "source": "brain" if k % 2 == 0 else "web", "url": "" if k % 2 == 0 else "https://venue.example/page",
                          "seen_at": "" if k % 2 == 0 else date + "T08:00", "status": st, "updated": date + "T08:10:00",
                          "history": ([] if st == "suggested" else [{"from": "suggested", "to": st if st != "loved" else "went", "at": date + "T20:00:00", "by": "user"}]
                                      + ([{"from": "went", "to": "loved", "at": date + "T21:00:00", "by": "user"}] if st == "loved" else []))})
    write_jsonl(out / "picks.jsonl", picks)
    write_jsonl(out / "outcomes.jsonl", [{"trip_id": t, "kind": k, "ref": "", "note": "", "at": d(30) + "T09:00:00"}
                                         for t, s in zip(trips, statuses) for k in (["planned"] + (["shopped"] if s in ("shopped", "booked", "done") else [])
                                                                                     + (["booked"] if s in ("booked", "done") else []) + (["travelled"] if s == "done" else []))])
    return len(trips), len(picks)


# ---------------------------------------------------------------- jobs
def jobs(rng):
    rows, seen = [], {}
    statuses = ["applied"] * 30 + ["filled"] * 6 + ["not_started"] * 4 + ["handoff_portal"] * 5 + ["drafted_linkedin"] * 3 + ["skipped_knockout"] * 5 + ["skipped_walled"] * 3 + ["prior_external"] * 4
    rng.shuffle(statuses)
    results = ["", "", "", "screen", "interview", "rejected", "", "offer"]
    for i in range(60):
        org = rng.choice(ORGS)
        role = rng.choice(["Head of Engineering", "VP Engineering", "CTO", "Engineering Director", "Head of Platform"])
        key = f"{org.lower().replace(' ', '-')}-{role.lower().replace(' ', '-')}-{i}"
        st = statuses[i]
        r = {"job_key": key, "company": org, "role": role, "status": st, "date": d(rng.randint(0, 40)), "url": f"https://jobs.example.com/{key}",
             "portal": rng.choice(["greenhouse", "lever", "ashby", "workday", "linkedin"]), "market": rng.choice(["Lisbon", "Madrid", "Berlin", "remote-EU"]),
             "archetype": rng.choice(["platform-leader", "ic-architect", "cto"]), "source": rng.choice(["careers board", "company registry", "brain", "explore"]),
             "score": rng.randint(60, 96), "location": rng.choice(["Lisbon", "Madrid", "Berlin", "Remote"]), "comp": ""}
        if st == "applied":
            res = rng.choice(results)
            if res:
                r["result"], r["result_date"] = res, d(rng.randint(0, 10))
        rows.append(r)
    for i in range(40):
        org = rng.choice(ORGS)
        role = rng.choice(["Head of Data", "Engineering Lead", "Director of Engineering", "Staff Engineer"])
        seen[f"{org.lower()}|{role.lower().replace(' ', '-')}-{i}"] = {"title": role, "company": org, "score": rng.randint(40, 95), "first_seen": d(rng.randint(0, 20)),
                                                                         "url": f"https://jobs.example.com/seen/{i}", "source": rng.choice(["careers board", "explore", "brain"])}
    out = FIX / "jobs-sim"
    write_jsonl(out / "outcomes.jsonl", rows)
    out.joinpath("seen.json").write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "reports").mkdir(exist_ok=True)
    (out / "reports" / f"{BASE.isoformat()}.md").write_text("# Shortlist\n\n| # | Company | Role | Score |\n|---|---|---|---|\n| 1 | Acme | CTO | 88 |\n| 2 | Globex | VP Engineering | 81 |\n", encoding="utf-8")
    return len(rows), len(seen)


def main():
    rng = random.Random(42)
    print("fundraising-sim:", fundraising(rng))
    print("sales-sim:", sales(rng))
    print("travel-sim:", travel(rng))
    print("jobs-sim:", jobs(rng))
    return 0


if __name__ == "__main__":
    sys.exit(main())
