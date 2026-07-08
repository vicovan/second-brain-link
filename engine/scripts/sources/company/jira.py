#!/usr/bin/env python3
"""
jira.py — Jira CSV-export adapter (company subject).

Jira's issue-navigator CSV export ("all fields" or default) is the decision +
ownership trail: projects → orgs, assignees/reporters → people, and per-person
issue activity → the who-owns-what signal (dept-style `project/<slug>` tags on
people). Issue summaries/descriptions are NOT imported as content — ownership
and structure are the brain signal; ticket prose is noise at best and sensitive
at worst.
"""
import re

from ..common import read_csv, norm_file, iso_date, EMAIL_RE

NAME = "jira"
SUBJECT = "company"
QUARANTINE = set()


def _is_jira_csv(p):
    if p.suffix.lower() != ".csv":
        return False
    try:
        head = p.read_text(encoding="utf-8", errors="replace")[:500].lower()
    except Exception:
        return False
    return "issue key" in head or "issue id" in head


def detect(file_index):
    """True if a Jira-shaped CSV is present ('jira' in the name, or an
    Issue key column in the header)."""
    for k, ps in file_index.items():
        for p in ps:
            if "jira" in k and p.suffix.lower() == ".csv":
                return True
            if k in ("issues", "issueexport") and _is_jira_csv(p):
                return True
    return False


def _proj_tag(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"project/{s}" if s else ""


def extract(root, file_index, all_paths, col):
    """Parse Jira CSV exports into the Collector. Returns consumed keys."""
    consumed = set()
    col.subject = "company"
    n_issues = 0
    projects = {}

    for k, ps in list(file_index.items()):
        for p in ps:
            if not ("jira" in k or k in ("issues", "issueexport")) or not _is_jira_csv(p):
                continue
            consumed.add(norm_file(p.name))
            for r in read_csv(p):
                # "all fields" exports repeat columns (Comment, Component, Labels);
                # read_csv keeps the FIRST of each duplicate header — collect the
                # rest from the row's raw values conservatively via the dict we have.
                low = {(kk or "").lower().strip(): (v or "").strip()
                       for kk, v in r.items() if kk}
                proj = low.get("project name") or low.get("project") or ""
                if proj:
                    projects[proj] = projects.get(proj, 0) + 1
                tag = _proj_tag(proj)
                for field, role in (("assignee", "assignee"), ("reporter", "reporter"),
                                    ("creator", "reporter")):
                    who = low.get(field, "")
                    # exports may carry account ids or emails here — names only
                    if not who or EMAIL_RE.search(who) or re.match(r"^[0-9a-f:\-]{10,}$", who):
                        continue
                    col.add_person(NAME, who, tags=[t for t in (tag,) if t])
                # components / labels → interests (the technology/ownership map)
                for f in ("components", "component", "labels", "label"):
                    for val in re.split(r"[;,]", low.get(f, "")):
                        val = val.strip()
                        if val:
                            col.add_interest(NAME, f"component: {val}")
                # comment cells: "date;author;text" — author is who-knows-what
                # SIGNAL; the text after the second ';' is never touched
                for kk, v in r.items():
                    if not kk or (kk or "").lower().strip() != "comment" or not v:
                        continue
                    parts = str(v).split(";", 2)
                    if len(parts) >= 2:
                        author = parts[1].strip()
                        if author and not EMAIL_RE.search(author) \
                                and not re.match(r"^[0-9a-f:\-]{10,}$", author):
                            col.add_person(NAME, author,
                                           tags=[t for t in (tag,) if t])
                            col.add_message_signal(NAME, author,
                                                   iso_date(parts[0].strip()[:10]))
                n_issues += 1

    for proj, cnt in projects.items():
        col.add_org(NAME, proj, "project", tags=["org/project"])

    if n_issues:
        col.note(f"[jira] {n_issues} issues across {len(projects)} projects "
                 "(ownership only — ticket prose never imported)")
    return consumed
