#!/usr/bin/env python3
"""
email_archive.py — MBOX email-archive adapter (company subject). SIGNAL ONLY.

Gmail Takeout / Google Vault (and anything else that speaks MBOX) is the
richest relationship + decision record a company has — and the most private.
We read HEADERS ONLY via the stdlib `mailbox` module: From/To/Cc display names
→ people, one per-person message SIGNAL per counterpart (count + last date).
Subjects and bodies are NEVER accessed; bare addresses without a display name
are skipped entirely (we never store third-party emails).

Outlook/M365 PST archives must be converted first (`readpst -o out/ file.pst`
emits mbox) — a documented, honest convert-first step; see microsoft365.py for
Purview .eml/.csv results.
"""
import email.utils
import mailbox

from ..common import norm_file, iso_date, EMAIL_RE

NAME = "email"
SUBJECT = "company"
QUARANTINE = set()
_MAX_MSGS = 200000  # defensive cap per archive


def detect(file_index):
    """True if a standalone .mbox archive is present. Stands DOWN when every
    mbox lives inside a Google Takeout tree (Takeout*/Mail/…): that's a
    PERSONAL Gmail export — excluded by design (a brain doesn't need your
    inbox), and firing there used to split a bogus company brain out of the
    owner's own mail headers. Drop the mbox under data/company/<co>/email/
    to build a Company Brain from it deliberately."""
    mboxes = [p for ps in file_index.values() for p in ps
              if p.suffix.lower() == ".mbox"]
    if not mboxes:
        return False

    def deliberate(p):
        # sitting under an email/ source folder = an intentional import, even
        # if the archive inside happens to be a Takeout
        parts = {seg.lower() for seg in p.parts}
        return "email" in parts or "takeout" not in str(p).lower()

    return any(deliberate(p) for p in mboxes)


def _names(header_value):
    """Display names from an address header — names only, never bare addresses."""
    out = []
    for nm, addr in email.utils.getaddresses([header_value or ""]):
        nm = (nm or "").strip().strip('"')
        if nm and not EMAIL_RE.search(nm):
            out.append(nm)
    return out


def extract(root, file_index, all_paths, col):
    """Header-only pass over every MBOX. Returns consumed keys."""
    consumed = set()
    n_msgs = 0
    people = set()
    for ps in list(file_index.values()):
        for p in ps:
            if p.suffix.lower() != ".mbox":
                continue
            consumed.add(norm_file(p.name))
            try:
                box = mailbox.mbox(str(p))
            except Exception:
                continue
            for msg in box:
                if n_msgs >= _MAX_MSGS:
                    break
                n_msgs += 1
                date = iso_date(email.utils.parsedate_to_datetime(
                    msg.get("Date", "")).strftime("%Y-%m-%d")) if msg.get("Date") else ""
                for hdr in ("From", "To", "Cc"):
                    for nm in _names(msg.get(hdr, "")):
                        people.add(nm)
                        col.add_person(NAME, nm, tags=["person/email"])
                        col.add_message_signal(NAME, nm, date)
                # NOTE: Subject and body are deliberately never accessed.
            box.close()

    # honest hint when a PST sits in the export unconverted
    psts = [p.name for p in all_paths if p.suffix.lower() == ".pst"]
    if psts:
        col.note(f"[email] {len(psts)} PST archive(s) present — convert first "
                 "(`readpst -o out/ <file>.pst` → mbox) and re-run")
    if n_msgs:
        col.note(f"[email] {n_msgs} messages → {len(people)} people "
                 "(headers only — subjects/bodies never read)")
    return consumed
