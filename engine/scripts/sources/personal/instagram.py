#!/usr/bin/env python3
"""
Instagram adapter — JSON export ("Download your information", JSON).
Core coverage: profile, followers + following (as people/handles), your posts &
captions (voice), liked/saved topics (interests), message signal (no bodies).
Defensive against Instagram's string_list_data wrapper shape and folder drift.
"""
import re
from ..common import read_json, walk_json_arrays, fix_mojibake, iso_date, nk

NAME = "instagram"
SIGNATURE = ("followers", "following", "personalinformation", "yourinstagramactivity",
             "instagramprofile", "connections")

def detect(file_index):
    """True if the export looks like an Instagram download; disambiguates from
    Facebook via an 'instagram' path hint or follower/following filenames."""
    keys = set(file_index)
    if any(k.startswith(s) for s in SIGNATURE for k in keys):
        # disambiguate from facebook by path hint where possible
        return any("instagram" in k for k in keys) or any(
            k.startswith(("followers", "following")) for k in keys)
    return any("instagram" in k for k in keys)

def _handles_from(d):
    """Instagram stores accounts as string_list_data:[{value,href,timestamp}]."""
    out = []
    sld = d.get("string_list_data")
    if isinstance(sld, list):
        for s in sld:
            if isinstance(s, dict) and s.get("value"):
                out.append((s["value"], s.get("timestamp", ""), s.get("href", "")))
    elif d.get("value"):
        out.append((d["value"], d.get("timestamp", ""), d.get("href", "")))
    return out

def extract(root, file_index, all_paths, col):
    """Parse an Instagram JSON export into the Collector (profile -> identity,
    followers/following -> people, posts/captions -> voice, topics -> interests,
    message signal). Returns the set of consumed normalized filename keys."""
    consumed = set()

    def jsons(*subs):
        """Return all .json paths whose lowercased path contains any substring."""
        return [p for p in all_paths if p.suffix.lower() == ".json"
                and any(s in str(p).lower() for s in subs)]

    # profile / personal information
    for p in jsons("personal_information", "personalinformation", "instagram_profile", "profile"):
        data = read_json(p)
        if not data:
            continue
        for arr in walk_json_arrays(data, ("string_map_data", "title", "value")):
            pass
        # personal info often a dict of fields
        name = None
        def find_name(o):
            """Recursively search the profile object for a display name, setting
            the enclosing `name` on first hit (string_map_data or name fields)."""
            nonlocal name
            if name: return
            if isinstance(o, dict):
                # Instagram profile: string_map_data -> {"Name": {"value": "..."}}
                smd = o.get("string_map_data")
                if isinstance(smd, dict):
                    for k, v in smd.items():
                        if "name" in k.lower() and isinstance(v, dict) and v.get("value"):
                            name = v["value"]; return
                for k, v in o.items():
                    if k.lower() in ("name", "full_name") and isinstance(v, str) and v.strip():
                        name = v; return
                    find_name(v)
            elif isinstance(o, list):
                for it in o: find_name(it)
        find_name(data)
        if name:
            col.set_identity(NAME, name=name)
        consumed.add(nk(p.name))

    # followers / following -> people (by handle)
    pc = 0
    for p in jsons("followers", "following"):
        data = read_json(p)
        if data is None:
            continue
        # the account list is either the top-level list, or under a relationships_* key
        if isinstance(data, list):
            arr = data
        else:
            arr = []
            for k, v in data.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    arr = v; break
        rel = "follower" if "follower" in p.name.lower() else "following"
        for d in arr:
            if not isinstance(d, dict):
                continue
            for handle, ts, href in _handles_from(d):
                col.add_person(NAME, handle, role=f"instagram {rel}",
                               date=ts, handle=handle, url=href)
                pc += 1
        consumed.add(nk(p.name))
    if pc:
        col.note(f"[instagram] {pc} follower/following accounts")

    # posts & captions -> voice
    vc = 0
    for p in jsons("/posts", "posts_1", "media", "content/posts"):
        data = read_json(p)
        if data is None:
            continue
        items = data if isinstance(data, list) else data.get("media") or []
        for d in items if isinstance(items, list) else []:
            if not isinstance(d, dict):
                continue
            cap = d.get("title") or d.get("caption") or ""
            if not cap and isinstance(d.get("media"), list) and d["media"]:
                cap = d["media"][0].get("title", "")
            ts = d.get("creation_timestamp") or d.get("timestamp") or ""
            if cap:
                col.add_post(NAME, cap, iso_date(ts), "post")
                vc += 1
        consumed.add(nk(p.name))
    if vc:
        col.note(f"[instagram] {vc} posts/captions")

    # topics / interests
    for p in jsons("your_topics", "topics", "interests", "ads_interests", "recommended_topics"):
        data = read_json(p)
        if data is None:
            continue
        _seen = set()
        def harvest(o):
            """Recursively walk a topics/interests object and push every value
            it finds as an interest; dedupes nodes by id() to avoid re-visiting."""
            if id(o) in _seen:
                return
            _seen.add(id(o))
            if isinstance(o, dict):
                smd = o.get("string_map_data")
                if isinstance(smd, dict):
                    for v in smd.values():
                        if isinstance(v, dict) and v.get("value"):
                            col.add_interest(NAME, v["value"])
                if o.get("value") and "string_map_data" not in o:
                    col.add_interest(NAME, o["value"])
                for v in o.values():
                    harvest(v)
            elif isinstance(o, list):
                for it in o:
                    harvest(it)
        harvest(data)
        consumed.add(nk(p.name))

    # message signal (no bodies)
    mc = 0
    for p in all_paths:
        if p.name.lower().startswith("message_") and p.suffix.lower() == ".json" \
           and "instagram" in str(p).lower():
            data = read_json(p)
            if not isinstance(data, dict):
                continue
            for m in data.get("messages", []) if isinstance(data.get("messages"), list) else []:
                sender = m.get("sender_name")
                ts = m.get("timestamp_ms")
                if sender:
                    col.add_message_signal(NAME, sender, iso_date(int(ts)//1000) if ts else "")
                    mc += 1
            consumed.add(nk(p.name))
    if mc:
        col.note(f"[instagram] message signal from {mc} messages (bodies dropped)")

    return consumed
