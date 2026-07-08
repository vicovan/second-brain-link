#!/usr/bin/env python3
"""
teams.py — Microsoft Teams (Purview message report) adapter (company subject).
SIGNAL ONLY.

Teams has no clean standalone export; compliance flows produce message reports
(CSV, sometimes JSON) whose filenames carry "teams". Same rule as Slack:
sender display names → people, channels/teams → orgs, one per-person message
SIGNAL per row. Message content columns are never read.
"""
import re

from ..common import read_csv, read_json, norm_file, iso_date, EMAIL_RE

NAME = "teams"
SUBJECT = "company"
QUARANTINE = set()


def detect(file_index):
    """True if a Teams-named message report (csv/json) is present."""
    return any("teams" in k and any(p.suffix.lower() in (".csv", ".json") for p in ps)
               for k, ps in file_index.items())


def _chan_tag(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"channel/{s}" if s else ""


def extract(root, file_index, all_paths, col):
    """Parse Teams message reports into the Collector. Returns consumed keys."""
    consumed = set()
    col.subject = "company"
    n_sig = 0
    channels = set()

    def one(sender, team, channel, date):
        nonlocal n_sig
        sender = (sender or "").strip()
        if not sender or EMAIL_RE.search(sender):
            return
        tag = _chan_tag(channel or team)
        col.add_person(NAME, sender, tags=[t for t in (tag,) if t])
        col.add_message_signal(NAME, sender, date)
        for nm, cat in ((team, "team"), (channel, "channel")):
            nm = (nm or "").strip()
            if nm and nm not in channels:
                channels.add(nm)
                col.add_org(NAME, nm if cat == "team" else f"#{nm}", cat,
                            tags=[f"org/{cat}"])
        n_sig += 1

    for k, ps in list(file_index.items()):
        if "teams" not in k:
            continue
        for p in ps:
            if p.suffix.lower() == ".csv":
                consumed.add(norm_file(p.name))
                for r in read_csv(p):
                    low = {(kk or "").lower().strip(): (v or "").strip()
                           for kk, v in r.items() if kk}
                    one(low.get("sender") or low.get("from") or low.get("sender name"),
                        low.get("team"), low.get("channel") or low.get("channel name"),
                        iso_date(low.get("date") or low.get("timestamp")
                                 or low.get("created date") or ""))
                    # NOTE: low.get("message")/("content") deliberately NOT read.
            elif p.suffix.lower() == ".json":
                consumed.add(norm_file(p.name))
                data = read_json(p) or []
                if isinstance(data, dict):
                    data = next((v for v in data.values() if isinstance(v, list)), [])
                for m in (data if isinstance(data, list) else []):
                    if not isinstance(m, dict):
                        continue
                    frm = m.get("from") or {}
                    user = (frm.get("user") or {}) if isinstance(frm, dict) else {}
                    chan = (m.get("channelIdentity") or {})
                    one(user.get("displayName", ""),
                        m.get("teamName", ""),
                        chan.get("channelName", "") if isinstance(chan, dict) else "",
                        iso_date(str(m.get("createdDateTime", ""))[:10]))
                    # NOTE: m.get("body") deliberately NOT read.

    if n_sig:
        col.note(f"[teams] {n_sig} message signals across {len(channels)} teams/"
                 "channels (bodies never read)")
    return consumed
