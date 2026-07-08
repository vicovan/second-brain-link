#!/usr/bin/env python3
"""
youtube.py — standalone YouTube Takeout-slice adapter (personal subject).

For when a user exports ONLY the "YouTube and YouTube Music" slice of Google
Takeout (arguably the strongest interest graph in existence): watch history →
channel interests, search history → 80-search, subscriptions.csv → interests,
comments → voice, playlists → interests. A FULL Takeout (which contains the
same folder) is left to the `google` adapter — detect() stands down when
Takeout-wide signals are present so the two never double-import.
"""
import re

from ..common import read_csv, read_json, norm_file, iso_date
from ._youtube_common import watch_channels, search_queries

NAME = "youtube"
SUBJECT = "person"
QUARANTINE = set()

_WATCHED = re.compile(r"^(?:Watched|Angesehen:?|Vistos?:?)\s+", re.I)
_SEARCHED = re.compile(r"^(?:Searched for|Gesucht nach|Buscaste)\s+", re.I)


def detect(file_index):
    """True for a standalone YouTube slice; defers to the google adapter for a
    full Takeout (same files, wider export)."""
    keys = set(file_index)
    if not ({"watchhistory", "searchhistory", "subscriptions"} & keys):
        return False
    blob = " ".join(str(p).lower() for ps in file_index.values() for p in ps)
    if "youtube" not in blob:
        return False
    # full-Takeout markers → the google adapter owns this export
    full = {"contacts", "savedplaces", "myactivity", "reviews"} & keys
    return not full


def extract(root, file_index, all_paths, col):
    """Parse the YouTube slice into the Collector. Returns consumed keys."""
    consumed = set()

    def paths(key, suffix):
        out = []
        for p in file_index.get(key, []):
            if p.suffix.lower() == suffix:
                out.append(p)
                consumed.add(norm_file(p.name))
        return out

    # watch history (JSON preferred; HTML fallback via the shared parser that
    # google.py uses on full Takeouts — one regex, two adapters, zero drift)
    n_watch = 0
    for p in paths("watchhistory", ".json"):
        for e in (read_json(p) or []):
            if not isinstance(e, dict):
                continue
            n_watch += 1
            for sub in e.get("subtitles") or []:
                ch = (sub.get("name") or "").strip()
                if ch:
                    col.add_interest(NAME, ch)
    if not n_watch:
        for p in paths("watchhistory", ".html"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for ch in watch_channels(text):
                col.add_interest(NAME, ch)
                n_watch += 1

    # search history → 80-search (JSON preferred; HTML fallback)
    n_q = 0
    for p in paths("searchhistory", ".json"):
        for e in (read_json(p) or []):
            t = (e.get("title") or "") if isinstance(e, dict) else ""
            q = _SEARCHED.sub("", t).strip()
            if q and q != t:
                col.add_search(NAME, q)
                n_q += 1
    if not n_q:
        for p in paths("searchhistory", ".html"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for q in search_queries(text):
                col.add_search(NAME, q)
                n_q += 1

    # subscriptions.csv → interests (the channels the owner chose)
    for p in paths("subscriptions", ".csv"):
        for r in read_csv(p):
            ch = (r.get("Channel Title") or r.get("Channel title") or "").strip()
            if ch:
                col.add_interest(NAME, ch)

    # comments → voice
    for key in ("comments", "mycomments"):
        for p in paths(key, ".csv"):
            for r in read_csv(p):
                txt = (r.get("Comment Text") or r.get("Comment text") or "").strip()
                if txt:
                    col.add_comment(NAME, txt,
                                    iso_date(r.get("Comment Create Timestamp")
                                             or r.get("Timestamp") or ""))

    # playlists.csv (index of playlists) → interests
    for p in paths("playlists", ".csv"):
        for r in read_csv(p):
            t = (r.get("Playlist Title (Original)") or r.get("Title") or "").strip()
            if t:
                col.add_interest(NAME, f"playlist: {t}")

    # per-playlist <name>-videos.csv → video titles when present, else the
    # playlist name (newer exports are ID-only — a wall of video ids is noise)
    for ps in list(file_index.values()):
        for p in ps:
            if p.suffix.lower() != ".csv" or not p.name.lower().endswith("-videos.csv"):
                continue
            consumed.add(norm_file(p.name))
            pl_name = re.sub(r"-videos$", "", p.stem, flags=re.I).strip()
            titled = 0
            for r in read_csv(p):
                t = (r.get("Video Title") or r.get("Title") or "").strip()
                if t:
                    col.add_interest(NAME, t)
                    titled += 1
            if not titled and pl_name:
                col.add_interest(NAME, f"playlist: {pl_name}")

    if n_watch or n_q:
        col.note(f"[youtube] {n_watch} watch entries → interests, {n_q} searches")
    return consumed
