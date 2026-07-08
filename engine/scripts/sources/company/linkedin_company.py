#!/usr/bin/env python3
"""
linkedin_company.py — LinkedIn Company/Page export adapter (company subject).

A LinkedIn *Company Page* admin export is different from a personal export: it's
the org's own profile, its followers, its posts, and (sometimes) an employee list.
This adapter roots the brain on the COMPANY (sets col.subject="company") and feeds
the same canonical Collector, so the existing builder/emitters render a
company-rooted vault with no source-specific code downstream.

Contract: NAME, SUBJECT="company", detect(file_index), extract(root, file_index,
all_paths, col). Privacy is the Collector's job — we pass fields through and it
decides (default strips employee email/phone; --full keeps them).
"""
import re

from ..common import read_csv, nk, iso_date, canonical_url, fix_mojibake

NAME = "linkedin_company"
SUBJECT = "company"   # marks this as a company-subject source (build auto-detect)

# Signature files unique to a Company Page export (not a personal one).
SIGNATURE = {"organizationprofile", "companyprofile", "pagefollowers",
             "organizationfollowers", "pageadmins", "employeelist", "organizationposts"}

# Company-side sensitive files (extends the global quarantine spirit).
QUARANTINE = {"pageadmins", "billing", "invoices", "adsbilling"}


def detect(file_index):
    """True if at least one Company-Page signature file is present (distinct
    from a personal LinkedIn export)."""
    keys = set(file_index)
    return len(SIGNATURE & keys) >= 1


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
    """Parse a LinkedIn Company Page export into the Collector (org identity,
    employees -> people, followers -> people, the company's posts -> voice).
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

    # --- organization identity (the root entity) -----------------------
    prof = rows("organizationprofile", "companyprofile")
    mark("organizationprofile", "companyprofile")
    org_name = ""
    if prof:
        r = prof[0]
        org_name = _col(r, "Organization Name", "Company Name", "Name", "Page Name")
        col.subject = "company"
        col.subject_entity = org_name
        col.set_identity(NAME, name=org_name,
                         headline=_col(r, "Tagline", "Headline"),
                         location=_col(r, "Location", "Headquarters"),
                         industry=_col(r, "Industry"),
                         about=_col(r, "Description", "About", "Overview"))
        if org_name:
            col.add_org(NAME, org_name, "self",
                        url=_col(r, "Url", "Website", "Public Url"),
                        location=_col(r, "Location", "Headquarters"),
                        industry=_col(r, "Industry"),
                        domain=_col(r, "Url", "Website"))

    # --- employees → people (works_at the company) ---------------------
    # The Department column is org structure, not trivia: each department
    # becomes an org note and the person carries a dept/<slug> tag (same
    # modeling as Google Workspace Org Units) so team-level analyses work.
    emps = rows("employeelist", "employees")
    mark("employeelist", "employees")
    depts = set()
    for r in emps:
        name = (_col(r, "First Name") + " " + _col(r, "Last Name")).strip() or _col(r, "Name")
        if not name:
            continue
        dept = _col(r, "Department", "Team", "Function")
        tags = []
        if dept:
            depts.add(dept)
            tags.append("dept/" + re.sub(r"[^a-z0-9]+", "-", dept.lower()).strip("-"))
        col.add_person(NAME, name,
                       company=org_name or _col(r, "Company"),
                       role=_col(r, "Title", "Position", "Role"),
                       url=_col(r, "Profile Url", "Url", "Public Url"),
                       email=_col(r, "Email", "Email Address"),
                       dept=dept,
                       tags=tags,
                       extra={k: v for k, v in r.items()
                              if k and nk(k) not in ("firstname", "lastname",
                              "name", "title", "position", "role", "profileurl",
                              "url", "email", "emailaddress", "department",
                              "team", "function")})
    for dept in depts:
        col.add_org(NAME, dept, "department", tags=["org/department"])

    # --- followers → org-follower people (light: name + url only) ------
    folls = rows("pagefollowers", "organizationfollowers", "followers")
    mark("pagefollowers", "organizationfollowers", "followers")
    for r in folls:
        name = _col(r, "Name", "Follower", "Full Name")
        if name:
            col.add_person(NAME, name, url=_col(r, "Profile Url", "Url"))

    # --- posts → voice (the company's own posts) -----------------------
    for r in rows("organizationposts", "pageposts", "posts"):
        col.add_post(NAME, _col(r, "Commentary", "Text", "Content", "Message"),
                     _col(r, "Date", "Created", "Posted On"), "post",
                     _col(r, "Url", "Link"))
    mark("organizationposts", "pageposts", "posts")

    # --- page analytics → 50-mirror (how the algorithm sees the PAGE) --
    # Follower/visitor demographics and post metrics are LinkedIn's model of
    # the company's audience — the company-side "algorithmic mirror".
    for r in rows("followerdemographics", "visitordemographics", "visitoranalytics",
                  "followermetrics", "pagestatistics"):
        seg = _col(r, "Value", "Segment", "Name", "Category", "Industry",
                   "Job Function", "Seniority", "Location", "Company Size")
        n = _col(r, "Followers", "Count", "Total", "Visitors", "Total Followers",
                 "Total Views")
        if seg:
            col.add_mirror_inference(NAME, f"{seg}" + (f" ({n})" if n else ""))
    mark("followerdemographics", "visitordemographics", "visitoranalytics",
         "followermetrics", "pagestatistics")
    for r in rows("updatemetrics", "postanalytics", "contentmetrics",
                  "updateengagement"):
        t = _col(r, "Update Title", "Post", "Title", "Update")
        imp = _col(r, "Impressions", "Views")
        eng = _col(r, "Engagement Rate", "Clicks", "Reactions")
        if t and (imp or eng):
            col.add_ad_segment(NAME, f"post '{t[:60]}' — impressions {imp or '?'}"
                               + (f", engagement {eng}" if eng else ""))
    mark("updatemetrics", "postanalytics", "contentmetrics", "updateengagement")

    if org_name:
        col.note(f"[linkedin_company] org '{org_name}': {len(emps)} employees, "
                 f"{len(folls)} followers")
    return consumed
