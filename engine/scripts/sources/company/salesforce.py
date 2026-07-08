#!/usr/bin/env python3
"""
salesforce.py — Salesforce Data Export Service adapter (company subject).

The weekly/monthly Data Export ZIP is per-object CSVs keyed by Salesforce Ids —
the classic cross-file join a Python adapter exists for: Account.csv → customer
orgs (HQ city geocodes for the map), Contact.csv/Lead.csv → people joined to
their account, Opportunity.csv → dated deal events, Task.csv → per-contact
interaction SIGNAL (subject/description never read — count + date only, the
same rule as messages), User.csv → the org's own employees.
"""
from ..common import read_csv, norm_file, iso_date, EMAIL_RE

NAME = "salesforce"
SUBJECT = "company"
QUARANTINE = {"loginhistory", "authsession", "userlogin"}


def detect(file_index):
    """True if the per-object CSV set looks like a Salesforce data export."""
    keys = {k for k, ps in file_index.items()
            if any(p.suffix.lower() == ".csv" for p in ps)}
    return ("account" in keys and ("contact" in keys or "opportunity" in keys
                                   or "lead" in keys))


def _rows(file_index, key, consumed):
    out = []
    for p in file_index.get(key, []):
        if p.suffix.lower() == ".csv":
            out.extend(read_csv(p))
            consumed.add(norm_file(p.name))
    return out


def _get(r, *names):
    low = {(k or "").lower().strip(): (v or "").strip() for k, v in r.items() if k}
    for n in names:
        if low.get(n.lower()):
            return low[n.lower()]
    return ""


def extract(root, file_index, all_paths, col):
    """Parse a Salesforce export into the Collector. Returns consumed keys."""
    consumed = set()
    col.subject = "company"

    # accounts → customer orgs (Id → Name map feeds every other join)
    acct = {}
    for r in _rows(file_index, "account", consumed):
        nm = _get(r, "Name")
        if not nm:
            continue
        acct[_get(r, "Id")] = nm
        col.add_org(NAME, nm, "customer", url=_get(r, "Website"),
                    location=_get(r, "BillingCity"), tags=["org/customer"],
                    industry=_get(r, "Industry"),
                    size=_get(r, "NumberOfEmployees", "Employees"),
                    domain=_get(r, "Website"))

    # contacts / leads → people at their account
    contact_by_id = {}
    for key in ("contact", "lead"):
        for r in _rows(file_index, key, consumed):
            nm = (_get(r, "FirstName") + " " + _get(r, "LastName")).strip() or _get(r, "Name")
            if not nm or EMAIL_RE.search(nm):
                continue
            comp = acct.get(_get(r, "AccountId")) or _get(r, "Company")
            contact_by_id[_get(r, "Id")] = nm
            col.add_person(NAME, nm, company=comp, role=_get(r, "Title"),
                           email=_get(r, "Email"), tags=["person/customer"])

    # the org's own users → employees
    for r in _rows(file_index, "user", consumed):
        nm = _get(r, "Name") or (_get(r, "FirstName") + " " + _get(r, "LastName")).strip()
        if nm and not EMAIL_RE.search(nm) and _get(r, "IsActive").lower() != "false":
            col.add_person(NAME, nm, role=_get(r, "Title"), email=_get(r, "Email"))

    # opportunities → dated deal events on the timeline
    n_opp = 0
    for r in _rows(file_index, "opportunity", consumed):
        nm = _get(r, "Name")
        if not nm:
            continue
        comp = acct.get(_get(r, "AccountId"), "")
        col.add_event(NAME, f"Deal: {nm}" + (f" ({comp})" if comp else "")
                      + (f" — {_get(r, 'StageName')}" if _get(r, "StageName") else ""),
                      date=_get(r, "CloseDate", "CreatedDate"), kind="deal",
                      value=_get(r, "Amount"))
        n_opp += 1

    # tasks/activities → per-contact interaction SIGNAL (never the content)
    n_sig = 0
    for key in ("task", "event", "activityhistory"):
        for r in _rows(file_index, key, consumed):
            who = contact_by_id.get(_get(r, "WhoId"))
            if who:
                col.add_message_signal(NAME, who, iso_date(_get(r, "ActivityDate", "CreatedDate")))
                n_sig += 1

    # cases → per-contact support SIGNAL + per-account volume (subjects never read)
    case_vol = {}
    n_case = 0
    for r in _rows(file_index, "case", consumed):
        who = contact_by_id.get(_get(r, "ContactId"))
        if who:
            col.add_message_signal(NAME, who, iso_date(_get(r, "CreatedDate")))
        acc = acct.get(_get(r, "AccountId"))
        if acc:
            case_vol[acc] = case_vol.get(acc, 0) + 1
        n_case += 1
        # NOTE: _get(r, "Subject")/("Description") deliberately NOT read.
    if case_vol:
        top = ", ".join(f"{a}: {n}" for a, n in
                        sorted(case_vol.items(), key=lambda x: -x[1])[:8])
        col.note(f"[salesforce] {n_case} support cases (signal only) · volume {top}")

    # campaigns → dated events + member interaction signal
    camp = {}
    for r in _rows(file_index, "campaign", consumed):
        nm = _get(r, "Name")
        if not nm:
            continue
        camp[_get(r, "Id")] = nm
        col.add_event(NAME, f"Campaign: {nm}"
                      + (f" ({_get(r, 'Type')})" if _get(r, "Type") else ""),
                      date=_get(r, "StartDate", "CreatedDate"), kind="campaign")
    for r in _rows(file_index, "campaignmember", consumed):
        who = contact_by_id.get(_get(r, "ContactId", "LeadId"))
        if who:
            col.add_message_signal(NAME, who, iso_date(_get(r, "CreatedDate")))

    if acct or contact_by_id:
        col.note(f"[salesforce] {len(acct)} accounts, {len(contact_by_id)} contacts/leads, "
                 f"{n_opp} deals, {n_sig} activity signals (content never read)")
    return consumed
