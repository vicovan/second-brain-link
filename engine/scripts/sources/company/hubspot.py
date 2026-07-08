#!/usr/bin/env python3
"""
hubspot.py — HubSpot per-object CSV export adapter (company subject).

HubSpot has no single "export all" — admins export Contacts / Companies /
Deals / Tickets as separate CSVs (filenames usually carry "hubspot" or the
object name). We stitch what's present: companies → customer orgs (city
geocodes), contacts → people at their associated company, deals → dated
events, tickets → per-company support COUNT (subjects/bodies never imported).
"""
from ..common import read_csv, norm_file, iso_date, EMAIL_RE

NAME = "hubspot"
SUBJECT = "company"
QUARANTINE = set()


def _bucket(file_index):
    """Classify export CSVs by object type from their filename key."""
    out = {"contacts": [], "companies": [], "deals": [], "tickets": []}
    for k, ps in file_index.items():
        for p in ps:
            if p.suffix.lower() != ".csv":
                continue
            for obj in out:
                if obj in k or obj.rstrip("s") in k:
                    out[obj].append(p)
                    break
    return out


def detect(file_index):
    """True if HubSpot-named exports are present, or ≥2 of the per-object set."""
    if any("hubspot" in k for k in file_index):
        return True
    b = _bucket(file_index)
    return sum(1 for v in b.values() if v) >= 2 and bool(b["companies"])


def _get(r, *names):
    low = {(k or "").lower().strip(): (v or "").strip() for k, v in r.items() if k}
    for n in names:
        if low.get(n.lower()):
            return low[n.lower()]
    return ""


def extract(root, file_index, all_paths, col):
    """Parse HubSpot per-object CSVs into the Collector. Returns consumed keys."""
    consumed = set()
    col.subject = "company"
    b = _bucket(file_index)
    for obj, paths in b.items():
        for p in paths:
            consumed.add(norm_file(p.name))

    n_co = n_ct = n_deal = 0
    for p in b["companies"]:
        for r in read_csv(p):
            nm = _get(r, "Name", "Company name")
            if nm:
                col.add_org(NAME, nm, "customer", url=_get(r, "Website URL", "Domain"),
                            location=_get(r, "City"), tags=["org/customer"],
                            industry=_get(r, "Industry"),
                            size=_get(r, "Number of Employees"),
                            domain=_get(r, "Website URL", "Domain"))
                n_co += 1

    for p in b["contacts"]:
        for r in read_csv(p):
            nm = (_get(r, "First Name") + " " + _get(r, "Last Name")).strip() or _get(r, "Name")
            if not nm or EMAIL_RE.search(nm):
                continue
            col.add_person(NAME, nm,
                           company=_get(r, "Primary Associated Company",
                                        "Associated Company", "Company Name"),
                           role=_get(r, "Job Title"), email=_get(r, "Email"),
                           tags=["person/customer"])
            n_ct += 1

    for p in b["deals"]:
        for r in read_csv(p):
            nm = _get(r, "Deal Name", "Name")
            if not nm:
                continue
            comp = _get(r, "Associated Company", "Company Name")
            stage = _get(r, "Deal Stage", "Stage")
            col.add_event(NAME, f"Deal: {nm}" + (f" ({comp})" if comp else "")
                          + (f" — {stage}" if stage else ""),
                          date=_get(r, "Close Date", "Create Date"), kind="deal",
                          value=_get(r, "Amount"))
            n_deal += 1

    # tickets → support volume per company + per-contact SIGNAL + owner people
    # (subjects/bodies never imported)
    tickets = {}
    for p in b["tickets"]:
        for r in read_csv(p):
            comp = _get(r, "Associated Company", "Company Name") or "(no company)"
            tickets[comp] = tickets.get(comp, 0) + 1
            who = _get(r, "Associated Contact", "Contact Name")
            if who and not EMAIL_RE.search(who):
                col.add_person(NAME, who, company="" if comp == "(no company)" else comp,
                               tags=["person/customer"])
                col.add_message_signal(NAME, who, iso_date(_get(r, "Create Date", "Created Date")))
            owner = _get(r, "Ticket owner", "Owner")
            if owner and not EMAIL_RE.search(owner):
                col.add_person(NAME, owner)   # the company's own agent
    for comp, n in tickets.items():
        if comp != "(no company)":
            col.add_org(NAME, comp, "customer", tags=["org/customer"])

    # deal/contact owners → the org's own people
    for obj in ("deals", "contacts"):
        for p in b[obj]:
            for r in read_csv(p):
                owner = _get(r, "Deal owner", "Contact owner", "Owner")
                if owner and not EMAIL_RE.search(owner):
                    col.add_person(NAME, owner)

    if n_co or n_ct:
        col.note(f"[hubspot] {n_co} companies, {n_ct} contacts, {n_deal} deals"
                 + (f", {sum(tickets.values())} tickets (count only)" if tickets else ""))
    return consumed
