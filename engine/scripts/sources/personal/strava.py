#!/usr/bin/env python3
"""
strava.py — Strava bulk-export adapter (personal subject).

The "Download or Delete Your Account" bulk export ships `activities.csv` (the
index), `profile.csv`, optional clubs/gear CSVs, and an `activities/` folder of
GPX/FIT tracks. We map: activities → events + sport-type interests, profile →
identity (city geocodes for the map), clubs → orgs, and each GPX's FIRST
trackpoint → an 85-places pin (where you train — never the full route: one
point is the signal, the track is surveillance).
"""
import re

from ..common import read_csv, norm_file, iso_date

NAME = "strava"
SUBJECT = "person"
QUARANTINE = {"email", "contacts", "messaging", "logins", "connectedapps"}

_TRKPT = re.compile(r'<trkpt[^>]*lat="(-?[\d.]+)"[^>]*lon="(-?[\d.]+)"')
_GPX_NAME = re.compile(r"<name>([^<]{1,80})</name>")
_MAX_GPX = 500  # defensive cap; a decade of daily activity stays under this


def detect(file_index):
    """True if activities.csv (with an Activity header) is present."""
    for p in file_index.get("activities", []):
        if p.suffix.lower() != ".csv":
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:300].lower()
        except Exception:
            continue
        if "activity" in head:
            return True
    return False


def extract(root, file_index, all_paths, col):
    """Parse a Strava bulk export into the Collector. Returns consumed keys."""
    consumed = set()

    def rows(key):
        out = []
        for p in file_index.get(key, []):
            if p.suffix.lower() == ".csv":
                out.append((p, read_csv(p)))
                consumed.add(norm_file(p.name))
        return out

    # profile → identity (City/State/Country → geocodable location)
    for _p, rr in rows("profile"):
        for r in rr:
            name = ((r.get("First Name") or "") + " " + (r.get("Last Name") or "")).strip()
            loc = ", ".join(x for x in (r.get("City"), r.get("State"), r.get("Country")) if x)
            col.set_identity(NAME, name=name, location=loc)
            break

    # activities → events + sport interests
    n_act = 0
    names_by_file = {}
    for _p, rr in rows("activities"):
        for r in rr:
            nm = (r.get("Activity Name") or "").strip()
            typ = (r.get("Activity Type") or "").strip()
            date = iso_date((r.get("Activity Date") or "").strip())
            if not (nm or typ):
                continue
            col.add_event(NAME, f"{typ}: {nm}".strip(": "), date=date,
                          kind="activity")
            if typ:
                col.add_interest(NAME, typ)
            fn = (r.get("Filename") or "").strip()
            if fn:
                names_by_file[fn.rsplit("/", 1)[-1]] = nm or typ
            n_act += 1

    # clubs → orgs
    for _p, rr in rows("clubs"):
        for r in rr:
            nm = (r.get("Club Name") or r.get("Name") or "").strip()
            if nm:
                col.add_org(NAME, nm, "club", tags=["org/club"])

    # followers / following → people (name columns when present; some exports
    # carry only athlete IDs — a bare number is not a person, skip those rows)
    for key, role in (("followers", "follower"), ("following", "following")):
        for _p, rr in rows(key):
            for r in rr:
                nm = ((r.get("First Name") or "") + " " + (r.get("Last Name") or "")).strip() \
                    or (r.get("Name") or r.get("Athlete Name") or "").strip()
                if nm and not nm.replace(" ", "").isdigit():
                    col.add_person(NAME, nm, role=f"strava {role}",
                                   tags=["person/athlete"])

    # gear → services (what you ride/run on)
    for _p, rr in rows("gear") + rows("bikes") + rows("shoes"):
        for r in rr:
            nm = (r.get("Gear Name") or r.get("Name") or "").strip()
            if nm:
                col.services[f"gear: {nm}"] += 1
                col.sources.add(NAME)

    # GPX tracks → 85-places pins (FIRST trackpoint only — where, not the route)
    n_gpx = 0
    for p in all_paths:
        if p.suffix.lower() != ".gpx":
            continue
        consumed.add(norm_file(p.name))
        if n_gpx >= _MAX_GPX:
            continue  # still consumed (coverage), just not pinned
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:8192]
        except Exception:
            continue
        m = _TRKPT.search(head)
        if not m:
            continue
        nm = names_by_file.get(p.name) or ""
        if not nm:
            gm = _GPX_NAME.search(head)
            nm = gm.group(1).strip() if gm else p.stem
        col.add_place(NAME, name=nm, lat=m.group(1), lng=m.group(2),
                      kind="activity", tags=["place/activity"])
        n_gpx += 1

    if n_act:
        col.note(f"[strava] {n_act} activities → events, {n_gpx} GPX start-points → places")
    return consumed
