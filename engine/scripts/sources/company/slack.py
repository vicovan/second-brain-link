#!/usr/bin/env python3
"""
slack.py — Slack workspace export adapter (company subject).

A Slack export is a folder of JSON: `users.json` (members), `channels.json`, and
per-channel/day message files. We map members → people and messages → SIGNAL ONLY
(per-person count + last date) — NEVER bodies, identical to the LinkedIn/FB/IG
message rule. v1 scope: detect + members + message signal; channels become light
project/org notes. Roots the brain on the workspace (company subject).
"""
from ..common import read_json, nk, iso_date

NAME = "slack"
SUBJECT = "company"

# Slack exports have these signature files at the root.
SIGNATURE_FILES = ("users.json", "channels.json")
QUARANTINE = set()  # message bodies handled by signal-only rule, not quarantine


def detect(file_index):
    """True if the export looks like a Slack workspace: both users.json and
    channels.json present, and not a Workspace export (which also has 'users')."""
    # file_index is keyed by normalized filename; users/channels collapse to
    # "users"/"channels". Require both to avoid colliding with Workspace "users".
    keys = set(file_index)
    return "channels" in keys and "users" in keys and "orgunits" not in keys


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
        col.subject_entity = ws
        col.add_org(NAME, ws, "self")
        col.set_identity(NAME, name=ws)

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
            col.add_person(NAME, nm, company=ws,
                           role=prof.get("title", ""),
                           email=prof.get("email", ""))   # Collector strips unless --full

    # channels → light project notes
    for cp in [p for p in all_paths if p.name == "channels.json"]:
        data = read_json(cp) or []
        consumed.add("channels")
        for ch in (data if isinstance(data, list) else []):
            nm = ch.get("name")
            if nm:
                col.add_org(NAME, f"#{nm}", "channel")

    # messages → SIGNAL ONLY (never bodies). Slack message files are per-channel
    # folders of YYYY-MM-DD.json arrays of {user, ts, text}. We read user+ts only.
    id_to_name = members
    msg_files = [p for p in all_paths
                 if p.suffix.lower() == ".json" and p.name not in
                 ("users.json", "channels.json", "integration_logs.json")
                 and len(p.name) == len("2024-01-01.json")]
    n_sig = 0
    for mp in msg_files:
        data = read_json(mp) or []
        for m in (data if isinstance(data, list) else []):
            uid = m.get("user")
            ts = m.get("ts", "")
            who = id_to_name.get(uid, "")
            if who:
                # ts is a unix epoch float as string; iso_date handles it
                col.add_message_signal(NAME, who, str(ts).split(".")[0])
                n_sig += 1
            # NOTE: m.get("text") deliberately NOT read.

    if members:
        col.note(f"[slack] workspace '{ws or '?'}': {len(members)} members, "
                 f"{n_sig} message signals (bodies never read)")
    return consumed
