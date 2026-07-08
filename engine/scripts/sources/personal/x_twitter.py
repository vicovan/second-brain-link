#!/usr/bin/env python3
"""
x_twitter.py — X / Twitter archive adapter (personal subject).

An X archive ("Settings → Download an archive") ships a `data/` folder of `.js`
files, each a JSON payload behind a `window.YTD.<name>.part0 =` preamble (the
same strip-the-preamble drift LinkedIn's "Notes:" line taught us). We map:
tweets → voice (the richest public-voice corpus most people own), likes →
interests (aggregate count only), following/followers → people (handle +
profile url), account/profile → identity. DMs are NEVER read as bodies —
`direct-messages.js` is quarantined outright (signal isn't worth parsing the
thread structure v1).
"""
import json
import re

from ..common import norm_file, iso_date

NAME = "x"
SUBJECT = "person"

# NOTE: X's imported-address-book file is `contact.js`, but quarantine keys are
# GLOBAL (the union of every adapter's set) and "contact" would swallow
# Salesforce's Contact.csv — so contact.js is skipped explicitly in extract()
# instead of quarantined by key.
QUARANTINE = {"directmessages", "directmessagesgroup", "directmessageheaders",
              "emailaddresschanges", "phonenumber", "ipaudit",
              "devicetoken", "savedsearch", "mute", "block"}

_PREAMBLE = re.compile(r"^\s*window\.YTD\.[\w.]+\s*=\s*", re.S)


def detect(file_index):
    """True if the export looks like an X/Twitter archive: the signature .js
    payload files (tweets/tweet + account/following) are present."""
    keys = set(file_index)
    js = {k for k, ps in file_index.items() if any(p.suffix.lower() == ".js" for p in ps)}
    return bool(({"tweets", "tweet"} & js) or ({"account", "following"} <= js))


def _read_ytd(path):
    """Read a window.YTD `.js` payload → the parsed JSON list (or [])."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            txt = path.read_text(encoding=enc)
            return json.loads(_PREAMBLE.sub("", txt).rstrip().rstrip(";"))
        except Exception:
            continue
    return []


def extract(root, file_index, all_paths, col):
    """Parse an X archive into the Collector. Returns consumed norm_file keys."""
    consumed = set()
    # imported phone-book contacts — pure third-party PII; handled = skipped
    for p in file_index.get("contact", []):
        if p.suffix.lower() == ".js":
            consumed.add(norm_file(p.name))
            col.note("[x] contact.js skipped (imported address book — never stored)")

    def files(*keys):
        out = []
        for k in keys:
            for p in file_index.get(k, []):
                if p.suffix.lower() == ".js":
                    out.append(p)
                    consumed.add(norm_file(p.name))
        return out

    # account / profile → identity
    for p in files("account"):
        for rec in _read_ytd(p):
            a = (rec or {}).get("account") or {}
            col.set_identity(NAME, name=a.get("accountDisplayName", ""),
                             handle=a.get("username", ""))
            if a.get("username"):
                col.identity.setdefault("handles", set()).add("@" + a["username"])
    for p in files("profile"):
        for rec in _read_ytd(p):
            pr = (rec or {}).get("profile") or {}
            col.set_identity(NAME, headline=(pr.get("description") or {}).get("bio", ""),
                             location=pr.get("location", ""))

    # tweets → voice
    n_tw = 0
    for p in files("tweets", "tweet"):
        for rec in _read_ytd(p):
            t = (rec or {}).get("tweet") or {}
            txt = t.get("full_text") or t.get("text") or ""
            if not txt or txt.startswith("RT @"):
                continue  # retweets aren't the owner's voice
            col.add_post(NAME, txt, iso_date(t.get("created_at", "")), "tweet",
                         tags=["post/tweet"])
            n_tw += 1

    # note-tweets (long-form posts) → voice — often the richest writing in an archive
    n_note = 0
    for p in files("notetweet", "notetweets"):
        for rec in _read_ytd(p):
            nt = (rec or {}).get("noteTweet") or {}
            txt = ((nt.get("core") or {}).get("text") or "").strip()
            if txt:
                col.add_post(NAME, txt, iso_date(nt.get("createdAt", "")),
                             "note-tweet", tags=["post/note-tweet"])
                n_note += 1

    # lists (owned / subscribed) → interests (what the owner curates/follows)
    for p in files("lists", "list", "listscreated", "listssubscribed"):
        for rec in _read_ytd(p):
            info = (rec or {}).get("userListInfo") or (rec or {}).get("list") or {}
            nm = (info.get("name") or "").strip()
            if nm:
                col.add_interest(NAME, f"list: {nm}")

    # verified badge → identity detail (harmless public fact)
    for p in files("verified"):
        for rec in _read_ytd(p):
            v = (rec or {}).get("verified") or {}
            if v.get("verified"):
                col.set_identity(NAME, headline=col.identity.get("headline", ""))
                col.identity.setdefault("extra", {})["verified"] = "yes"

    # likes → interests (aggregate; liked-tweet text is other people's words —
    # count the signal, don't store the content)
    n_like = 0
    for p in files("like"):
        for _ in _read_ytd(p):
            n_like += 1
    if n_like:
        col.add_reaction(NAME, "like")
        col.reactions["like"] += n_like - 1

    # following / followers → people (handle + public profile link)
    for key, role in (("following", "following"), ("follower", "follower"),
                      ("followers", "follower")):
        for p in files(key):
            for rec in _read_ytd(p):
                f = (rec or {}).get(key) or (rec or {}).get("follower") \
                    or (rec or {}).get("following") or {}
                link = f.get("userLink", "")
                # archives carry accountId + userLink only; screen name is the
                # link tail — a handle, not an email (safe to store)
                handle = link.rsplit("/", 1)[-1] if link else ""
                nm = f.get("name") or f.get("screenName") or handle
                if nm and not nm.isdigit():
                    col.add_person(NAME, nm, handle=handle, url=link,
                                   role=f"x {role}", tags=[f"person/{role}"])

    if n_tw:
        col.note(f"[x] {n_tw} tweets (voice), {n_like} likes (count only)")
    return consumed
