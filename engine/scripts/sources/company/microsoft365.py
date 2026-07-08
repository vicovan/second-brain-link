#!/usr/bin/env python3
"""
microsoft365.py — Microsoft 365 / Purview eDiscovery adapter (company subject).
SIGNAL ONLY.

Purview Content Search exports arrive as loose .eml files (and/or result CSVs
whose filenames carry "purview"/"ediscovery"/"results"). Same rule as the MBOX
adapter: HEADERS ONLY — From/To/Cc display names → people + per-person message
signal; subjects/bodies never read. PST containers must be converted first
(readpst → mbox → the `email` adapter picks them up).
"""
import email
import email.utils
from email import policy

from ..common import read_csv, norm_file, iso_date, EMAIL_RE

NAME = "microsoft365"
SUBJECT = "company"
QUARANTINE = set()
_MAX_MSGS = 200000

_CSV_HINTS = ("purview", "ediscovery", "results", "items")


def detect(file_index):
    """True if Purview-style artifacts are present: .eml files, or result CSVs
    named for the export tooling."""
    for k, ps in file_index.items():
        for p in ps:
            if p.suffix.lower() == ".eml":
                return True
            if p.suffix.lower() == ".csv" and any(h in k for h in ("purview", "ediscovery")):
                return True
    return False


def _names(header_value):
    out = []
    for nm, addr in email.utils.getaddresses([header_value or ""]):
        nm = (nm or "").strip().strip('"')
        if nm and not EMAIL_RE.search(nm):
            out.append(nm)
    return out


def extract(root, file_index, all_paths, col):
    """Header-only pass over .eml files + Purview result CSVs. Returns consumed keys."""
    consumed = set()
    col.subject = "company"
    n_msgs = 0
    people = set()

    for ps in list(file_index.values()):
        for p in ps:
            if p.suffix.lower() != ".eml" or n_msgs >= _MAX_MSGS:
                continue
            consumed.add(norm_file(p.name))
            try:
                with open(p, "rb") as f:
                    msg = email.parser.BytesParser(policy=policy.default).parse(
                        f, headersonly=True)
            except Exception:
                continue
            n_msgs += 1
            date = ""
            if msg.get("Date"):
                try:
                    date = email.utils.parsedate_to_datetime(
                        msg.get("Date")).strftime("%Y-%m-%d")
                except Exception:
                    date = ""
            for hdr in ("From", "To", "Cc"):
                for nm in _names(str(msg.get(hdr, "") or "")):
                    people.add(nm)
                    col.add_person(NAME, nm, tags=["person/email"])
                    col.add_message_signal(NAME, nm, date)
            # NOTE: Subject and body are deliberately never accessed.

    # Purview result CSVs: sender/recipient columns → same signal
    for k, ps in list(file_index.items()):
        if not any(h in k for h in ("purview", "ediscovery")):
            continue
        for p in ps:
            if p.suffix.lower() != ".csv":
                continue
            consumed.add(norm_file(p.name))
            for r in read_csv(p):
                low = {(kk or "").lower().strip(): (v or "").strip()
                       for kk, v in r.items() if kk}
                date = iso_date(low.get("date sent") or low.get("sent") or "")
                for field in ("sender", "from", "recipients", "to"):
                    for nm in _names(low.get(field, "")):
                        people.add(nm)
                        col.add_person(NAME, nm, tags=["person/email"])
                        col.add_message_signal(NAME, nm, date)
                n_msgs += 1

    psts = [p.name for p in all_paths if p.suffix.lower() == ".pst"]
    if psts:
        col.note(f"[microsoft365] {len(psts)} PST archive(s) present — convert "
                 "first (`readpst -o out/ <file>.pst` → mbox) and re-run")
    if n_msgs:
        col.note(f"[microsoft365] {n_msgs} items → {len(people)} people "
                 "(headers only — subjects/bodies never read)")
    return consumed
