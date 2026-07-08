#!/usr/bin/env python3
"""
google_workspace.py — Google Workspace (admin) export adapter (company subject).

A Workspace admin export (Admin console / org Takeout) contains the org directory
(users → employees), shared calendars (→ events), and shared-drive metadata
(→ projects/orgs). Roots the brain on the organization. Same Collector contract.
Privacy: employee email/phone pass through; the Collector strips them unless
--full. HR/payroll/security/admin-log files are quarantined (see QUARANTINE).
"""
import re

from ..common import read_csv, read_json, nk, iso_date, canonical_url, EMAIL_RE

NAME = "google_workspace"
SUBJECT = "company"

SIGNATURE = {"users", "useraccounts", "domainusers", "orgunits", "googleworkspace"}
QUARANTINE = {"payroll", "salaries", "loginaudit", "adminaudit", "tokenaudit",
              "securitytokens", "passwords", "twostepverification", "drivetokens"}


def detect(file_index):
    """True if the export looks like a Google Workspace admin export; requires a
    workspace/orgunit signal so it doesn't false-positive on personal Takeout."""
    keys = set(file_index)
    # require a workspace-ish signal; "users" alone is common, so also accept a
    # workspace/orgunit hint to avoid false positives on personal Takeout.
    if "orgunits" in keys or "googleworkspace" in keys or "domainusers" in keys:
        return True
    return ("users" in keys or "useraccounts" in keys) and any(
        k in keys for k in ("orgunits", "sharedcalendars", "shareddrives"))


def _col(row, *names, default=""):
    """Fetch a cell from a CSV row by trying each candidate column name in
    order: exact (case-insensitive) match first, then a normalized substring
    match; returns the trimmed value or `default`."""
    low = {k.lower().strip(): v for k, v in row.items() if k}
    for n in names:
        if n.lower() in low and low[n.lower()] not in (None, ""):
            return str(low[n.lower()]).strip()
    for n in names:
        nn = nk(n)
        for k, v in low.items():
            if nn and (nn in nk(k) or nk(k) in nn) and v:
                return str(v).strip()
    return default


def extract(root, file_index, all_paths, col):
    """Parse a Google Workspace admin export into the Collector (org identity,
    users -> employees, shared calendars -> events, shared drives -> projects).
    Roots the brain on the company. Returns consumed normalized filename keys."""
    consumed = set()

    def rows(*prefixes):
        """Read and concatenate CSV rows of every file whose normalized key
        equals or starts with any prefix (non-CSV files are skipped)."""
        out = []
        for key, paths in file_index.items():
            if any(key == p or key.startswith(p) for p in prefixes):
                for p in paths:
                    if p.suffix.lower() == ".csv":
                        out.extend(read_csv(p))
        return out

    def mark(*p): consumed.update(  # mark every index key matching a prefix as handled
        k for k in file_index if any(k == x or k.startswith(x) for x in p))

    col.subject = "company"

    # org name from an org-units / domain file if present
    ou = rows("orgunits", "domains", "googleworkspace")
    mark("orgunits", "domains", "googleworkspace")
    org_name = ""
    for r in ou:
        org_name = _col(r, "Organization Name", "Domain", "Org Name", "Name")
        if org_name:
            break
    if org_name:
        col.subject_entity = org_name
        col.add_org(NAME, org_name, "self")
        col.set_identity(NAME, name=org_name, industry="")

    # users → employees. The Org Unit column is the org STRUCTURE — each unit
    # becomes a department org note, and the person carries a dept/<slug> tag so
    # the org chart / who-knows-what analyses can group by team.
    users = rows("users", "useraccounts", "domainusers")
    mark("users", "useraccounts", "domainusers")
    depts = set()
    for r in users:
        name = (_col(r, "First Name", "Given Name") + " " +
                _col(r, "Last Name", "Family Name")).strip() or _col(r, "Name", "Full Name")
        if not name:
            continue
        ou = _col(r, "Org Unit", "Org Unit Path", "Organizational Unit", "Department")
        dept = ou.strip("/").split("/")[-1].strip() if ou else ""
        tags = []
        if dept:
            depts.add(dept)
            tags.append("dept/" + re.sub(r"[^a-z0-9]+", "-", dept.lower()).strip("-"))
        col.add_person(NAME, name,
                       company=org_name,
                       role=_col(r, "Title", "Job Title", "Role"),
                       email=_col(r, "Email", "Email Address", "Primary Email"),
                       dept=dept,
                       tags=tags,
                       extra={k: v for k, v in r.items()
                              if k and nk(k) not in ("firstname", "givenname",
                              "lastname", "familyname", "name", "fullname",
                              "title", "jobtitle", "role", "email", "emailaddress",
                              "primaryemail")})
    for dept in depts:
        col.add_org(NAME, dept, "department", tags=["org/department"])

    # shared calendars → events, WITH the collaboration signal a calendar
    # actually carries: attendees (names only — email-shaped entries are skipped
    # in default mode; the Collector would strip them anyway), organizer, location.
    for r in rows("sharedcalendars", "calendarevents", "events"):
        attendees = []
        raw = _col(r, "Attendees", "Guests", "Participants")
        organizer = _col(r, "Organizer", "Creator")
        for who in ([organizer] if organizer else []) + re.split(r"[;,]", raw or ""):
            who = (who or "").strip()
            if not who or EMAIL_RE.search(who):
                continue  # attendee lists are often emails — never store those
            attendees.append(who)
            col.add_person(NAME, who, company=org_name)
        col.add_event(NAME, _col(r, "Summary", "Event Name", "Title"),
                      date=_col(r, "Start", "Date", "Start Date"),
                      kind="meeting" if attendees else "event",
                      location=_col(r, "Location", "Where"),
                      description=_col(r, "Description"),
                      attendees=attendees)
    mark("sharedcalendars", "calendarevents", "events")

    # shared drives → orgs/projects (light)
    for r in rows("shareddrives", "drives"):
        nm = _col(r, "Name", "Drive Name")
        if nm:
            col.add_org(NAME, nm, "project")
    mark("shareddrives", "drives")

    # groups → orgs (mailing lists/teams are real structure; member emails are
    # never stored — the group NAME is the signal)
    for r in rows("groups", "groupmembers"):
        nm = _col(r, "Group Name", "Name", "Group Email")
        if nm and "@" in nm:
            nm = nm.split("@", 1)[0]
        if nm:
            col.add_org(NAME, nm, "group", tags=["org/group"])
    mark("groups", "groupmembers")

    if org_name or users:
        col.note(f"[google_workspace] org '{org_name or '?'}': {len(users)} users")
    return consumed
