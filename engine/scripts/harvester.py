#!/usr/bin/env python3
"""
harvester.py — the universal, deterministic shape recognizer.

Runs over every indexed file that NO source/mapping claimed, so the brain never
loses data even from an unknown export format. It recognizes a handful of common
shapes and pushes them through col.add_* (privacy still enforced in the Collector).
Anything it still can't place is recorded for the coverage report under "needs a
mapping" with its detected shape — the cue for the agent to write a mapping JSON.

This is best-effort and COARSE on purpose: a real mapping always beats it. No AI,
no eval — pure structural heuristics.
"""
from sources.common import read_json, read_csv, walk_json_arrays, iso_date, nk

# field-name hints
NAME_KEYS = ("name", "full_name", "fullname", "display_name", "username", "value", "title")
HANDLE_KEYS = ("username", "value", "handle", "screen_name")
PLACE_NAME_KEYS = ("name", "title", "place_name")
ADDR_KEYS = ("address", "formatted_address", "location")


def _g(d, *keys):
    """Pluck the first non-empty scalar from dict `d` for the given keys (in order),
    returning it stripped as str, or "" if none match. Also unwraps Instagram-style
    {"value": ...} / {"name": ...} single-level wrappers."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
        if isinstance(v, dict):                       # IG {"value": ...}
            inner = v.get("value") or v.get("name")
            if isinstance(inner, (str, int, float)) and str(inner).strip():
                return str(inner).strip()
    return ""


def _handles(d):
    """IG-style string_list_data wrapper → [(value, href, ts)]."""
    out = []
    sld = d.get("string_list_data")
    if isinstance(sld, list):
        for s in sld:
            if isinstance(s, dict) and s.get("value"):
                out.append((str(s["value"]), s.get("href", ""), s.get("timestamp", "")))
    return out


def _classify_record(col, source, d):
    """Try to place one dict record. Returns the bucket name it hit, or ''. """
    if not isinstance(d, dict):
        return ""
    # message signal (never body)
    if d.get("sender_name") and ("timestamp_ms" in d or "timestamp" in d):
        ts = d.get("timestamp_ms") or d.get("timestamp")
        ds = iso_date(int(ts) // 1000) if str(ts).isdigit() and len(str(ts)) >= 12 else str(ts)
        col.add_message_signal(source, d["sender_name"], ds)
        return "message_signal"
    # IG string_list_data accounts → people/handles
    hs = _handles(d)
    if hs:
        for val, href, ts in hs:
            col.add_person(source, val, handle=val, url=href, date=str(ts))
        return "person"
    # geo place: explicit lat/lng or GeoJSON-ish
    lat = d.get("latitude") or d.get("lat")
    lng = d.get("longitude") or d.get("lng") or d.get("lon")
    if (lat and lng) or (isinstance(d.get("geometry"), dict)
                         and isinstance(d["geometry"].get("coordinates"), list)):
        props = d.get("properties") if isinstance(d.get("properties"), dict) else d
        coords = (d.get("geometry") or {}).get("coordinates") if isinstance(d.get("geometry"), dict) else [lng, lat]
        loc = props.get("location") if isinstance(props.get("location"), dict) else {}
        nm = _g(props, *PLACE_NAME_KEYS) or (loc.get("name") if isinstance(loc, dict) else "") \
            or _g(d, *PLACE_NAME_KEYS)
        if nm:
            addr = (loc.get("address") if isinstance(loc, dict) else "") or _g(props, "address")
            col.add_place(source, name=nm, address=addr,
                          lng=(coords[0] if coords else ""), lat=(coords[1] if coords and len(coords) > 1 else ""),
                          url=_g(props, "google_maps_url", "url"),
                          note=_g(props, "review_text_published", "review"))
            return "place"
    # person by name + (company|url|email-less)
    nm = _g(d, "name", "full_name", "fullname", "display_name")
    if nm and (d.get("company") or d.get("url") or d.get("profile_url") or d.get("title")):
        col.add_person(source, nm, company=_g(d, "company"),
                       role=_g(d, "title", "position", "role"),
                       url=_g(d, "url", "profile_url"))
        return "person"
    # post/voice: free text + a timestamp
    txt = _g(d, "title", "caption", "text", "content", "post")
    if txt and (d.get("timestamp") or d.get("creation_timestamp") or d.get("date")):
        col.add_post(source, txt, date=iso_date(_g(d, "creation_timestamp", "timestamp", "date")), kind="post")
        return "post"
    # IG string_map_data → interests
    smd = d.get("string_map_data")
    if isinstance(smd, dict):
        hit = False
        for v in smd.values():
            if isinstance(v, dict) and v.get("value"):
                col.add_interest(source, str(v["value"])); hit = True
        if hit:
            return "interest"
    return ""


def harvest(col, source, path):
    """Harvest one unclaimed file. Returns (hits:int, detected_shape:str)."""
    suffix = path.suffix.lower()
    hits = 0
    shape = ""
    try:
        if suffix == ".csv":
            rows = read_csv(path)
            for r in rows:
                if _classify_record(col, source, r):
                    hits += 1
            shape = f"csv:{len(rows)} rows, cols={list(rows[0].keys())[:6] if rows else []}"
        elif suffix == ".json":
            data = read_json(path)
            # try the obvious arrays first, then a deep walk
            arrays = []
            if isinstance(data, list):
                arrays = [data]
            elif isinstance(data, dict):
                if isinstance(data.get("features"), list):
                    arrays = [data["features"]]
                else:
                    arrays = walk_json_arrays(data, NAME_KEYS + ("sender_name", "string_list_data",
                                              "string_map_data", "geometry", "latitude"))
            seen_ids = set()
            for arr in arrays:
                if id(arr) in seen_ids:
                    continue
                seen_ids.add(id(arr))
                for rec in arr:
                    if _classify_record(col, source, rec):
                        hits += 1
            top = list(data.keys())[:6] if isinstance(data, dict) else f"list[{len(data)}]"
            shape = f"json:{top}"
    except Exception as e:
        shape = f"unreadable: {e}"
    return hits, shape
