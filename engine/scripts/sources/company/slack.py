#!/usr/bin/env python3
"""
slack.py — Slack workspace export adapter (company subject).

A Slack export is a folder of JSON: `users.json` (members), `channels.json`, and
per-channel/day message files. We map members → people and messages → SIGNAL ONLY
(per-person count + last date) — NEVER bodies, identical to the LinkedIn/FB/IG
message rule. v1 scope: detect + members + message signal; channels become light
project/org notes. Roots the brain on the workspace (company subject).
"""
from ..common import read_json, nk, norm_file, iso_date

NAME = "slack"
SUBJECT = "company"


def _chan_tag(name):
    """Semantic tag slug for channel membership: '#cobot-v2 launch' → 'channel/cobot-v2-launch'."""
    import re
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"channel/{s}" if s else ""

# Slack exports have these signature files at the root.
SIGNATURE_FILES = ("users.json", "channels.json")
QUARANTINE = set()  # message bodies handled by signal-only rule, not quarantine


def detect(file_index):
    """True if the export looks like a Slack workspace: both users.json and
    channels.json present. Distinguished from a Google Workspace export (which
    also has a 'users' key) by FILE TYPE — Slack's users/channels are JSON,
    Workspace's users are CSV — so a combined company export containing BOTH
    sources still fires both adapters (an 'orgunits not present' guard used to
    silently disable Slack whenever Workspace files sat in the same entity)."""
    keys = set(file_index)
    if "channels" not in keys or "users" not in keys:
        return False
    return (any(p.suffix.lower() == ".json" for p in file_index.get("users", []))
            and any(p.suffix.lower() == ".json" for p in file_index.get("channels", [])))


def _name(u):
    """Best display name for a Slack user dict, preferring profile.real_name
    then display_name then the top-level real_name/name; "" if none."""
    p = u.get("profile") or {}
    return (p.get("real_name") or p.get("display_name") or u.get("real_name")
            or u.get("name") or "").strip()


def extract(root, file_index, all_paths, col):
    """Parse a Slack workspace export into the Collector (workspace identity,
    members -> people, channels -> orgs, messages -> signal only, never bodies).
    Roots the brain on the workspace. Returns consumed normalized filename keys."""
    consumed = set()
    col.subject = "company"

    # workspace name (best effort): a folder name or a team file
    ws = ""
    for p in all_paths:
        if p.name == "users.json":
            ws = p.parent.name
            break
    if ws:
        # Defer to a root entity another company adapter already established
        # (e.g. linkedin_company's org profile) — slack runs LAST alphabetically
        # and used to clobber subject_entity with the export folder name.
        col.set_identity(NAME, name=ws)     # first-non-empty merge, safe
        if not col.subject_entity:
            col.subject_entity = ws
        if nk(ws) == nk(col.subject_entity):
            col.add_org(NAME, ws, "self")
        else:
            col.add_org(NAME, ws, "workspace")

    # members → people
    users_paths = [p for p in all_paths if p.name == "users.json"]
    members = {}
    for up in users_paths:
        data = read_json(up) or []
        consumed.add("users")
        for u in (data if isinstance(data, list) else []):
            if u.get("is_bot") or u.get("deleted"):
                continue
            nm = _name(u)
            if not nm:
                continue
            members[u.get("id", nm)] = nm
            prof = u.get("profile") or {}
            # avatar_url = the profile image URL the export itself carries —
            # stored verbatim, never fetched (Studios use it only behind an
            # explicit opt-in network toggle).
            col.add_person(NAME, nm, company=col.subject_entity or ws,
                           role=prof.get("title", ""),
                           email=prof.get("email", ""),   # Collector strips unless --full
                           avatar_url=(prof.get("image_512")
                                       or prof.get("image_192") or ""))

    # channels → org notes carrying topic/purpose (extra, --full only) and, via
    # semantic person tags (channel/<slug>), WHO is in each channel — the
    # membership signal the who-knows-what analysis feeds on.
    chan_members = {}          # channel name -> set of member user ids
    for cp in [p for p in all_paths if p.name == "channels.json"]:
        data = read_json(cp) or []
        consumed.add("channels")
        for ch in (data if isinstance(data, list) else []):
            nm = ch.get("name")
            if not nm:
                continue
            topic = ((ch.get("topic") or {}).get("value") or "").strip()
            purpose = ((ch.get("purpose") or {}).get("value") or "").strip()
            about = " — ".join(x for x in (topic, purpose) if x)
            col.add_org(NAME, f"#{nm}", "channel", about=about,
                        extra={"topic": topic, "purpose": purpose},
                        tags=["org/channel"])
            ids = set(ch.get("members") or [])
            if ids:
                chan_members[nm] = ids
                tag = _chan_tag(nm)
                for uid in ids:
                    who = members.get(uid)
                    if who and tag:
                        col.add_person(NAME, who, tags=[tag])

    # messages → SIGNAL ONLY (never bodies). Slack message files are per-channel
    # folders of YYYY-MM-DD.json arrays of {user, ts, text}. We read user+ts only.
    id_to_name = members
    msg_files = [p for p in all_paths
                 if p.suffix.lower() == ".json" and p.name not in
                 ("users.json", "channels.json", "integration_logs.json")
                 and len(p.name) == len("2024-01-01.json")]
    n_sig = 0
    chan_activity = {}         # channel folder name -> message count
    for mp in msg_files:
        data = read_json(mp) or []
        # the per-day file lives inside its channel's folder — that folder name
        # is the channel; count activity per channel (frequency only, no content)
        chan = mp.parent.name
        # a message file IS handled here — mark it consumed so coverage doesn't
        # ALSO hand it to the harvester as "uncategorized" (real bug: the same
        # day-file was both signal-extracted and rescued into 99-uncategorized/)
        consumed.add(norm_file(mp.name))
        for m in (data if isinstance(data, list) else []):
            uid = m.get("user")
            ts = m.get("ts", "")
            who = id_to_name.get(uid, "")
            if who:
                # ts is a unix epoch float as string; iso_date handles it
                col.add_message_signal(NAME, who, str(ts).split(".")[0],
                                       ts=str(ts))
                n_sig += 1
                chan_activity[chan] = chan_activity.get(chan, 0) + 1
            # NOTE: m.get("text") deliberately NOT read.

    if members:
        act = ", ".join(f"#{c}: {n}" for c, n in
                        sorted(chan_activity.items(), key=lambda x: -x[1])[:10])
        col.note(f"[slack] workspace '{ws or '?'}': {len(members)} members, "
                 f"{len(chan_members)} channels with membership, "
                 f"{n_sig} message signals (bodies never read)"
                 + (f" · activity {act}" if act else ""))
    return consumed
