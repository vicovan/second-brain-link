#!/usr/bin/env python3
"""
Google Takeout adapter — a multi-product archive. Core coverage:
  Contacts (CSV/vCard)            -> people
  Calendar (.ics)                 -> events
  YouTube subscriptions (CSV)     -> interests / orgs (channels)
  Profile (Profile.json)          -> identity
Takeout is huge and varied; we cover the high-value, reasonably stable products
and let the universal catch-all summarize the rest.
"""
import re
from ..common import read_csv, read_json, nk, iso_date, EMAIL_RE

NAME = "google"
SIGNATURE_DIRS = ("contacts", "calendar", "youtube and youtube music", "profile",
                  "my activity", "google account")

def detect(file_index):
    """True if the archive looks like a Google Takeout export (a 'Takeout/'
    root, a Google profile, or contacts co-occurring with calendar/YouTube)."""
    # Takeout exports nest everything under a "Takeout/" root and use product
    # folder names. Detect by any of those signals appearing in the file paths.
    joined = " ".join(file_index.keys())
    paths = []
    for paths_list in file_index.values():
        for p in paths_list:
            paths.append(str(p).lower())
    blob = " ".join(paths)
    if "takeout" in blob:
        return True
    if "googleprofile" in joined:
        return True
    # contacts + calendar/youtube co-occurring is a strong Takeout signal
    has_contacts = any("contact" in p for p in paths)
    has_cal = any(p.endswith(".ics") for p in paths)
    has_yt = any("subscription" in p for p in paths)
    return has_contacts and (has_cal or has_yt)

def extract(root, file_index, all_paths, col):
    """Parse a Google Takeout export into the Collector (profile -> identity,
    contacts -> people/orgs, .ics -> events, YouTube subs -> interests).
    Returns the set of consumed normalized filename keys."""
    consumed = set()
    low = lambda p: str(p).lower()  # lowercased full path, for substring matching

    # profile
    for p in all_paths:
        if p.name.lower() in ("profile.json",) and "profile" in low(p):
            data = read_json(p) or {}
            nm = data.get("displayName") or (data.get("name") or {}).get("formattedName")
            if isinstance(data.get("name"), dict) and not nm:
                nm = (data["name"].get("givenName", "") + " " + data["name"].get("familyName", "")).strip()
            if nm:
                col.set_identity(NAME, name=nm)
            consumed.add(nk(p.name))

    # contacts (CSV) -> people. Google Contacts CSV has "Name"/"Given Name" + org cols.
    pc = 0
    for p in all_paths:
        if p.suffix.lower() == ".csv" and "contact" in low(p):
            for r in read_csv(p):
                name = (r.get("Name") or
                        (r.get("Given Name", "") + " " + r.get("Family Name", "")).strip() or
                        r.get("File As") or "")
                org = r.get("Organization Name") or r.get("Organization 1 - Name") or ""
                title = r.get("Organization Title") or r.get("Organization 1 - Title") or ""
                if name and not EMAIL_RE.search(name):
                    col.add_person(NAME, name, org, title)   # emails/phones ignored
                    if org: col.add_org(NAME, org, "contact-org")
                    pc += 1
            consumed.add(nk(p.name))
    if pc:
        col.note(f"[google] {pc} contacts")

    # calendar (.ics) -> events (parse SUMMARY + DTSTART only; no attendee PII)
    ec = 0
    for p in all_paths:
        if p.suffix.lower() == ".ics":
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            summary = dtstart = None
            for line in text.splitlines():
                if line.startswith("SUMMARY:"):
                    summary = line[8:].strip()
                elif line.startswith("DTSTART"):
                    m = re.search(r":(\d{8})", line)
                    if m:
                        dtstart = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}"
                elif line.startswith("END:VEVENT"):
                    if summary:
                        col.events.append({"name": summary, "date": dtstart or ""})
                        ec += 1
                    summary = dtstart = None
            consumed.add(nk(p.name))
    if ec:
        col.note(f"[google] {ec} calendar events")

    # youtube subscriptions (CSV) -> interests + channels as orgs
    yc = 0
    for p in all_paths:
        if p.suffix.lower() == ".csv" and "subscription" in low(p):
            for r in read_csv(p):
                ch = r.get("Channel Title") or r.get("Channel title") or ""
                if ch:
                    col.add_interest(NAME, ch)
                    yc += 1
            consumed.add(nk(p.name))
    if yc:
        col.note(f"[google] {yc} YouTube subscriptions")

    return consumed
