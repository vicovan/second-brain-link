#!/usr/bin/env python3
"""
_youtube_common.py — shared YouTube parsing helpers (private; not an adapter).

YouTube data reaches the engine two ways: inside a FULL Google Takeout (owned by
google.py) and as a standalone "YouTube and YouTube Music" slice (owned by
youtube.py). Both must parse the same file shapes — these helpers keep the two
adapters from drifting (the HTML history regexes especially).
"""
import html as _html
import re

# The proven patterns from google.py (validated on real Takeout HTML):
# watch-history.html channel anchors / search-history.html query anchors.
RE_CHANNEL = re.compile(
    r'href="https://www\.youtube\.com/(?:channel/|user/|@)[^"]+">([^<]+)</a>')
RE_QUERY = re.compile(
    r'href="https://www\.youtube\.com/results\?search_query=[^"]*">([^<]+)</a>')


def watch_channels(text, cap=500):
    """Channel names from watch-history.html, deduped, capped."""
    out, seen = [], set()
    for raw in RE_CHANNEL.findall(text):
        ch = _html.unescape(raw).strip()
        k = re.sub(r"[^a-z0-9]", "", ch.lower())
        if ch and k and k not in seen:
            seen.add(k)
            out.append(ch)
            if len(out) >= cap:
                break
    return out


def search_queries(text, cap=500):
    """Query strings from search-history.html, capped."""
    out = []
    for raw in RE_QUERY.findall(text):
        q = _html.unescape(raw).strip()
        if q:
            out.append(q)
            if len(out) >= cap:
                break
    return out
