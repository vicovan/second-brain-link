#!/usr/bin/env python3
"""
Facebook adapter — JSON export ("Download your information", JSON format).

NOTE: this is a RESILIENCE FALLBACK. The declarative JSON mapping
(engine/mappings/sources/facebook.json) WINS over this module (mapping-wins-over-
.py) and is the authoritative, comprehensive Facebook path. This adapter only runs
if that mapping is removed; it covers the core (profile, friends, posts, liked
pages, message signal) defensively, tolerating the wrapper-key/folder-layout drift
across Facebook export versions.
"""
import re
from pathlib import Path
from ..common import read_json, walk_json_arrays, fix_mojibake, iso_date, norm_file

NAME = "facebook"
SIGNATURE_DIRS = ("friends_and_followers", "connections", "profile_information",
                  "your_posts", "your_facebook_activity", "ads_information",
                  "posts", "messages")
SIGNATURE_FILES = ("friends", "profileinformation", "yourposts", "yourposts1",
                   "yourfriends")

def detect(file_index):
    """True if the export looks like a Facebook download (signature filename
    prefix present, or any path mentions 'facebook')."""
    keys = set(file_index)
    if any(k.startswith(s) for s in SIGNATURE_FILES for k in keys):
        return True
    # path-based hint
    return any("facebook" in k for k in keys)

def _text_from_post(d):
    """Pull the text body out of a single Facebook post dict, tolerating the
    several wrapper shapes FB has shipped; returns "" when none found."""
    # FB posts: data:[{post:"..."}] or {message:""} or {data:[{post}]}
    if isinstance(d.get("data"), list):
        for item in d["data"]:
            if isinstance(item, dict) and item.get("post"):
                return item["post"]
    return d.get("post") or d.get("message") or d.get("title") or ""

def extract(root, file_index, all_paths, col):
    """Parse a Facebook JSON export into the Collector (identity, friends,
    posts, liked pages -> interests, message signal). Returns the set of
    consumed normalized filename keys."""
    consumed = set()

    def jsons(*name_substrings):
        """Return all .json paths whose lowercased path contains any of the
        given substrings (folder layout drifts, so match on path not name)."""
        out = []
        for p in all_paths:
            if p.suffix.lower() != ".json":
                continue
            rel = str(p).lower()
            if any(s in rel for s in name_substrings):
                out.append(p)
        return out

    # profile
    for p in jsons("profile_information", "profileinformation"):
        data = read_json(p)
        if not data:
            continue
        prof = data.get("profile_v2") or data.get("profile") or data
        if isinstance(prof, dict):
            name = prof.get("name")
            if isinstance(name, dict):
                name = name.get("full_name")
            col.set_identity(NAME, name=name,
                             location=(prof.get("current_city") or {}).get("name")
                             if isinstance(prof.get("current_city"), dict) else prof.get("current_city"),
                             about=prof.get("about_me") or prof.get("bio"))
        consumed.add(norm_file(p.name))

    # friends
    fr = 0
    for p in jsons("friends"):
        data = read_json(p)
        if data is None:
            continue
        for arr in walk_json_arrays(data, ("name",)):
            for d in arr:
                nm = d.get("name")
                if nm:
                    col.add_person(NAME, nm, date=d.get("timestamp", ""))
                    fr += 1
        consumed.add(norm_file(p.name))
    if fr:
        col.note(f"[facebook] {fr} friends")

    # posts
    pc = 0
    for p in jsons("your_posts", "yourposts", "/posts/"):
        data = read_json(p)
        if data is None:
            continue
        items = data if isinstance(data, list) else data.get("status_updates") or []
        if isinstance(items, dict):
            items = [items]
        for d in items if isinstance(items, list) else []:
            if not isinstance(d, dict):
                continue
            text = _text_from_post(d)
            if text:
                col.add_post(NAME, text, d.get("timestamp", ""), "post")
                pc += 1
        consumed.add(norm_file(p.name))
    if pc:
        col.note(f"[facebook] {pc} posts")

    # pages liked / followed -> interests/orgs
    for p in jsons("pages", "likes_and_reactions", "your_pages"):
        data = read_json(p)
        if data is None:
            continue
        for arr in walk_json_arrays(data, ("name",)):
            for d in arr:
                if d.get("name"):
                    col.add_interest(NAME, d["name"])
        consumed.add(norm_file(p.name))

    # message signal (participants + timestamps only; NEVER message text)
    mc = 0
    for p in all_paths:
        if p.name.lower().startswith("message_") and p.suffix.lower() == ".json":
            data = read_json(p)
            if not isinstance(data, dict):
                continue
            parts = [pp.get("name") for pp in data.get("participants", []) if isinstance(pp, dict)]
            msgs = data.get("messages", [])
            # derive per-participant count + last timestamp; ignore 'content'
            for m in msgs if isinstance(msgs, list) else []:
                sender = m.get("sender_name")
                ts = m.get("timestamp_ms")
                d = iso_date(int(ts) // 1000) if ts else ""
                if sender:
                    col.add_message_signal(NAME, sender, d)
                    mc += 1
            consumed.add(norm_file(p.name))
    if mc:
        col.note(f"[facebook] message signal from {mc} messages (bodies dropped)")

    return consumed
