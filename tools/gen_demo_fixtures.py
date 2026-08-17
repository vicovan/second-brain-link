#!/usr/bin/env python3
"""gen_demo_fixtures.py — deterministic generator for the shipped demo exports.

The demo brains that ship in web Studio, desktop Studio and the mobile app are built
from two synthetic export archives: `data/personal/john/` and `data/company/acme/`.
Those archives are bulky and were previously hand-edited, which let four copies of
them drift apart. This script is the single source of truth: it regenerates both
archives byte-identically from a fixed seed, so the demo can always be rebuilt.

    python3 tools/gen_demo_fixtures.py                  # -> data/  (refuses to clobber)
    python3 tools/gen_demo_fixtures.py --out /tmp/demo  # -> anywhere
    python3 tools/gen_demo_fixtures.py --force          # overwrite an existing target

Design constraints this script is written against (all verified in the engine):

  * Identity resolution is EXACT normalized-name only (`nk()` in sources/common.py:91)
    — no fuzzy matching exists. A person appearing in several sources must use a
    byte-identical name string or they silently become duplicate nodes.
  * `strength` is derived from message-signal COUNT (>=20 -> 5, >=10 -> 4, >=5 -> 3,
    else 2) and `works_at` edge weight is strength/5. Bright top-tier edges have to be
    earned with >=20 message rows.
  * Quarantine is the live union of all 25 adapters' lists, matched on the normalized
    filename, so generic names (contacts / email / description / security / block /
    mute / userdata) vanish silently in ANY source folder.
  * A "person" whose name matches EMAIL_RE is dropped outright.
  * Only people, organizations, places, posts, purchases, services and company
    deals/campaigns produce one note per item. Everything else collapses to a single
    note, so node count comes from those buckets.

Synthetic-data policy: RFC-2606 reserved domains only, no real people, no real
addresses. Message bodies are never read by the engine; the canary strings here exist
so the test suite can assert that.
"""
import argparse
import json
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

SEED = 0xC0FFEE
TODAY = date(2026, 8, 17)

# --------------------------------------------------------------------------- pools
FIRST = """Ada Alan Grace Priya Dana Maya Jonas Omar Ivy Noah Lena Kofi Ruth Eli Nora
Tom Hana Sam Leo Iris Mateo Zara Felix Anya Rhys Tara Yusuf Clara Milo Sana Oscar June
Arto Nadia Pablo Freya Idris Vera Hugo Amara Bo Cleo Dmitri Esme Farid Gia Hector Inez
Jonah Kira Luca Mira Nils Ola Pia Quinn Rosa Said Tessa Umi Vik Wren Xenia Yara Zeno
Bea Cato Dara Enzo Fay Gil Hedy Ines Jai Kian Lark Mona Nero Odile Piet Rune Selma Toma
Ulla Vidal Wanda Yosef Zola Bram Coral Dov Elif Gwen Halim Ilona Jarek Kaya Liem Marit
Nuno Oona Petra Rafa Suri Tomas Ugo Vesna Wilf Yannis Zuri""".split()
LAST = """Hopper Turing Lovelace Nair Reyes Chen Beck Diaz Kim Marsh Sato Patel Cohen
Alvarez Vance Ross Bauer Mensah Okafor Lindqvist Moreau Rossi Novak Haddad Silva Tanaka
Weber Dubois Costa Ivanov Nguyen Bergman Farkas Kowalski Duarte Ahmadi Blum Castillo
Doyle Eriksen Ferrari Gallo Holm Iqbal Jensen Klein Lombardi Mackay Nilsson Ortega
Pfeiffer Quintero Ramirez Sandberg Toth Ueda Vargas Wallace Yilmaz Zimmer Abara Boateng
Cardoso Delgado Espinoza Fontaine Grigoryan Halvorsen Imani Jaramillo Kaur Laurent
Maalouf Nakamura Olsen Pereira Rahman Salazar Thibault Undset Villanueva Wojcik Yakovlev
Zubair Bassett Cormier Drury Falk Guerra Hollis Ives Jonsson Keller Lund Mercier Norrell
Pike Renner Stahl Trevino Vogel Wexler""".split()

CITIES = [
    ("San Francisco", "US", 37.7749, -122.4194), ("London", "GB", 51.5074, -0.1278),
    ("Berlin", "DE", 52.52, 13.405), ("Lisbon", "PT", 38.7223, -9.1393),
    ("Amsterdam", "NL", 52.3676, 4.9041), ("Toronto", "CA", 43.6532, -79.3832),
    ("Singapore", "SG", 1.3521, 103.8198), ("Dublin", "IE", 53.3498, -6.2603),
    ("Barcelona", "ES", 41.3851, 2.1734), ("Copenhagen", "DK", 55.6761, 12.5683),
    ("Austin", "US", 30.2672, -97.7431), ("Zurich", "CH", 47.3769, 8.5417),
    ("Tallinn", "EE", 59.437, 24.7536), ("Warsaw", "PL", 52.2297, 21.0122),
    ("Melbourne", "AU", -37.8136, 144.9631), ("Nairobi", "KE", -1.2921, 36.8219),
]
VENUE_KINDS = ["cafe", "coworking", "venue", "office", "park", "bookshop", "lab"]
VENUE_WORDS = ["Ironwood", "Blue Harbour", "Northgate", "Old Mill", "Fern", "Copper",
               "Lantern", "Rivet", "Saltbox", "Quarry", "Beacon", "Verge", "Kiln",
               "Alder", "Foundry", "Meridian", "Tidewater", "Gasworks", "Pallas"]

# Hub organizations become the cells in the molecular view and the ring-1 hubs in the
# radial view (which needs >=2 `company` nodes and caps at HUB_CAP=12). Sizes are
# Zipf-ish on purpose: a dozen real hubs plus a long tail is what makes cells form
# instead of one uniform blob per folder.
JOHN_COMMUNITIES = [
    ("Acme Robotics", "employer", 44), ("Meridian Labs", "employer", 40),
    ("Bletchley Institute", "school", 36), ("Harbour Runners", "club", 32),
    ("Opencobot Collective", "oss", 30), ("Loopr Logistics", "employer", 26),
    ("Verge Freight", "client", 20), ("Saltbox Foods", "client", 18),
    ("Kiln Ceramics", "client", 16), ("Tidewater Marine", "client", 14),
    ("Alder Health", "client", 12), ("Analytical Engines", "peer", 10),
    # Northwind Capital is DELIBERATELY a one-person org: the guided tour says
    # "she is the only investor in your network", and that has to be literally
    # true in the data. See PINNED below.
    ("Northwind Capital", "investor", 1),
]

# ---------------------------------------------------------------- the tour cast
# The guided Studio tour (second-brain-link-web/src/lib/tour/) narrates specific
# facts about specific people — role, employer, relationship strength. Those
# assertions must be TRUE in the generated vault or the tour lies to the viewer.
# Pinning them here makes the fixtures serve the script, rather than rewriting the
# script every time the demo is reseeded.
#
# `msgs` drives `strength` (>=20 -> 5, >=10 -> 4, >=5 -> 3, else 2) and
# `status` ("warm" when >=5 messages, "cold"/"dormant" when few + last contact
# before 2024). `age` shifts the message dates back so a relationship reads cold.
#
# ROLE GOTCHA: `Collector.add_person` is first-non-empty-wins (common.py:435) and
# adapters run alphabetically, so facebook / github / instagram all resolve BEFORE
# linkedin and stamp their constant role ("facebook friend", "instagram follower").
# The tour asserts real job titles, so the pinned cast may only carry extra sources
# that sort AFTER "linkedin" (strava, whatsapp, x) — those supply no role, leaving
# the LinkedIn Position authoritative.
PINNED = {
    # "your strongest contact" must be UNIQUE — Grace is the only person in the
    # whole vault allowed to reach strength 5 (see MAX_MSGS_OTHERS).
    "Grace Hopper": dict(company="Acme Robotics", role="VP Engineering",
                         msgs=26, age=(5, 120), extra=["strava", "whatsapp"]),
    # "Partner at Northwind Capital… the relationship is cold"
    "Priya Nair": dict(company="Northwind Capital", role="Partner",
                       msgs=2, age=(1180, 1400), extra=[]),
    # "Founder at Analytical Engines… a founder peer who has raised before"
    "Ada Lovelace": dict(company="Analytical Engines", role="Founder",
                         msgs=8, age=(30, 400), extra=["strava"]),
    "Alan Turing": dict(company="Meridian Labs", role="Principal Scientist",
                        msgs=14, age=(10, 300), extra=["strava"]),
}
# Nobody except Grace may reach the >=20 threshold, so "strongest contact" is
# unambiguous in the data as well as in the narration.
MAX_MSGS_OTHERS = 19
# the long tail: many small orgs so `15-organizations` is a real layer, not 8 notes
TAIL_ORG_WORDS = ["Foundry", "Pallas", "Gasworks", "Beacon", "Ironwood", "Copper",
                  "Lantern", "Rivet", "Quarry", "Fern", "Alder", "Meridian", "Cobalt",
                  "Halyard", "Juniper", "Kestrel", "Larkspur", "Mistral", "Nimbus",
                  "Orchard", "Pewter", "Quill", "Rookery", "Sable", "Thistle",
                  "Umber", "Vellum", "Wicker", "Yarrow", "Zephyr"]
TAIL_ORG_KINDS = ["Systems", "Works", "Robotics", "Analytics", "Freight", "Foods",
                  "Marine", "Health", "Metals", "Energy", "Rail", "Ceramics"]
ACME_DEPTS = [("Engineering", 72), ("Sales", 48), ("Support", 34),
              ("Operations", 26), ("Design", 20)]
ACME_CUSTOMERS = ["Brightline", "Northwind Mutual", "Meridian Labs", "Verge Freight",
                  "Saltbox Foods", "Kiln Ceramics", "Tidewater Marine", "Alder Health",
                  "Foundry Metals", "Pallas Insurance", "Gasworks Energy", "Beacon Rail"]
ACME_VENDORS = ["Ironwood Cloud", "Copper Analytics", "Lantern Support Desk",
                "Rivet CI", "Quarry Storage", "Fern Design Co"]

SKILLS = ["Robotics", "Control Systems", "Product Strategy", "Distributed Systems",
          "Computer Vision", "Fleet Ops", "Safety Engineering", "Simulation",
          "Embedded Linux", "Motion Planning", "Manufacturing", "Pricing"]
TOPICS = ["collaborative robotics", "warehouse automation", "sensor fusion",
          "industrial safety", "supply chain", "edge compute", "battery systems",
          "human factors", "open hardware", "trail running", "espresso", "bouldering",
          "field recording", "letterpress", "cartography"]
PRODUCTS = ["Torque Wrench Set", "Lidar Module", "Servo Driver", "Carbon Tripod",
            "Trail Shoes", "Espresso Grinder", "Mechanical Keyboard", "Cable Loom Kit",
            "Bench Multimeter", "Notebook (A5)", "Standing Desk Mat", "Headlamp",
            "Rain Shell", "Soldering Station", "Caliper", "Label Printer"]


def d(offset_days):
    """A date offset from TODAY, ISO. Negative = past."""
    return (TODAY + timedelta(days=offset_days)).isoformat()


def li_date(offset_days):
    """LinkedIn 'Connected On' style: 15 Mar 2021."""
    x = TODAY + timedelta(days=offset_days)
    return f"{x.day:02d} {x.strftime('%b')} {x.year}"


class World:
    """The synthetic world, built once so both brains agree on shared entities."""

    def __init__(self, rnd):
        self.r = rnd
        self.used_names = set()
        self.john_people = []   # dicts: name, company, role, community, strength_msgs
        self.acme_people = []
        self.build()

    def name(self):
        for _ in range(400):
            n = f"{self.r.choice(FIRST)} {self.r.choice(LAST)}"
            if n not in self.used_names:
                self.used_names.add(n)
                return n
        raise RuntimeError("name pool exhausted")

    def build(self):
        r = self.r
        # --- fixed cast: these names are referenced by the website and tutorials and
        # must keep working. Byte-identical strings are what make cross-source and
        # cross-brain merging happen at all.
        for n in ("Grace Hopper", "Alan Turing", "Ada Lovelace", "Priya Nair",
                  "Dana Reyes", "Maya Chen", "Jonas Beck", "John Carter"):
            self.used_names.add(n)

        # ---- John's network, grouped into communities so cells form -------------
        anchors = {
            "Acme Robotics": ["Grace Hopper"],
            "Meridian Labs": ["Alan Turing"],
            "Analytical Engines": ["Ada Lovelace"],
            # size-1 org: Priya is its only member, so "the only investor" holds
            "Northwind Capital": ["Priya Nair"],
        }
        roles = ["Engineer", "Head of Ops", "Researcher", "Designer", "Founder",
                 "Partner", "Technician", "Coach", "Maintainer", "Analyst"]

        def add_person(nm, org, kind, rank):
            pin = PINNED.get(nm)
            if pin:
                # The tour asserts these facts verbatim — never randomise them.
                self.john_people.append({
                    "name": nm, "company": pin["company"], "kind": kind,
                    "role": pin["role"], "msgs": pin["msgs"],
                    "age": pin["age"],
                    "since": r.randint(-2000, -400),
                    "extra": list(pin["extra"]),
                })
                return
            # rank drives message volume -> strength (>=10 -> 4, >=5 -> 3) -> the
            # works_at edge weight. Capped below 20 so strength 5 stays Grace's alone.
            msgs = (r.randint(14, MAX_MSGS_OTHERS) if rank < 2 else
                    r.randint(10, 15) if rank < 6 else
                    r.randint(5, 9) if rank < 14 else r.randint(0, 4))
            # Multi-source presence is the point of identity resolution: the SAME
            # byte-identical name in several exports must merge to one note. `nk()`
            # is exact-match only, so the strings have to agree exactly.
            extra = r.sample(["facebook", "instagram", "github", "strava"],
                             r.choice([0, 0, 1, 1, 1, 2, 2, 3]))
            self.john_people.append({
                "name": nm, "company": org, "kind": kind,
                "role": r.choice(roles), "msgs": msgs,
                "age": (5, 700),
                "since": r.randint(-2000, -60),
                "extra": extra,
            })

        for org, kind, size in JOHN_COMMUNITIES:
            fixed = anchors.get(org, [])
            for i in range(size):
                add_person(fixed[i] if i < len(fixed) else self.name(), org, kind, i)

        # the long tail of small orgs — this is what turns 15-organizations from an
        # 8-note stub into a real layer, and gives the cells a Zipf shape
        self.tail_orgs = []
        for w in TAIL_ORG_WORDS:
            for k in r.sample(TAIL_ORG_KINDS, r.choice([1, 1, 2])):
                self.tail_orgs.append(f"{w} {k}")
        for org in self.tail_orgs:
            for i in range(r.randint(1, 5)):
                add_person(self.name(), org, "client", 20 + i)
        # deliberate bridge people: in a second community too (multi-context)
        self.bridges = [p["name"] for p in self.john_people[:80]][::17][:6]

        # ---- Acme's people ------------------------------------------------------
        dept_anchor = {"Engineering": ["Grace Hopper", "Alan Turing", "Jonas Beck"],
                       "Sales": ["Dana Reyes", "Maya Chen"]}
        for dept, size in ACME_DEPTS:
            fixed = dept_anchor.get(dept, [])
            for i in range(size):
                nm = fixed[i] if i < len(fixed) else self.name()
                self.acme_people.append({
                    "name": nm, "dept": dept,
                    "role": r.choice(["Engineer", "Senior Engineer", "Account Executive",
                                      "Support Lead", "Designer", "Ops Manager",
                                      "Solutions Architect", "Analyst"]),
                    "msgs": r.randint(20, 40) if i < 3 else
                            r.randint(10, 19) if i < 9 else
                            r.randint(2, 9),
                })
        # customer-side contacts (their own orgs -> more org nodes + member_of)
        self.customer_contacts = []
        for co in ACME_CUSTOMERS:
            for _ in range(r.randint(7, 13)):
                self.customer_contacts.append({"name": self.name(), "company": co,
                                               "role": r.choice(["Buyer", "Plant Manager",
                                                                 "CTO", "Ops Lead",
                                                                 "Procurement"])})
        # Priya Nair and John Carter appear in BOTH brains -> _correlations/
        self.acme_people.append({"name": "Priya Nair", "dept": "Operations",
                                 "role": "Board Advisor", "msgs": 12})
        self.acme_people.append({"name": "John Carter", "dept": "Engineering",
                                 "role": "Technical Advisor", "msgs": 26})

        # ---- places -------------------------------------------------------------
        # Places and posts are leaf-only in this engine (nothing links to them), so
        # they land as degree-0 halo dots in the cellular view. Keep them present for
        # the map view and the voice layer, but well below the people count.
        self.places = []
        for i in range(112):
            city, cc, lat, lng = r.choice(CITIES)
            self.places.append({
                "name": f"{r.choice(VENUE_WORDS)} {r.choice(VENUE_KINDS).title()} {i + 1}",
                "city": city, "cc": cc,
                "lat": round(lat + r.uniform(-0.09, 0.09), 5),
                "lng": round(lng + r.uniform(-0.09, 0.09), 5),
                "kind": r.choice(["saved", "reviewed", "check-in"]),
                "date": d(-r.randint(20, 900)),
            })
        self.acme_sites = []
        for i, co in enumerate(ACME_CUSTOMERS + ACME_VENDORS):
            city, cc, lat, lng = CITIES[i % len(CITIES)]
            self.acme_sites.append({"name": f"{co} — {city} site", "city": city,
                                    "lat": round(lat + r.uniform(-0.05, 0.05), 5),
                                    "lng": round(lng + r.uniform(-0.05, 0.05), 5)})


# --------------------------------------------------------------------------- io
def w_text(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def w_json(root, rel, obj):
    w_text(root, rel, json.dumps(obj, ensure_ascii=False, indent=1))


def csv_rows(header, rows):
    out = [",".join(header)]
    for row in rows:
        cells = []
        for c in row:
            s = "" if c is None else str(c)
            cells.append('"' + s.replace('"', '""') + '"' if ("," in s or '"' in s) else s)
        out.append(",".join(cells))
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------- personal
def gen_john(root, W):
    r, P = W.r, W.john_people
    li = "linkedin"

    # Connections.csv keeps LinkedIn's real "Notes:" preamble — the reader skips it,
    # and shipping it proves the preamble handling works.
    conns = P
    rows = [(p["name"].split()[0], " ".join(p["name"].split()[1:]),
             f"https://www.linkedin.com/in/{p['name'].split()[0].lower()}{i}",
             "", p["company"], p["role"], li_date(p["since"]))
            for i, p in enumerate(conns)]
    w_text(root, f"{li}/Connections.csv",
           'Notes:\n"When exporting your connection data, you may notice that some of the '
           'email addresses are missing. You will only see email addresses for connections '
           'who have allowed their connections to see or download their email address."\n\n'
           + csv_rows(["First Name", "Last Name", "URL", "Email Address", "Company",
                       "Position", "Connected On"], rows))

    w_text(root, f"{li}/Profile.csv", csv_rows(
        ["First Name", "Last Name", "Headline", "Geo Location", "Industry", "Summary"],
        [("John", "Carter", "Founder & CEO at Acme Robotics", "San Francisco",
          "Robotics", "Building collaborative robots for small manufacturers.")]))
    w_text(root, f"{li}/Positions.csv", csv_rows(
        ["Company Name", "Title", "Description", "Location", "Started On", "Finished On"],
        [("Acme Robotics", "Founder & CEO", "Collaborative robots for small manufacturers",
          "San Francisco", "Jan 2020", ""),
         ("Meridian Labs", "Director of Product", "Autonomy platform", "London",
          "Feb 2017", "Dec 2019"),
         ("Loopr Logistics", "Head of Product", "Warehouse automation line", "London",
          "Mar 2014", "Jan 2017")]))
    w_text(root, f"{li}/Skills.csv", csv_rows(["Name"], [(s,) for s in SKILLS]))
    w_text(root, f"{li}/Education.csv", csv_rows(
        ["School Name", "Degree Name", "Start Date", "End Date", "Notes"],
        [("Bletchley Institute", "MSc Robotics", "2010", "2012", "Autonomy lab")]))
    w_text(root, f"{li}/Certifications.csv", csv_rows(
        ["Name"], [("Functional Safety (TUV)",), ("ROS 2 Developer",)]))
    w_text(root, f"{li}/Languages.csv", csv_rows(
        ["Name"], [("English",), ("Portuguese",)]))

    # messages.csv — the ONLY lever on `strength`, hence on works_at edge weight.
    mrows = []
    for p in P:
        lo, hi = p.get("age", (5, 700))
        for k in range(p["msgs"]):
            mrows.append((f"c{abs(hash(p['name'])) % 9999}", p["name"], p["name"],
                          "", "John Carter",
                          f"{d(-r.randint(lo, hi))} 09:{k % 60:02d}:00 UTC", "",
                          "private message body not imported"))
    w_text(root, f"{li}/messages.csv", csv_rows(
        ["CONVERSATION ID", "CONVERSATION TITLE", "FROM", "SENDER PROFILE URL", "TO",
         "DATE", "SUBJECT", "CONTENT"], mrows))

    orgs = sorted({p["company"] for p in P})
    w_text(root, f"{li}/Company Follows.csv",
           csv_rows(["Organization"], [(o,) for o in orgs]))
    w_text(root, f"{li}/Job Applications.csv", csv_rows(
        ["Company Name", "Job Title", "Application Date"],
        [(o, "Advisor", d(-r.randint(60, 500))) for o in orgs[:6]]))
    w_text(root, f"{li}/Search Queries.csv", csv_rows(
        ["Search Query", "Time"],
        [(t, d(-r.randint(10, 400))) for t in TOPICS]))
    w_text(root, f"{li}/Recommendations_Received.csv", csv_rows(
        ["First Name", "Last Name", "Text"],
        [(p["name"].split()[0], " ".join(p["name"].split()[1:]),
          "Steady under pressure and unusually clear about tradeoffs.")
         for p in P[:6]]))
    w_text(root, f"{li}/Recommendations_Given.csv", csv_rows(
        ["First Name", "Last Name", "Text"],
        [(p["name"].split()[0], " ".join(p["name"].split()[1:]),
          "Shipped the hardest part of the platform and made it look calm.")
         for p in P[6:11]]))
    w_text(root, f"{li}/Shares.csv", csv_rows(
        ["Date", "ShareCommentary", "ShareLink"],
        [(d(-r.randint(5, 500)),
          f"Notes on {r.choice(TOPICS)} — what changed for us this quarter.",
          f"https://www.linkedin.com/feed/update/{i}") for i in range(34)]))
    w_text(root, f"{li}/Events.csv", csv_rows(
        ["Event Name", "Date"],
        [(f"{r.choice(VENUE_WORDS)} Robotics Meetup {i}", d(-r.randint(20, 600)))
         for i in range(14)]))
    w_text(root, f"{li}/Inferences_about_you.csv", csv_rows(
        ["Category", "Inference"],
        [(t, f"Interested in {t}") for t in TOPICS]))
    w_text(root, f"{li}/Ad_Targeting.csv", csv_rows(
        ["Segment"], [(f"{t} buyers",) for t in TOPICS]))
    w_text(root, f"{li}/Learning.csv", csv_rows(
        ["Content Title"], [(f"{s} fundamentals",) for s in SKILLS[:8]]))

    # ---- facebook (declarative mapping; nested paths are load-bearing) ----------
    fb = [p for p in P if "facebook" in p["extra"]]
    w_json(root, "facebook/connections/friends/your_friends.json",
           {"friends_v2": [{"name": p["name"],
                            "timestamp": int((TODAY - timedelta(days=-p["since"])).toordinal() * 86400)}
                           for p in fb]})
    w_json(root, "facebook/your_facebook_activity/posts/your_posts__check_ins__photos_and_videos_1.json",
           [{"timestamp": int((TODAY - timedelta(days=r.randint(5, 700))).toordinal() * 86400),
             "data": [{"post": f"Field notes on {r.choice(TOPICS)}."}]} for _ in range(24)])
    checkins = [p for p in W.places if p["kind"] == "check-in"]
    w_json(root, "facebook/your_facebook_activity/posts/check-ins.json",
           [{"timestamp": int((TODAY - timedelta(days=30)).toordinal() * 86400),
             "data": [{"place": {"name": p["name"],
                                 "coordinate": {"latitude": p["lat"], "longitude": p["lng"]}}}]}
            for p in checkins])
    w_json(root, "facebook/your_facebook_activity/pages/pages_you_liked.json",
           {"page_likes_v2": [{"name": f"{t.title()} Weekly"} for t in TOPICS]})
    w_json(root, "facebook/logged_information/other_logged_information/ads_interests.json",
           {"topics_v2": TOPICS})
    w_json(root, "facebook/ads_information/ad_preferences.json",
           {"label_values": [{"value": f"{t} enthusiasts"} for t in TOPICS]})
    w_json(root, "facebook/logged_information/search/your_search_history.json",
           {"searches_v2": [{"data": [{"text": t}]} for t in TOPICS]})
    w_json(root, "facebook/personal_information/profile_information/profile_information.json",
           {"profile_v2": {"name": {"full_name": "John Carter"},
                           "current_city": {"name": "San Francisco"}}})

    # ---- instagram --------------------------------------------------------------
    ig = [p for p in P if "instagram" in p["extra"]]
    w_json(root, "instagram/connections/followers_and_following/followers_1.json",
           [{"string_list_data": [{"value": p["name"],
                                   "href": f"https://instagram.com/{p['name'].split()[0].lower()}",
                                   "timestamp": 1700000000}]} for p in ig])
    w_json(root, "instagram/your_instagram_activity/media/posts_1.json",
           [{"title": f"{r.choice(VENUE_WORDS)} — {r.choice(TOPICS)}",
             "creation_timestamp": 1700000000 + i * 90000} for i in range(20)])
    w_json(root, "instagram/preferences/your_topics/your_topics.json",
           {"topics": [{"string_map_data": {"Name": {"value": t}}} for t in TOPICS]})
    w_json(root, "instagram/personal_information/personal_information/personal_information.json",
           {"profile_user": [{"string_map_data": {"Name": {"value": "John Carter"}}}]})

    # ---- google maps (GeoJSON: coordinates are [lng, lat]) ----------------------
    saved = [p for p in W.places if p["kind"] == "saved"]
    revd = [p for p in W.places if p["kind"] == "reviewed"]
    w_json(root, "google/Maps (your places)/Saved Places.json",
           {"type": "FeatureCollection", "features": [
               {"type": "Feature",
                "geometry": {"type": "Point", "coordinates": [p["lng"], p["lat"]]},
                "properties": {"location": {"name": p["name"], "country_code": p["cc"],
                                            "address": f"{p['city']}"},
                               "date": p["date"]}} for p in saved]})
    w_json(root, "google/Maps (your places)/Reviews.json",
           {"type": "FeatureCollection", "features": [
               {"type": "Feature",
                "geometry": {"type": "Point", "coordinates": [p["lng"], p["lat"]]},
                "properties": {"location": {"name": p["name"], "country_code": p["cc"]},
                               "five_star_rating_published": r.randint(3, 5),
                               "review_text_published": "Good light, quiet in the mornings.",
                               "date": p["date"]}} for p in revd]})

    # ---- amazon (the ONLY source of purchased_from edges) ----------------------
    w_text(root, "amazon/Retail.OrderHistory.1.csv", csv_rows(
        ["Order Date", "Product Name", "Total Owed", "Currency", "ASIN"],
        [(d(-r.randint(10, 720)), f"{r.choice(PRODUCTS)}",
          f"{r.randint(12, 480)}.00", "USD", f"B{i:09d}") for i in range(64)]))
    w_text(root, "amazon/Digital Items.csv", csv_rows(
        ["OrderDate", "ProductName", "OurPrice", "OurPriceCurrencyCode"],
        [(d(-r.randint(10, 700)), f"{r.choice(TOPICS).title()} (audiobook)",
          f"{r.randint(6, 30)}.00", "USD") for i in range(18)]))
    w_text(root, "amazon/Subscriptions.csv", csv_rows(
        ["ServiceProvider", "SubscriptionStartDate"],
        [("Prime", d(-900)), ("Audible", d(-640))]))

    # ---- lighter sources: breadth for the source filter ------------------------
    gh = [p for p in P if "github" in p["extra"]]
    # Emit the DISPLAY NAME, not a synthesised login: the engine treats the value
    # as a person name, so a login like "ada11" became a junk node instead of
    # merging into the existing person.
    w_json(root, "github/followers_000001.json",
           [{"login": p["name"], "user": p["name"]} for p in gh])
    w_json(root, "github/repositories_000001.json",
           [{"name": f"cobot-{w.lower()}", "description": f"{r.choice(TOPICS)} tooling"}
            for w in VENUE_WORDS[:10]])
    st = [p for p in P if "strava" in p["extra"]]
    w_text(root, "strava/followers.csv",
           csv_rows(["Name"], [(p["name"],) for p in st]))
    w_text(root, "strava/activities.csv", csv_rows(
        ["Activity Date", "Activity Name", "Activity Type"],
        [(d(-i * 3), f"Morning run — {r.choice(CITIES)[0]}", "Run") for i in range(40)]))
    w_text(root, "strava/clubs.csv", csv_rows(["Club Name"], [("Harbour Runners",)]))
    w_json(root, "spotify/StreamingHistory_music_0.json",
           [{"artistName": f"{r.choice(VENUE_WORDS)} Ensemble",
             "trackName": f"Movement {i}", "endTime": d(-i)} for i in range(50)])
    w_text(root, "reddit/posts.csv", csv_rows(
        ["date", "title", "body", "permalink"],
        [(d(-r.randint(5, 500)), f"Ask: {t}?", f"Notes on {t}.",
          f"https://reddit.example/r/robotics/{i}") for i, t in enumerate(TOPICS)]))
    w_text(root, "reddit/subscribed_subreddits.csv",
           csv_rows(["subreddit"], [("robotics",), ("automate",), ("trailrunning",)]))
    w_json(root, "youtube/subscriptions.json",
           [{"snippet": {"title": f"{t.title()} Channel"}} for t in TOPICS[:8]])
    w_json(root, "tiktok/user_data.json",
           {"Activity": {"Favorite Videos": {"FavoriteVideoList": [
               {"Date": d(-i * 7), "Link": f"https://tiktok.example/v/{i}"}
               for i in range(12)]}}})
    wa = [p for p in P if "whatsapp" in p["extra"]] or P[:12]
    w_text(root, "whatsapp/chat-with-harbour-runners.txt",
           "\n".join(f"[{d(-i)}, 07:1{i % 10}] {wa[i % len(wa)]['name']}: "
                     "message body not imported" for i in range(30)) + "\n")
    w_text(root, "x/tweets.js", "window.YTD.tweets.part0 = " + json.dumps(
        [{"tweet": {"created_at": d(-i * 5),
                    "full_text": f"Shipping notes: {r.choice(TOPICS)}."}}
         for i in range(30)], indent=1))


# ---------------------------------------------------------------------- company
def gen_acme(root, W):
    r, P = W.r, W.acme_people

    # ---- linkedin_company -------------------------------------------------------
    w_text(root, "linkedin_company/Organization Profile.csv", csv_rows(
        ["Organization Name", "Tagline", "Industry", "Location", "Description", "Url"],
        [("Acme Robotics", "Collaborative robots for small manufacturers", "Robotics",
          "San Francisco",
          "Acme Robotics builds collaborative robots and the fleet software around them.",
          "https://acme-robotics.example")]))
    w_text(root, "linkedin_company/EmployeeList.csv", csv_rows(
        ["First Name", "Last Name", "Title", "Profile Url", "Department"],
        [(p["name"].split()[0], " ".join(p["name"].split()[1:]), p["role"],
          f"https://www.linkedin.com/in/{p['name'].split()[0].lower()}{i}", p["dept"])
         for i, p in enumerate(P)]))
    w_text(root, "linkedin_company/PageFollowers.csv", csv_rows(
        ["Name", "Profile Url"],
        [(c["name"], f"https://www.linkedin.com/in/{c['name'].split()[0].lower()}c{i}")
         for i, c in enumerate(W.customer_contacts)]))
    w_text(root, "linkedin_company/Organization Posts.csv", csv_rows(
        ["Date", "Commentary", "Url"],
        [(d(-r.randint(5, 500)),
          f"How we think about {r.choice(TOPICS)} on the factory floor.",
          f"https://acme-robotics.example/posts/{i}") for i in range(70)]))
    w_text(root, "linkedin_company/FollowerDemographics.csv", csv_rows(
        ["Segment", "Followers"],
        [(f"{c} — manufacturing", r.randint(20, 400)) for c in ACME_CUSTOMERS]))

    # ---- google_workspace: users (depts) + calendars (the ONLY attended edges) --
    w_text(root, "google_workspace/GoogleWorkspace.csv", csv_rows(
        ["Organization Name", "Domain"], [("Acme Robotics", "acme-robotics.example")]))
    w_text(root, "google_workspace/users.csv", csv_rows(
        ["First Name", "Last Name", "Org Unit", "Title"],
        [(p["name"].split()[0], " ".join(p["name"].split()[1:]),
          f"/{p['dept']}", p["role"]) for p in P]))
    # attendees must be display names — the adapter drops anything email-shaped
    ev = []
    for i in range(90):
        att = r.sample([p["name"] for p in P], r.randint(3, 7))
        ev.append((f"{r.choice(['Design review', 'Fleet sync', 'Customer QBR', 'Retro', 'Launch prep'])} — {r.choice(ACME_CUSTOMERS)}",
                   d(-r.randint(5, 400)), r.choice(CITIES)[0], "; ".join(att)))
    w_text(root, "google_workspace/SharedCalendars.csv",
           csv_rows(["Summary", "Start", "Location", "Attendees"], ev))

    # ---- slack: users/channels + day files (channel filename must be YYYY-MM-DD)
    ws = "slack/Acme Robotics"
    uid = {p["name"]: f"U{i:04d}" for i, p in enumerate(P)}
    w_json(root, f"{ws}/users.json",
           [{"id": uid[p["name"]], "name": p["name"].split()[0].lower() + str(i),
             "deleted": False, "is_bot": False,
             "profile": {"real_name": p["name"], "title": p["role"]}}
            for i, p in enumerate(P)])
    chans = [("general", P),
             ("eng-standup", [p for p in P if p["dept"] == "Engineering"]),
             ("sales-floor", [p for p in P if p["dept"] == "Sales"]),
             ("support-queue", [p for p in P if p["dept"] == "Support"]),
             ("cobot-v2-launch", P[:24]), ("customer-wins", P[:30]),
             ("design-crit", [p for p in P if p["dept"] == "Design"]),
             ("ops-room", [p for p in P if p["dept"] == "Operations"])]
    w_json(root, f"{ws}/channels.json",
           [{"id": f"C{i:03d}", "name": nm, "members": [uid[p["name"]] for p in mem],
             "topic": {"value": f"{nm} topic"},
             "purpose": {"value": f"The Acme {nm} channel"}}
            for i, (nm, mem) in enumerate(chans)])
    for ci, (nm, mem) in enumerate(chans):
        for day in range(6):
            stamp = d(-(day * 11 + ci))
            msgs = []
            for k, p in enumerate(r.sample(mem, min(len(mem), r.randint(4, 10)))):
                msgs.append({"user": uid[p["name"]],
                             "ts": f"{1750000000 + ci * 100000 + day * 900 + k}.000100",
                             "text": "secret-body-do-not-leak — never imported"})
            w_json(root, f"{ws}/{nm}/{stamp}.json", msgs)

    # ---- salesforce: Opportunity rows are the ONLY per-item deal notes ---------
    accounts = ACME_CUSTOMERS + ACME_VENDORS
    aid = {a: f"001{i:04d}" for i, a in enumerate(accounts)}
    w_text(root, "salesforce/Account.csv", csv_rows(
        ["Id", "Name", "Website", "BillingCity", "Industry", "NumberOfEmployees"],
        [(aid[a], a, f"https://{a.split()[0].lower()}.example",
          CITIES[i % len(CITIES)][0], "Manufacturing", r.randint(40, 4000))
         for i, a in enumerate(accounts)]))
    w_text(root, "salesforce/Contact.csv", csv_rows(
        ["Id", "FirstName", "LastName", "Title", "AccountId"],
        [(f"003{i:04d}", c["name"].split()[0], " ".join(c["name"].split()[1:]),
          c["role"], aid.get(c["company"], "")) for i, c in enumerate(W.customer_contacts)]))
    stages = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won"]
    w_text(root, "salesforce/Opportunity.csv", csv_rows(
        ["Id", "Name", "AccountId", "StageName", "Amount", "CloseDate"],
        [(f"006{i:04d}",
          f"{r.choice(['Fleet expansion', 'Cobot pilot', 'Line retrofit', 'Support renewal', 'Safety upgrade'])} {i + 1}",
          aid[r.choice(ACME_CUSTOMERS)], r.choice(stages),
          r.randint(8000, 480000), d(r.randint(-300, 200))) for i in range(110)]))
    w_text(root, "salesforce/Campaign.csv", csv_rows(
        ["Id", "Name", "StartDate"],
        [(f"701{i:04d}", f"{r.choice(TOPICS).title()} webinar", d(-r.randint(30, 400)))
         for i in range(12)]))

    # ---- lighter company sources ----------------------------------------------
    w_text(root, "zendesk/tickets.csv", csv_rows(
        ["Id", "Subject", "Created At", "Requester"],
        [(i, f"Ticket {i}", d(-r.randint(5, 300)), r.choice(W.customer_contacts)["name"])
         for i in range(60)]))
    w_text(root, "jira/issues.csv", csv_rows(
        ["Key", "Summary", "Assignee", "Created"],
        [(f"COB-{i}", f"{r.choice(TOPICS)} task", r.choice(P)["name"], d(-r.randint(5, 300)))
         for i in range(50)]))
    w_json(root, "notion/pages.json",
           [{"title": f"{t.title()} runbook", "created_time": d(-r.randint(20, 500))}
            for t in TOPICS])
    w_text(root, "confluence/space.xml",
           "<space><page><title>Onboarding</title></page>"
           "<page><title>Fleet runbook</title></page></space>\n")
    w_text(root, "hubspot/hubspot-crm-exports-all-contacts.csv", csv_rows(
        ["First Name", "Last Name", "Company", "Job Title"],
        [(c["name"].split()[0], " ".join(c["name"].split()[1:]), c["company"], c["role"])
         for c in W.customer_contacts[:60]]))
    w_text(root, "teams/TeamsMessagesReport.csv", csv_rows(
        ["Participant", "Date"],
        [(p["name"], d(-r.randint(5, 200))) for p in P[:40]]))
    w_text(root, "microsoft365/mailbox-usage.csv", csv_rows(
        ["Display Name", "Last Activity Date"],
        [(p["name"], d(-r.randint(3, 90))) for p in P[:40]]))


# ------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Generate the synthetic demo exports.")
    ap.add_argument("--out", default=None,
                    help="target data root (default: <repo>/data)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing target (it is deleted first)")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()

    repo = Path(__file__).resolve().parent.parent
    out = Path(a.out).resolve() if a.out else (repo / "data")
    john, acme = out / "personal" / "john", out / "company" / "acme"

    for p in (john, acme):
        if p.exists() and any(p.iterdir()):
            if not a.force:
                sys.exit(f"Refusing to overwrite non-empty {p}\n"
                         f"  re-run with --force to replace it, or pass --out elsewhere.")
            shutil.rmtree(p)

    W = World(random.Random(a.seed))
    gen_john(john, W)
    gen_acme(acme, W)

    for label, p in (("personal/john", john), ("company/acme", acme)):
        files = [f for f in p.rglob("*") if f.is_file()]
        kb = sum(f.stat().st_size for f in files) / 1024
        print(f"  {label:16s} {len(files):4d} files  {kb:8.1f} KB")
    print(f"\nseed {a.seed} · john people {len(W.john_people)} · "
          f"acme people {len(W.acme_people)} · customer contacts "
          f"{len(W.customer_contacts)} · places {len(W.places)}")
    print(f"\nNext: python3 engine/scripts/build_vault.py {out} -o <vault-dir>")


if __name__ == "__main__":
    main()
