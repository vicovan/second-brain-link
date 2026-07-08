#!/usr/bin/env python3
"""
whatsapp.py — WhatsApp exported-chat adapter (personal subject). SIGNAL ONLY.

WhatsApp's per-chat "Export chat" produces `WhatsApp Chat with <name>.txt`
transcripts. Message BODIES are never stored — each line is parsed only up to
`<sender>: ` for the sender name + timestamp, feeding the same per-person
count/last-contact signal as LinkedIn/FB/IG/Slack messages. That contact-graph
signal (who you actually talk to, how often, how recently) is the only thing a
brain needs from a chat export; the words stay private.
"""
import re

from ..common import norm_file, EMAIL_RE

NAME = "whatsapp"
SUBJECT = "person"
QUARANTINE = set()

# "12/31/23, 21:05 - John Doe: …"  ·  "[31.12.2023, 21:05:59] John Doe: …"
_LINE = re.compile(
    r"^\[?(\d{1,2})[./](\d{1,2})[./](\d{2,4}),?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AP]M)?\]?\s*[-–]?\s*"
    r"([^:\n]{1,60}):\s")
_SYSTEM = ("Messages and calls are end-to-end encrypted",
           "created group", "added you", "changed the subject",
           "changed this group's icon", "joined using this group's invite")


def detect(file_index):
    """True if any exported-chat transcript is present."""
    return any(k.startswith("whatsappchatwith") or k.startswith("whatsappchat")
               for k in file_index)


def _iso(d1, d2, y, dayfirst):
    """ISO date from the two ambiguous day/month fields, using the per-chat
    day-first/month-first decision (a single chat never mixes formats)."""
    y = int(y)
    if y < 100:
        y += 2000
    a, b = int(d1), int(d2)
    d, m = (a, b) if dayfirst else (b, a)
    if m > 12 or d > 31 or m < 1 or d < 1:
        return ""
    return f"{y:04d}-{m:02d}-{d:02d}"


def extract(root, file_index, all_paths, col):
    """Parse chat transcripts → people + message SIGNAL (never bodies).
    Returns consumed norm_file keys."""
    consumed = set()
    chats = [p for k, ps in file_index.items()
             if k.startswith(("whatsappchatwith", "whatsappchat"))
             for p in ps if p.suffix.lower() == ".txt"]
    n_sig = 0
    for p in chats:
        consumed.add(norm_file(p.name))
        # the chat partner (or group name) from the filename
        m = re.match(r"whatsapp chat with (.+)$", p.stem, re.I)
        partner = m.group(1).strip() if m else ""
        if partner and not EMAIL_RE.search(partner):
            col.add_person(NAME, partner, tags=["person/chat"])
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        # decide the chat's date order ONCE: any first-field > 12 → day-first
        # (dd/mm), any second-field > 12 → month-first; default day-first (the
        # WhatsApp-majority locale). One chat never mixes formats.
        matches = [m for m in (_LINE.match(ln) for ln in lines) if m]
        dayfirst = True
        if not any(int(m.group(1)) > 12 for m in matches) and \
                any(int(m.group(2)) > 12 for m in matches):
            dayfirst = False
        for ln in lines:
            lm = _LINE.match(ln)
            if not lm:
                continue  # continuation line of a message body — never read
            sender = lm.group(4).strip()
            if (not sender or EMAIL_RE.search(sender)
                    or any(s in ln for s in _SYSTEM)):
                continue
            date = _iso(lm.group(1), lm.group(2), lm.group(3), dayfirst)
            col.add_person(NAME, sender, tags=["person/chat"])
            # ts = date + the raw time prefix of the line → idempotent signal
            # when the same exported chat is dropped in again later
            col.add_message_signal(NAME, sender, date,
                                   ts=f"{date} {ln[:24]}")
            n_sig += 1
            # NOTE: everything after "<sender>: " is deliberately NOT read.
    if chats:
        col.note(f"[whatsapp] {len(chats)} chats → {n_sig} message signals "
                 "(bodies never read)")
    return consumed
