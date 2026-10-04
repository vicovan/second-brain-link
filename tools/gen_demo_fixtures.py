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

The story the two archives tell (keep it coherent when you extend them):

  * John Carter — founder & CEO of Acme Robotics (San Francisco), ex Director of Product at
    Meridian Labs (London), MSc Bletchley Institute. Grace Hopper (Acme's VP Engineering) is
    his strongest contact; Priya Nair (Northwind Capital) the only — and dormant — investor.
    He keeps a travel corpus the Travel Agent can plan from: coffee he loved in London,
    Tokyo and San Francisco (reviewed ★5), a Lisbon trip he took (fado cellar, Web Summit,
    a sunset photo on the Tagus) and saved-but-never-visited pins in Lisbon, Tokyo and
    Seoul (`TRAVEL_PLACES`, `TIMELINE_VISITS`, `FB_EVENTS`). He also applied for a few
    advisory / fractional product roles at client companies (`JOHN_APPLICATIONS`).
  * Acme Robotics — a 200-person collaborative-robotics company: five departments, twelve
    customers, six vendors, Salesforce deals, Slack, Workspace calendars, and a LINKED
    document store (`_docs/acme-handbook`, read through `git_docs/_SOURCE_LINK.json`) with
    runbooks, a launch plan, a seed-round narrative and one credentials-named file that must
    render as a metadata-only stub. John Carter and Priya Nair appear in BOTH brains, which
    is what populates `_correlations/`.

Everything is derived from `SEED`; the same seed yields byte-identical files (no `hash()`,
no wall-clock time, fixed link ids), so `diff -r` between two runs is empty.
"""
import argparse
import json
import random
import shutil
import sys
import zlib
from datetime import date, timedelta
from pathlib import Path

SEED = 0xC0FFEE
# The demo's "today": the newest Slack day-file / order / message is just before this. Every
# date in both archives is relative to it, so bumping it moves the whole story forward.
TODAY = date(2026, 10, 3)

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

# ------------------------------------------------------------- John's travel corpus
# Named places with real-world-plausible coordinates (fictional venues). This is what the
# Travel Agent plans from: `saved` pins never visited become trip ideas (Lisbon, Tokyo,
# Seoul), ★4+ reviews define his taste (third-wave coffee, small rooms, no buffets), and
# the Timeline visits / FB events / IG venue prove where he has actually been. Each entry:
# (name, city, country, lat, lng, mode, date, rating, review, saved-list)
#   mode: "saved" -> Saved Places.json (+ the Saved/<list>.csv), "review" -> Reviews.json
TRAVEL_PLACES = [
    # Lisbon — saved for a trip he has not taken yet ("Want to go")
    ("Alfama Tile Café", "Lisbon", "PT", 38.7117, -9.1303, "saved", "2024-02-11", None, "", "Want to go"),
    ("Miradouro Roastery", "Lisbon", "PT", 38.7154, -9.1340, "saved", "2024-02-11", None, "", "Want to go"),
    ("Tasca do Largo", "Lisbon", "PT", 38.7110, -9.1445, "saved", "2024-03-02", None, "", "Want to go"),
    ("LX Riverside Market", "Lisbon", "PT", 38.7070, -9.1459, "saved", "2024-03-02", None, "", "Want to go"),
    ("Belém Pastry House", "Lisbon", "PT", 38.6975, -9.2032, "saved", "2024-03-05", None, "", "Want to go"),
    ("Tagus Design Museum", "Lisbon", "PT", 38.7079, -9.1366, "saved", "2024-03-05", None, "", "Want to go"),
    ("Príncipe Real Garden Bar", "Lisbon", "PT", 38.7166, -9.1487, "saved", "2024-04-18", None, "", "Want to go"),
    ("Sintra Ridge Trail", "Sintra", "PT", 38.7876, -9.3906, "saved", "2024-04-18", None, "", "Want to go"),
    # Lisbon — the one night he did spend there (Web Summit week, 2022)
    ("Lisbon Fado Cellar", "Lisbon", "PT", 38.7123, -9.1296, "review", "2022-10-14", 4,
     "Small room, real fado, book ahead.", ""),
    # Tokyo — saved for the Robot Expo trip he keeps postponing
    ("Shibuya Standing Coffee", "Tokyo", "JP", 35.6614, 139.6983, "saved", "2025-01-20", None, "", "Want to go"),
    ("Nakameguro Canal Roasters", "Tokyo", "JP", 35.6440, 139.6990, "saved", "2025-01-20", None, "", "Want to go"),
    ("Yanaka Ramen Counter", "Tokyo", "JP", 35.7263, 139.7671, "saved", "2025-01-22", None, "", "Want to go"),
    ("Kiyosumi Garden Tea", "Tokyo", "JP", 35.6800, 139.7985, "saved", "2025-02-03", None, "", "Want to go"),
    ("Ueno Robotics Museum", "Tokyo", "JP", 35.7188, 139.7760, "saved", "2025-02-03", None, "", "Want to go"),
    ("Golden Gai Listening Bar", "Tokyo", "JP", 35.6938, 139.7046, "saved", "2025-02-09", None, "", "Want to go"),
    ("Kanda Pour-Over Bar", "Tokyo", "JP", 35.6953, 139.7708, "review", "2023-11-05", 5,
     "The best pour-over I have had; single-origin, tiny counter, no laptops.", "Favourite coffee"),
    # Seoul — two pins, one weekend
    ("Bukchon Hanok Teahouse", "Seoul", "KR", 37.5826, 126.9830, "saved", "2025-02-10", None, "", "Want to go"),
    ("Seongsu Espresso Works", "Seoul", "KR", 37.5446, 127.0557, "saved", "2025-02-10", None, "", "Want to go"),
    # London — three mornings in a row at the same counter (the Timeline agrees)
    ("Harbour Third Wave", "London", "GB", 51.5202, -0.0776, "review", "2024-06-12", 5,
     "Proper third-wave espresso. Went back three mornings in a row.", "Favourite coffee"),
    ("Chain Hotel Breakfast Hall", "London", "GB", 51.5074, -0.1278, "review", "2024-06-13", 2,
     "Buffet breakfast, forgettable. Would rather find a café.", ""),
    # San Francisco — home turf
    ("Mission Espresso Lab", "San Francisco", "US", 37.7599, -122.4148, "review", "2024-08-30", 5,
     "Light roast, patient baristas, great pastries.", "Favourite coffee"),
    ("Telegraph Hill Steps", "San Francisco", "US", 37.8024, -122.4058, "review", "2024-09-02", 4,
     "Steep, quiet, the best view of the bay for the price of nothing.", ""),
]
REVIEW_LINES = {
    3: ["Fine for a quick stop; nothing to go back for.", "Decent, a bit loud at lunch."],
    4: ["Good light, quiet in the mornings.", "Friendly, consistent, worth the detour.",
        "Great room; the coffee is the weak point."],
    5: ["Exactly the kind of place I look for — small, careful, no fuss.",
        "Went twice in one week. The owner remembers your order."],
}
HOME_LATLNG = (37.7749, -122.4194)          # San Francisco (identity + Timeline HOME)

# Google's on-device Timeline (semanticSegments) — dated visits the engine names by the
# nearest saved place; HOME is skipped by design. (place, local ISO start, tz)
TIMELINE_VISITS = [
    ("Harbour Third Wave", "2024-06-12T08:10:00", "+01:00"),
    ("Harbour Third Wave", "2024-06-13T08:05:00", "+01:00"),
    ("Harbour Third Wave", "2024-06-14T08:15:00", "+01:00"),
    ("Lisbon Fado Cellar", "2022-10-14T21:00:00", "+01:00"),
    ("Mission Espresso Lab", "2024-08-30T09:00:00", "-07:00"),
    ("Telegraph Hill Steps", "2024-09-02T12:30:00", "-07:00"),
    ("Kanda Pour-Over Bar", "2023-11-05T10:20:00", "+09:00"),
]
# Facebook event responses — venues with coordinates land in 85-places; the meetup has none.
FB_EVENTS = {
    "events_joined": [
        {"name": "Web Summit Lisbon", "start_timestamp": 1665741600,
         "place": {"name": "Lisbon Arena", "address": "Parque das Nações, Lisbon",
                   "coordinate": {"latitude": 38.7686, "longitude": -9.0939}}},
        {"name": "Harbour Runners Spring 10K", "start_timestamp": 1718434800,
         "place": {"name": "Victoria Park Bandstand", "address": "Hackney, London",
                   "coordinate": {"latitude": 51.5362, "longitude": -0.0387}}},
        {"name": "Robotics meetup", "start_timestamp": 1718200800},
    ],
    "events_declined": [],
    "events_interested": [
        {"name": "Tokyo Robot Expo", "start_timestamp": 1769821200,
         "place": {"name": "Tokyo Big Sight", "address": "Ariake, Tokyo",
                   "coordinate": {"latitude": 35.6298, "longitude": 139.7942}}},
    ],
}
# LinkedIn Job Applications — advisory / fractional product roles at companies in his own
# network, which is the Jobs Agent's lane in the demo. (company, title, days ago)
JOHN_APPLICATIONS = [
    ("Verge Freight", "Board Advisor, Automation", 410),
    ("Saltbox Foods", "Fractional Chief Product Officer", 330),
    ("Tidewater Marine", "Product Advisor (Robotics)", 240),
    ("Kiln Ceramics", "Fractional Head of Product", 160),
    ("Analytical Engines", "VP Product", 95),
]


def d(offset_days):
    """A date offset from TODAY, ISO. Negative = past."""
    return (TODAY + timedelta(days=offset_days)).isoformat()


def profile_url(name):
    """One stable public-profile URL per person. The same person must carry the same URL in every
    export (correlate.py refuses a cross-brain merge on a conflicting canonical_url)."""
    return "https://www.linkedin.com/in/" + "-".join(name.lower().split())


def epoch(day_):
    """Unix seconds at 09:00 UTC on a date. (The old `toordinal()*86400` counted from year 1, so
    every Facebook timestamp landed in year 3994 and its 11-digit note filename read as a phone
    number to the PII sweep.)"""
    return (day_.toordinal() - date(1970, 1, 1).toordinal()) * 86400 + 9 * 3600


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
        # Priya Nair and John Carter appear in BOTH brains -> _correlations/. John's title
        # here matches his own LinkedIn Positions (he founded Acme); Priya sits on the board.
        self.acme_people.append({"name": "Priya Nair", "dept": "Operations",
                                 "role": "Board Advisor", "msgs": 12})
        self.acme_people.append({"name": "John Carter", "dept": "Operations",
                                 "role": "Founder & CEO", "msgs": 26})

        # ---- places -------------------------------------------------------------
        # Places and posts are leaf-only in this engine (nothing links to them), so
        # they land as degree-0 halo dots in the cellular view. Keep them present for
        # the map view and the voice layer, but well below the people count.
        self.places = []
        combos = [(w, k) for w in VENUE_WORDS for k in VENUE_KINDS]
        r.shuffle(combos)
        for w, k in combos[:112]:
            city, cc, lat, lng = r.choice(CITIES)
            self.places.append({
                "name": f"{w} {k.title()}",
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
             profile_url(p["name"]),
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
    # The conversation id is a crc32, not hash(): Python salts hash() per process, which
    # made two runs of this script differ in this one column.
    mrows = []
    for p in P:
        lo, hi = p.get("age", (5, 700))
        for k in range(p["msgs"]):
            mrows.append((f"c{zlib.crc32(p['name'].encode('utf-8')) % 9999}", p["name"], p["name"],
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
        [(co, title, d(-ago)) for co, title, ago in JOHN_APPLICATIONS]))
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
                            "timestamp": epoch(TODAY - timedelta(days=-p["since"]))}
                           for p in fb]})
    w_json(root, "facebook/your_facebook_activity/posts/your_posts__check_ins__photos_and_videos_1.json",
           [{"timestamp": epoch(TODAY - timedelta(days=r.randint(5, 700))),
             "data": [{"post": f"Field notes on {r.choice(TOPICS)}."}]} for _ in range(24)])
    checkins = [p for p in W.places if p["kind"] == "check-in"]
    w_json(root, "facebook/your_facebook_activity/posts/check-ins.json",
           [{"timestamp": epoch(TODAY - timedelta(days=r.randint(20, 400))),
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
    # event responses: a venue with coordinates becomes a place (rule-level `require`
    # keeps the coordinate-less meetup out of 85-places)
    w_json(root, "facebook/your_facebook_activity/events/your_event_responses.json",
           {"event_responses_v2": FB_EVENTS})

    # ---- instagram --------------------------------------------------------------
    ig = [p for p in P if "instagram" in p["extra"]]
    w_json(root, "instagram/connections/followers_and_following/followers_1.json",
           [{"string_list_data": [{"value": p["name"],
                                   "href": f"https://instagram.com/{p['name'].split()[0].lower()}",
                                   "timestamp": 1700000000}]} for p in ig])
    ig_posts = [{"title": f"{r.choice(VENUE_WORDS)} — {r.choice(TOPICS)}",
                 "creation_timestamp": 1700000000 + i * 90000} for i in range(20)]
    # one geotagged post (the Lisbon trip) — the only IG post that may become a place
    ig_posts.append({
        "media": [{"uri": "media/posts/202210/tagus.jpg", "creation_timestamp": 1665770400,
                   "title": "",
                   "media_metadata": {"photo_metadata": {"exif_data": [
                       {"latitude": 38.7058, "longitude": -9.144}]}}}],
        "title": "Sunset over the Tagus", "creation_timestamp": 1665770400,
        "location": {"name": "Cais Sunset Pier", "latitude": 38.7058, "longitude": -9.144}})
    w_json(root, "instagram/your_instagram_activity/media/posts_1.json", ig_posts)
    w_json(root, "instagram/preferences/your_topics/your_topics.json",
           {"topics": [{"string_map_data": {"Name": {"value": t}}} for t in TOPICS]})
    w_json(root, "instagram/personal_information/personal_information/personal_information.json",
           {"profile_user": [{"string_map_data": {"Name": {"value": "John Carter"}}}]})

    # ---- google maps (GeoJSON: coordinates are [lng, lat]) ----------------------
    saved = [p for p in W.places if p["kind"] == "saved"]
    revd = [p for p in W.places if p["kind"] == "reviewed"]
    saved_feats = [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [p["lng"], p["lat"]]},
         "properties": {"location": {"name": p["name"], "country_code": p["cc"],
                                     "address": f"{p['city']}"},
                        "date": p["date"]}} for p in saved]
    review_feats = [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [p["lng"], p["lat"]]},
         "properties": {"location": {"name": p["name"], "country_code": p["cc"]},
                        "five_star_rating_published": (rt := r.choice([3, 4, 4, 5, 5])),
                        "review_text_published": r.choice(REVIEW_LINES[rt]),
                        "date": p["date"]}} for p in revd]
    # the named travel corpus (see TRAVEL_PLACES) rides on the same two files
    for name, city, cc, lat, lng, mode, when, rating, review, _lst in TRAVEL_PLACES:
        props = {"location": {"name": name, "country_code": cc, "address": f"{city}"},
                 "date": when}
        feat = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": props}
        if mode == "review":
            props["five_star_rating_published"] = rating
            props["review_text_published"] = review
            review_feats.append(feat)
        else:
            saved_feats.append(feat)
    w_json(root, "google/Maps (your places)/Saved Places.json",
           {"type": "FeatureCollection", "features": saved_feats})
    w_json(root, "google/Maps (your places)/Reviews.json",
           {"type": "FeatureCollection", "features": review_feats})
    # Saved lists (Takeout "Saved/<list>.csv"): the pins grouped the way he grouped them
    for lst in sorted({p[9] for p in TRAVEL_PLACES if p[9]}):
        rows = [(name, "", "https://www.google.com/maps/search/" + name.replace(" ", "+"),
                 "coffee" if lst == "Favourite coffee" else "", "")
                for name, *_rest, l in TRAVEL_PLACES if l == lst]
        w_text(root, f"google/Saved/{lst}.csv",
               csv_rows(["Title", "Note", "URL", "Tags", "Comment"], rows))
    # the new on-device Timeline: visits only (no raw signals), HOME skipped by the engine
    by_name = {p[0]: p for p in TRAVEL_PLACES}
    segs = []
    for place, start, tz in TIMELINE_VISITS:
        _n, _c, _cc, lat, lng, *_ = by_name[place]
        segs.append({"startTime": f"{start}.000{tz}", "endTime": f"{start}.000{tz}",
                     "visit": {"hierarchyLevel": 0, "probability": 0.9,
                               "topCandidate": {"placeId": "demo-" + place.split()[0].lower(),
                                                "semanticType": "UNKNOWN", "probability": 0.8,
                                                "placeLocation": {"latLng": f"{lat}°, {lng}°"}}}})
    segs.append({"startTime": "2024-09-01T07:00:00.000-07:00", "endTime": "2024-09-01T07:00:00.000-07:00",
                 "visit": {"hierarchyLevel": 0, "probability": 0.9,
                           "topCandidate": {"placeId": "demo-home", "semanticType": "HOME",
                                            "probability": 0.8,
                                            "placeLocation": {"latLng": f"{HOME_LATLNG[0]}°, {HOME_LATLNG[1]}°"}}}})
    w_json(root, "google/Location History (Timeline)/Timeline.json",
           {"semanticSegments": segs, "rawSignals": [], "userLocationProfile": {}})

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
    # YouTube rides inside the Google Takeout (the standalone youtube adapter stands down
    # when Maps/Reviews are present, so a separate youtube/ folder would never be claimed)
    w_text(root, "google/YouTube and YouTube Music/subscriptions/subscriptions.csv", csv_rows(
        ["Channel Id", "Channel Url", "Channel Title"],
        [(f"UC{i:022d}", f"https://www.youtube.com/channel/UC{i:022d}", f"{t.title()} Channel")
         for i, t in enumerate(TOPICS[:8])]))
    w_text(root, "google/YouTube and YouTube Music/history/search-history.html",
           "<html><body>" + "".join(
               f'<div>Searched for <a href="https://www.youtube.com/results?search_query='
               f'{t.replace(" ", "+")}">{t}</a><br>{d(-i * 9)}</div>'
               for i, t in enumerate(TOPICS[:10])) + "</body></html>\n")
    # TikTok: the mapping detects the export by its real filename
    w_json(root, "tiktok/user_data_tiktok.json",
           {"Profile": {"Profile Information": {"ProfileMap": {"userName": "johncarter.builds"}}},
            "Activity": {"Favorite Videos": {"FavoriteVideoList": [
                {"Date": d(-i * 7), "Link": f"https://tiktok.example/v/{i}"}
                for i in range(12)]},
                "Hashtag": {"HashtagList": [{"HashtagName": t.replace(" ", "")} for t in TOPICS[:6]]},
                "Search History": {"SearchList": [{"Date": d(-i * 11), "SearchTerm": t}
                                                  for i, t in enumerate(TOPICS[:6])]}}})
    # WhatsApp: "WhatsApp Chat with <name>.txt", day-first timestamps; bodies never read
    wa = [p for p in P if "whatsapp" in p["extra"]] or P[:12]
    wa_lines = []
    for i in range(30):
        x = TODAY - timedelta(days=i)
        wa_lines.append(f"[{x.day:02d}.{x.month:02d}.{x.year}, 07:1{i % 10}:00] "
                        f"{wa[i % len(wa)]['name']}: message body not imported")
    w_text(root, "whatsapp/WhatsApp Chat with Harbour Runners.txt", "\n".join(wa_lines) + "\n")
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
          profile_url(p["name"]), p["dept"])
         for i, p in enumerate(P)]))
    w_text(root, "linkedin_company/PageFollowers.csv", csv_rows(
        ["Name", "Profile Url"],
        [(c["name"], profile_url(c["name"]))
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

    # ---- lighter company sources (each shaped the way its adapter detects it) -----
    # (no Zendesk folder on purpose: the engine indexes files by BASENAME, and Zendesk's
    # `users`/`tickets` keys collide with Slack's users.json and Workspace's users.csv —
    # the adapters would read each other's files. Tracked as an engine bug, not papered over.)
    # jira: the issue-navigator CSV (detected by the "Issue key" header)
    w_text(root, "jira/jira-issues.csv", csv_rows(
        ["Issue key", "Issue id", "Summary", "Assignee", "Reporter", "Project name", "Created", "Labels"],
        [(f"COB-{i}", f"{10000 + i}", f"{r.choice(TOPICS)} task", r.choice(P)["name"],
          r.choice(P)["name"], r.choice(["Cobot V2", "Fleet Platform", "Field Ops"]),
          d(-r.randint(5, 300)), r.choice(["safety", "lidar", "fleet", "ui", ""])) for i in range(50)]))
    # notion: "Export all workspace content" — <Title> <32-hex>.md pages + a database CSV
    def hexid(s):
        return f"{zlib.crc32(s.encode('utf-8')):08x}" * 4
    for t in TOPICS[:10]:
        title = f"{t.title()} runbook"
        w_text(root, f"notion/Acme Wiki {hexid('wiki')}/{title} {hexid(title)}.md",
               f"# {title}\n\nHow we handle {t} on the factory floor: who owns it, what to check first, "
               f"and when to page engineering.\n")
    w_text(root, f"notion/Acme Wiki {hexid('wiki')}/Runbooks {hexid('db')}_all.csv", csv_rows(
        ["Name", "Owner team", "Last reviewed"],
        [(f"{t.title()} runbook", r.choice(["Engineering", "Support", "Operations"]), d(-r.randint(10, 300)))
         for t in TOPICS[:10]]))
    # confluence: an XML space export (entities.xml) — titles + authors only
    wiki_users = [p for p in P if p["dept"] == "Engineering"][:5]
    xml = ['<?xml version="1.0" encoding="UTF-8"?><hibernate-generic>',
           '<object class="Space"><property name="name">Acme Engineering Wiki</property></object>']
    for i, p in enumerate(wiki_users):
        xml.append(f'<object class="ConfluenceUserImpl"><id name="key">u{i}</id>'
                   f'<property name="fullName">{p["name"]}</property></object>')
    for i, t in enumerate(["Onboarding", "Fleet runbook", "Cobot V2 release notes", "Safety case",
                           "Customer site checklist", "On-call handbook", "Lidar vendor notes",
                           "Retrofit kit assembly"]):
        xml.append(f'<object class="Page"><property name="title">{t}</property>'
                   f'<property name="creator"><id name="key">u{i % len(wiki_users)}</id></property></object>')
    xml.append("</hibernate-generic>")
    w_text(root, "confluence/entities.xml", "\n".join(xml) + "\n")
    w_text(root, "hubspot/hubspot-crm-exports-all-contacts.csv", csv_rows(
        ["First Name", "Last Name", "Company", "Job Title"],
        [(c["name"].split()[0], " ".join(c["name"].split()[1:]), c["company"], c["role"])
         for c in W.customer_contacts[:60]]))
    w_text(root, "teams/TeamsMessagesReport.csv", csv_rows(
        ["Participant", "Date"],
        [(p["name"], d(-r.randint(5, 200))) for p in P[:40]]))
    # microsoft365: a Purview content-search export = loose .eml files; HEADERS ONLY are
    # read by the engine (display names + dates), the bodies here are a canary
    for i in range(36):
        frm = r.choice(P)
        to = r.sample([p for p in P if p is not frm], 2)
        x = TODAY - timedelta(days=r.randint(3, 120))
        addr = lambda p: f'"{p["name"]}" <{p["name"].split()[0].lower()}@acme-robotics.example>'  # noqa: E731
        w_text(root, f"microsoft365/Purview Export/Mailbox/message-{i:03d}.eml",
               f"From: {addr(frm)}\nTo: {addr(to[0])}\nCc: {addr(to[1])}\n"
               f"Date: {x.strftime('%a, %d %b %Y')} 09:{i % 60:02d}:00 +0000\n"
               f"Subject: Fleet sync\nMessage-ID: <msg{i}@acme-robotics.example>\n\n"
               "secret-body-do-not-leak — never imported\n")


# ------------------------------------------------------------- the document store
# A LINKED store, never copied into the entity: `company/acme/git_docs/_SOURCE_LINK.json`
# points (relatively) at `_docs/acme-handbook/`, which sits at the data root under a `_`
# name so neither `discover_entities` nor Studio's data index mistakes it for an entity.
# Every file is fictional; the one credentials file is assembled from pieces so no scanner
# reads this generator as a leak, and it MUST come out of the build as a metadata-only stub.
DOCS_STORE = "_docs/acme-handbook"
DOCS_LINK_ID = "demo2acme2handbook2link2id26"       # fixed: make_link() would use uuid4()


def gen_acme_docs(out_root, W):
    """Write `_docs/acme-handbook/` + the link file. `out_root` is the data root."""
    store = Path(out_root) / DOCS_STORE
    people = {p["name"]: p for p in W.acme_people}
    eng = [p["name"] for p in W.acme_people if p["dept"] == "Engineering"][:6]
    sales = [p["name"] for p in W.acme_people if p["dept"] == "Sales"][:4]
    files = {
        "README.md": ("# Acme Robotics handbook\n\nThe company handbook: how we ship, support and sell "
                      "collaborative robots. Start with [the launch plan](product/Cobot-V2-Launch-Plan.md) "
                      "and [the team](company/Team.md).\n"),
        "company/Team.md": ("# Team\n\n| Name | Role | Department |\n|---|---|---|\n"
                            + "".join(f"| {n} | {people[n]['role']} | {people[n]['dept']} |\n"
                                      for n in ["John Carter", "Grace Hopper", "Alan Turing", "Jonas Beck",
                                                "Dana Reyes", "Maya Chen", "Priya Nair"])
                            + "\nBoard: Priya Nair (Northwind Capital) advises on the seed round.\n"),
        "company/Onboarding-Checklist.md": (
            "# Week-one onboarding\n\n## Goals\n\n- Day 1: laptop, Slack, Workspace; read the fleet runbook.\n"
            "- Day 3: shadow one customer call with Sales.\n- Day 5: ship one change through CI.\n\n"
            "## Who to ask\n\n" + "".join(f"- {n} — {people[n]['role']}\n" for n in eng[:3] + sales[:2])),
        "company/Values.md": "# How we work\n\n1. Safety before speed.\n2. The floor is the customer.\n3. Write it down.\n",
        "engineering/Cobot-V2-Release-Runbook.md": (
            "---\nowner: engineering\n---\n# Cobot V2 release runbook\n\n1. Freeze `main` at 17:00 the day before.\n"
            "2. Run the safety suite on the staging cell.\n3. Roll to one customer line, watch for 48 hours.\n"
            "4. Fleet-wide roll by region.\n\nOwners: " + ", ".join(eng[:3]) + ".\n"),
        "engineering/Fleet-Incident-Playbook.md": (
            "# Fleet incident playbook\n\n## Severity\n\n| Sev | Means | Response |\n|---|---|---|\n"
            "| 1 | a robot stopped a line | 15 min, page the on-call |\n| 2 | degraded fleet telemetry | 2 h |\n"
            "| 3 | cosmetic | next sprint |\n\nSee [the runbook](Cobot-V2-Release-Runbook.md).\n"),
        "engineering/Safety-Certification-Notes.md": (
            "# Functional safety notes\n\nWhat the certification body asked for, and where each answer lives.\n\n"
            "- Risk assessment per cell — see the Launch plan.\n- Emergency stop latency — measured at 42 ms.\n"),
        "engineering/api-spec.yaml": "openapi: 3.0.0\ninfo:\n  title: Acme Fleet API\n  version: 2.1.0\npaths: {}\n",
        "engineering/System-Architecture.svg": ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500">'
                                                '<rect x="20" y="20" width="220" height="90"/>'
                                                '<text x="30" y="70">Fleet API</text></svg>\n'),
        "product/Cobot-V2-Launch-Plan.md": (
            "---\nowner: product\n---\n# Cobot V2 launch plan\n\n## Goals\n\n"
            "- Ship Cobot V2 to the first three customer lines between 2026-10-15 and 2026-12-01.\n"
            "- Retrofit kits for Verge Freight and Saltbox Foods in the same window.\n\n"
            "## Risks\n\n- Lidar module supply (Ironwood Cloud is the single vendor).\n\n"
            "Related: [[Pricing-Model]] and [the runbook](../engineering/Cobot-V2-Release-Runbook.md).\n"),
        "product/Cobot-V2-Launch-Plan-v2.md": "# Cobot V2 launch plan v2\n\nThe revised plan: the retrofit kits move to Q1.\n",
        "product/Pricing-Model.md": ("# Pricing model\n\n| Tier | Robots | Per robot / month |\n|---|---|---|\n"
                                     "| Pilot | 1–3 | 1,900 |\n| Line | 4–12 | 1,500 |\n| Fleet | 13+ | custom |\n"),
        "sales/Customer-QBR-Template.md": ("# Customer QBR template\n\n1. Uptime and interventions.\n"
                                           "2. What changed on the floor.\n3. Renewal and expansion.\n"),
        "sales/Verge-Freight-Account-Plan.md": (
            "# Verge Freight — account plan\n\nTwo warehouse lines live; a third in negotiation (Fleet expansion).\n\n"
            f"Owner: {sales[0] if sales else 'Sales'}. Exec sponsor on their side: a plant manager.\n"),
        "support/Escalation-Policy.md": ("# Support escalation\n\nTickets older than 48 hours escalate to the "
                                         "support lead; a stopped line pages engineering.\n"),
        "fundraising/Seed-Round-Narrative.md": (
            "# Seed round narrative\n\nAcme sells collaborative robots to small manufacturers who could never "
            "afford integration projects. Twelve customers, two renewals, one vendor risk.\n\n"
            "## Use of funds\n\n- Lidar second-sourcing.\n- Two field engineers.\n\n"
            "## Do not claim\n\n- recurring revenue figures that are not in the data room\n"),
        "fundraising/Investor-FAQ.md": ("# Investor FAQ\n\n**Why now?** Cobot V2 cut install time from weeks to days.\n\n"
                                        "**Who is on the board?** Priya Nair (Northwind Capital), advisor.\n"),
        "compliance/Data-Handling-Policy.md": ("# Data handling\n\nCustomer floor telemetry stays on the customer's "
                                               "network. No video leaves the cell.\n"),
        "compliance/policies/password-policy.md": "# Password policy\n\nPasswords rotate every 90 days.\n",
        # the one sensitive file: its NAME trips the credentials rule, so the brain gets a
        # metadata-only stub. The body is deliberately plain prose — a key-shaped string in a
        # committed demo folder would only set off secret scanners for nothing.
        "ops/Staging-Access-Credentials.md": ("# Staging access\n\nWho has access to the staging fleet and "
                                              "how it is granted. The actual credentials live in the team "
                                              "password manager — never in this repository.\n"),
        # the company's own mark (fictional, original): the docs pipeline promotes it to the
        # brain's `_assets/logo.svg`, which Studio's brain switcher and the graph show. A
        # full-bleed colour square with a bold "A" reads at 24px and survives a cover-fit crop.
        "assets/acme-logo.svg": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Acme Robotics">'
            '<rect width="64" height="64" rx="10" fill="#2f6f4f"/>'
            '<path d="M15 49 32 17l17 32" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>'
            '<path d="M24 39h16" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round"/>'
            '<circle cx="32" cy="17" r="6" fill="#f2a100" stroke="#2f6f4f" stroke-width="2.5"/>'
            '</svg>\n'
        ),
    }
    for rel, content in files.items():
        w_text(store, rel, content)
    link = {
        "schema": "sbl-source-link/1", "kind": "git_docs", "id": DOCS_LINK_ID,
        "label": "Acme handbook (docs repo)",
        # RELATIVE to the link folder, so the demo works wherever the data folder is copied
        "root": "../../../" + DOCS_STORE,
        "mode": "local", "layout": "auto", "include": ["**"], "exclude": [],
        "vcs": "auto", "copy_files": True,
        "max_copy_bytes": 25 * 1024 * 1024, "max_total_copy_bytes": 2 * 1024 * 1024 * 1024,
        "rules": {}, "connector": None,
        "created": "2026-10-01T09:00:00Z", "created_by": "gen_demo_fixtures",
    }
    w_text(Path(out_root), "company/acme/git_docs/_SOURCE_LINK.json",
           json.dumps(link, indent=2) + "\n")
    return store


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
    john, acme, docs = out / "personal" / "john", out / "company" / "acme", out / DOCS_STORE

    for p in (john, acme, docs):
        if p.exists() and any(p.iterdir()):
            if not a.force:
                sys.exit(f"Refusing to overwrite non-empty {p}\n"
                         f"  re-run with --force to replace it, or pass --out elsewhere.")
            shutil.rmtree(p)

    W = World(random.Random(a.seed))
    gen_john(john, W)
    gen_acme(acme, W)
    gen_acme_docs(out, W)

    for label, p in (("personal/john", john), ("company/acme", acme), (DOCS_STORE, docs)):
        files = [f for f in p.rglob("*") if f.is_file()]
        kb = sum(f.stat().st_size for f in files) / 1024
        print(f"  {label:20s} {len(files):4d} files  {kb:8.1f} KB")
    print(f"\nseed {a.seed} · john people {len(W.john_people)} · "
          f"acme people {len(W.acme_people)} · customer contacts "
          f"{len(W.customer_contacts)} · places {len(W.places)}")
    print(f"\nNext: python3 engine/scripts/build_vault.py {out} -o <vault-dir>")


if __name__ == "__main__":
    main()
