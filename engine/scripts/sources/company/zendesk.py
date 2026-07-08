#!/usr/bin/env python3
"""
zendesk.py — Zendesk account-export adapter (company subject).

The (support-enabled) account data export ships JSON/CSV: organizations →
customer orgs, users → requester people at their org, tickets → per-requester
interaction SIGNAL + per-org support volume. Ticket subjects/descriptions are
never imported — support history's brain value is WHO has issues and how often,
not the complaint text.
"""
from ..common import read_csv, read_json, norm_file, iso_date, EMAIL_RE

NAME = "zendesk"
SUBJECT = "company"
QUARANTINE = set()


def detect(file_index):
    """True if a Zendesk-shaped export is present (tickets + organizations, or
    'zendesk' in a filename)."""
    keys = set(file_index)
    if any("zendesk" in k for k in keys):
        return True
    return "tickets" in keys and "organizations" in keys


def _records(p):
    if p.suffix.lower() == ".csv":
        return read_csv(p)
    data = read_json(p)
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
    return data if isinstance(data, list) else []


def extract(root, file_index, all_paths, col):
    """Parse a Zendesk export into the Collector. Returns consumed keys."""
    consumed = set()
    col.subject = "company"

    def take(key):
        out = []
        for p in file_index.get(key, []):
            if p.suffix.lower() in (".json", ".csv"):
                out.extend(_records(p))
                consumed.add(norm_file(p.name))
        return out

    orgs = {}
    for o in take("organizations"):
        nm = (o.get("name") or "").strip() if isinstance(o, dict) else ""
        if nm:
            orgs[o.get("id")] = nm
            col.add_org(NAME, nm, "customer", tags=["org/customer"])

    users = {}
    for u in take("users"):
        if not isinstance(u, dict):
            continue
        nm = (u.get("name") or "").strip()
        if not nm or EMAIL_RE.search(nm):
            continue
        users[u.get("id")] = nm
        col.add_person(NAME, nm, company=orgs.get(u.get("organization_id"), ""),
                       role=u.get("role", ""), email=u.get("email", ""),
                       tags=["person/customer"])

    n_t = 0
    vol = {}
    for t in take("tickets"):
        if not isinstance(t, dict):
            continue
        who = users.get(t.get("requester_id"))
        if who:
            col.add_message_signal(NAME, who, iso_date(t.get("created_at", "")))
        org = orgs.get(t.get("organization_id"))
        if org:
            vol[org] = vol.get(org, 0) + 1
        n_t += 1
        # NOTE: t.get("subject") / t.get("description") deliberately NOT read.

    if users or n_t:
        top = ", ".join(f"{o}: {n}" for o, n in
                        sorted(vol.items(), key=lambda x: -x[1])[:8])
        col.note(f"[zendesk] {len(orgs)} orgs, {len(users)} users, {n_t} tickets "
                 "(signal only — subjects/bodies never read)"
                 + (f" · volume {top}" if top else ""))
    return consumed
