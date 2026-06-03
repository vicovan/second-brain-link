#!/usr/bin/env python3
"""LinkedIn adapter — CSV export. Fully supported & tested."""
import re
from collections import Counter
from ..common import (read_csv, nk, norm_file, iso_date, EMAIL_RE,
                     SENSITIVE_COL_HINTS, canonical_url)

NAME = "linkedin"

# normalized-filename -> (canonical concept, expected column aliases)
QUARANTINE = {"emailaddresses", "phonenumbers", "whatsappphonenumbers",
              "importedcontacts", "logins", "securitychallenges", "registration",
              "receipts", "receiptsv2", "privateidentityasset", "guidemessages"}

# Files that signal "this is a LinkedIn export"
SIGNATURE = {"connections", "positions", "inferencesaboutyou", "profilesummary"}

def detect(file_index):
    """True if at least one LinkedIn signature CSV is present in the export."""
    keys = set(file_index)
    return len(SIGNATURE & keys) >= 1

def _col(row, *names, default=""):
    """Fetch a cell from a CSV row by trying each candidate column name in
    order: exact (case-insensitive) match first, then a normalized substring
    match; returns the trimmed value or `default`."""
    low = {k.lower().strip(): v for k, v in row.items() if k}
    # exact then fuzzy substring
    for n in names:
        if n.lower() in low and low[n.lower()] not in (None, ""):
            return str(low[n.lower()]).strip()
    for n in names:
        nn = nk(n)
        for k, v in low.items():
            if nn and (nn in nk(k) or nk(k) in nn) and v:
                return str(v).strip()
    return default

# concept handlers operate on rows and push into collector
def extract(root, file_index, col, alias_lookup=None):
    """file_index: {normkey: [Path,...]}; col: the collector."""
    def rows(*prefixes):
        """Read and concatenate the CSV rows of every file whose normalized key
        equals or starts with any of the given prefixes."""
        out = []
        for key, paths in file_index.items():
            if any(key == p or key.startswith(p) for p in prefixes):
                for p in paths:
                    # LinkedIn is a CSV-only export; never read a sibling source's
                    # JSON (e.g. Instagram's profile_*.json shares the "profile"
                    # prefix) — that leaked garbage into the identity note.
                    if p.suffix.lower() != ".csv":
                        continue
                    out.extend(read_csv(p))
        return out
    def present(*prefixes):
        """True if any file in the index matches one of the given key prefixes."""
        return any(any(k == p or k.startswith(p) for p in prefixes) for k in file_index)

    consumed = set()
    def mark(*p): consumed.update(p)  # record these keys as handled by this adapter

    # identity
    prof = rows("profile"); mark("profile")
    summ = rows("profilesummary"); mark("profilesummary")
    positions = rows("positions"); mark("positions")
    skills = rows("skills"); mark("skills")
    edu = rows("education"); mark("education")
    certs = rows("certifications"); mark("certifications")
    langs = rows("languages"); mark("languages")
    if prof:
        r = prof[0]
        col.set_identity(NAME,
            name=(_col(r, "First Name") + " " + _col(r, "Last Name")).strip(),
            headline=_col(r, "Headline"),
            location=_col(r, "Geo Location", "Location"),
            industry=_col(r, "Industry"),
            about=_col(r, "Summary"))
    if summ and not col.identity.get("about"):
        col.set_identity(NAME, about=_col(summ[0], "Summary", "Description"))
    for r in positions:
        comp = _col(r, "Company Name", "Company")
        if comp: col.add_org(NAME, comp, "employer")
        col.identity.setdefault("positions", []).append({
            "title": _col(r, "Title"), "company": comp,
            "start": iso_date(_col(r, "Started On", "Start Date")),
            "end": iso_date(_col(r, "Finished On", "End Date")) or "Present",
            "desc": _col(r, "Description")})
    for r in skills:
        s = _col(r, "Name", "Skill")
        if s: col.identity.setdefault("skills", []).append(s)
    for r in edu:
        col.identity.setdefault("education", []).append({
            "school": _col(r, "School Name", "School"),
            "degree": _col(r, "Degree Name", "Degree"),
            "field": _col(r, "Notes", "Field Of Study"),
            "years": f"{_col(r,'Start Date')}–{_col(r,'End Date')}".strip("–")})
    for r in certs:
        col.identity.setdefault("certifications", []).append(_col(r, "Name"))
    for r in langs:
        col.identity.setdefault("languages", []).append(_col(r, "Name", "Language"))
    col.note(f"[linkedin] identity: {len(positions)} roles, {len(skills)} skills, "
             f"{len(edu)} education, {len(certs)} certs")

    # message signal (bodies never read)
    msgs = rows("messages"); mark("messages")
    for r in msgs:
        party = _col(r, "FROM", "TO")
        col.add_message_signal(NAME, party, _col(r, "DATE", "Date"))
        # enrich an EXISTING person with their profile URL (never create people
        # from messages, and never read the message body)
        pu = canonical_url(_col(r, "SENDER PROFILE URL", "Sender Profile Url"))
        pkey = nk(party)
        if pu and pkey in col.people and not col.people[pkey].get("url"):
            col.people[pkey]["url"] = pu
    if msgs: col.note(f"[linkedin] message signal from {len(col.msg_signal)} correspondents (bodies dropped)")

    # people
    conns = rows("connections"); mark("connections")
    for r in conns:
        name = (_col(r, "First Name") + " " + _col(r, "Last Name")).strip()
        # Email Address ignored in default (privacy) mode; captured in --full mode
        # (the collector enforces which). `extra` carries every remaining column so
        # full mode loses nothing.
        col.add_person(NAME, name, _col(r, "Company"), _col(r, "Position"),
                       _col(r, "Connected On"),
                       url=_col(r, "URL", "Profile Url", "Public Url"),
                       email=_col(r, "Email Address"),
                       extra={k: v for k, v in r.items()
                              if k and nk(k) not in (
                                  "firstname", "lastname", "company", "position",
                                  "connectedon", "url", "emailaddress")})
    follows = rows("memberfollows"); mark("memberfollows")
    for r in follows:
        col.add_person(NAME, _col(r, "Name", "Full Name"))
    # invitations carry profile URLs — enrich EXISTING people (don't create new
    # notes for the user or pending strangers)
    def _enrich_url(name, u):
        """Attach a profile URL to an EXISTING person note (matched by nk(name)),
        only if they have none yet; never creates a new person."""
        u = canonical_url(u); k = nk(name)
        if u and k in col.people and not col.people[k].get("url"):
            col.people[k]["url"] = u
    for r in rows("invitations"):
        _enrich_url(_col(r, "From"), _col(r, "inviterProfileUrl"))
        _enrich_url(_col(r, "To"), _col(r, "inviteeProfileUrl"))
    mark("invitations")
    if conns: col.note(f"[linkedin] {len(conns)} connections")
    col._li_company_counts = Counter(_col(r, "Company") for r in conns if _col(r, "Company"))
    col._li_year_counts = Counter((iso_date(_col(r, "Connected On"))[:4] or "?") for r in conns)

    # orgs (followed)
    for r in rows("companyfollows"): col.add_org(NAME, _col(r, "Organization", "Company", "Name"), "followed")
    mark("companyfollows")

    # reputation
    for r in rows("recommendationsreceived"):
        who = (_col(r, "First Name") + " " + _col(r, "Last Name")).strip() or _col(r, "Name")
        col.reputation_received.append({"who": who, "text": _col(r, "Text", "Recommendation")})
    for r in rows("recommendationsgiven"):
        who = (_col(r, "First Name") + " " + _col(r, "Last Name")).strip() or _col(r, "Name")
        col.reputation_given.append({"who": who, "text": _col(r, "Text", "Recommendation")})
    for r in rows("endorsementreceivedinfo"):
        sk = _col(r, "Skill Name", "Skill")
        if sk: col.endorse_received[sk] += 1
        who = (_col(r, "Endorser First Name") + " " + _col(r, "Endorser Last Name")).strip()
        _enrich_url(who, _col(r, "Endorser Public Url"))
    for r in rows("endorsementgiveninfo"):
        col.endorse_given += 1
        who = (_col(r, "Endorsee First Name") + " " + _col(r, "Endorsee Last Name")).strip()
        _enrich_url(who, _col(r, "Endorsee Public Url"))
    mark("recommendationsreceived", "recommendationsgiven", "endorsementreceivedinfo", "endorsementgiveninfo")

    # voice
    for r in rows("shares"):
        col.add_post(NAME, _col(r, "ShareCommentary", "Commentary", "Text"),
                     _col(r, "Date"), "share", _col(r, "ShareLink", "SharedUrl"))
    for r in rows("instantreposts"):
        col.add_post(NAME, _col(r, "Commentary", "Text"), _col(r, "Date"), "repost")
    for r in rows("comments"):
        col.add_comment(NAME, _col(r, "Message", "Comment", "Text"), _col(r, "Date"))
    for r in rows("reactions"):
        col.add_reaction(NAME, _col(r, "Type", "Reaction"))
    col.reactions["poll vote"] += len(rows("votes"))
    for r in rows("hashtagfollows"):
        col.add_interest(NAME, _col(r, "HashTag", "Hashtag", "Name"))
    col.saved_count += len(rows("saveditems"))
    mark("shares", "instantreposts", "comments", "reactions", "votes", "hashtagfollows", "saveditems", "richmedia")

    # career
    apps = rows("jobapplications"); mark("jobapplications")
    for r in apps:
        c = _col(r, "Company Name", "Company"); t = _col(r, "Job Title", "Title")
        if c: col.applications[c] += 1; col.add_org(NAME, c, "target")
        if t: col.app_titles[t] += 1
        d = iso_date(_col(r, "Application Date", "Date"))
        if d: col.app_dates.append(d)
    pr = rows("jobseekerpreferences"); mark("jobseekerpreferences")
    if pr: col.prefs.update({k: v for k, v in pr[0].items() if v})
    for r in rows("savedjobs"):
        comp = _col(r, "Company Name", "Company")
        if comp: col.add_org(NAME, comp, "saved-job")
        col.saved_jobs.append({"title": _col(r, "Job Title", "Title"), "company": comp})
    mark("savedjobs", "savedjobalerts", "onlinejobpostings")
    for r in rows("jobapplicantsavedanswers") + rows("jobapplicantsavedscreeningquestionresponses"):
        col.reusable.append({"q": _col(r, "Question", "Prompt"), "a": _col(r, "Answer", "Response")})
    mark("jobapplicantsavedanswers", "jobapplicantsavedscreeningquestionresponses")

    # mirror
    for r in rows("inferencesaboutyou"):
        cells = [v.strip() for v in r.values() if v and v.strip()]
        if cells: col.mirror_inferences.append(max(cells, key=len))
    for r in rows("adtargeting"):
        col.ad_segments.extend(v for v in r.values() if v and len(v) < 80)
    col._li_ads_clicked = len(rows("adsclicked")); col._li_ad_eng = len(rows("lanadsengagement"))
    mark("inferencesaboutyou", "adtargeting", "adsclicked", "lanadsengagement")

    # learning / services / search
    col.learning_count += len(rows("learningcoachmessages")) + len(rows("learningroleplaymessages"))
    mark("learningcoachmessages", "learningroleplaymessages")
    # LinkedIn Learning courses (Learning.csv) — titles are a real topic/skill signal
    for r in rows("learning"):
        title = _col(r, "Content Title", "Title", "Course Title", "Name")
        if title:
            col.add_interest(NAME, title)
    mark("learning")
    for r in rows("events"):
        col.events.append({"name": _col(r, "Event Name", "Name"), "date": _col(r, "Date", "Time")})
    mark("events")
    col.services["engagements"] += len(rows("engagements"))
    col.services["opportunities"] += len(rows("opprtunities", "opportunities"))
    col.services["providers"] += len(rows("providers"))
    mark("engagements", "opprtunities", "opportunities", "providers")
    for r in rows("searchqueries"):
        q = _col(r, "Search Query", "Query", "Value")
        if q: col.searches.append(q)
    mark("searchqueries")

    return consumed
