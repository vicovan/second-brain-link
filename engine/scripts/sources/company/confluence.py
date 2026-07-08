#!/usr/bin/env python3
"""
confluence.py — Confluence space-export adapter (company subject).

A space admin's "Export space" produces either an XML export (entities.xml +
exportDescriptor.properties — full fidelity) or an HTML export. We map page
titles → 30-voice knowledge notes (the canonical institutional-memory wiki) and
the space itself → an org. XML parsing is deliberately regex-scoped (page
objects' title properties) — entities.xml can be huge and its schema shifts;
titles are the durable signal. HTML exports are handled when present alongside.
"""
import re

from ..common import norm_file

NAME = "confluence"
SUBJECT = "company"
QUARANTINE = set()

_PAGE_BLOCK = re.compile(
    r'<object class="Page"[^>]*>(.*?)</object>', re.S)
_TITLE = re.compile(r'<property name="title">\s*<!\[CDATA\[(.*?)\]\]>\s*</property>'
                    r'|<property name="title">([^<]{1,200})</property>', re.S)
_SPACE_NAME = re.compile(r'<object class="Space"[^>]*>.*?<property name="name">'
                         r'(?:<!\[CDATA\[(.*?)\]\]>|([^<]{1,200}))', re.S)
_HTML_TITLE = re.compile(r"<title>([^<]{1,200})</title>", re.I)
# ConfluenceUserImpl objects map user keys → usernames; Page blocks reference the
# key in their creator/lastModifier properties.
_USER_BLOCK = re.compile(
    r'<object class="ConfluenceUserImpl"[^>]*>(.*?)</object>', re.S)
_USER_KEY = re.compile(r'<id name="key">([^<]{1,64})</id>')
_USER_NAME = re.compile(r'<property name="(?:name|lowerName)">'
                        r'(?:<!\[CDATA\[(.*?)\]\]>|([^<]{1,120}))', re.S)
_FULL_NAME = re.compile(r'<property name="fullName">'
                        r'(?:<!\[CDATA\[(.*?)\]\]>|([^<]{1,120}))', re.S)
_CREATOR = re.compile(r'<property name="creator"[^>]*>\s*<id name="key">([^<]{1,64})</id>')
_BODY = re.compile(r'<object class="BodyContent"[^>]*>.*?<property name="body">'
                   r'<!\[CDATA\[(.*?)\]\]>', re.S)
_TAGS = re.compile(r"<[^>]+>")
_EXCERPT_CHARS = 300


def detect(file_index):
    """True for a Confluence XML space export (entities.xml present)."""
    return any(p.name.lower() == "entities.xml"
               for ps in file_index.values() for p in ps)


def extract(root, file_index, all_paths, col):
    """Parse a Confluence space export into the Collector. Returns consumed keys."""
    consumed = set()
    col.subject = "company"
    n_pages = 0
    space = ""

    for ps in list(file_index.values()):
        for p in ps:
            if p.name.lower() != "entities.xml":
                continue
            consumed.add(norm_file(p.name))
            try:
                xml = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            sm = _SPACE_NAME.search(xml)
            if sm:
                space = (sm.group(1) or sm.group(2) or "").strip()
                if space:
                    col.add_org(NAME, space, "wiki-space", tags=["org/wiki"])
            # user key → display name map (authors are who-knows-what signal)
            users = {}
            for ub in _USER_BLOCK.finditer(xml):
                km = _USER_KEY.search(ub.group(1))
                nm = _FULL_NAME.search(ub.group(1)) or _USER_NAME.search(ub.group(1))
                if km and nm:
                    users[km.group(1)] = (nm.group(1) or nm.group(2) or "").strip()
            # bounded body excerpt (tags stripped; strip_pii runs in add_post)
            bm = {}
            for b in _BODY.finditer(xml):
                # BodyContent lacks a page back-ref in this shallow parse — keep
                # the first excerpt as a space-level sample only when 1 page
                bm.setdefault("first", _TAGS.sub(" ", b.group(1)))
            page_authors = {}
            blocks = list(_PAGE_BLOCK.finditer(xml))
            for block in blocks:
                tm = _TITLE.search(block.group(1))
                if not tm:
                    continue
                title = (tm.group(1) or tm.group(2) or "").strip()
                if not title:
                    continue
                excerpt = ""
                if len(blocks) == 1 and bm.get("first"):
                    excerpt = " ".join(bm["first"].split())[:_EXCERPT_CHARS]
                col.add_post(NAME, title + (f" — {excerpt}" if excerpt else ""),
                             "", "page", tags=["post/page"])
                n_pages += 1
                cm = _CREATOR.search(block.group(1))
                author = users.get(cm.group(1), "") if cm else ""
                if author:
                    col.add_person(NAME, author, role="wiki author",
                                   tags=["person/author"])
                    page_authors[author] = page_authors.get(author, 0) + 1
            if page_authors:
                top = ", ".join(f"{a}: {n}" for a, n in
                                sorted(page_authors.items(), key=lambda x: -x[1])[:8])
                col.note(f"[confluence] pages by author — {top}")

    # HTML export pages that shipped alongside (index/styles excluded)
    for ps in list(file_index.values()):
        for p in ps:
            if p.suffix.lower() not in (".html", ".htm"):
                continue
            if p.name.lower() in ("index.html", "toc.html"):
                consumed.add(norm_file(p.name))
                continue
            try:
                head = p.read_text(encoding="utf-8", errors="replace")[:2000]
            except Exception:
                continue
            if "confluence" not in head.lower():
                continue  # not a Confluence page — leave it to other adapters
            consumed.add(norm_file(p.name))
            tm = _HTML_TITLE.search(head)
            title = (tm.group(1) or "").split(" : ")[-1].strip() if tm else ""
            if title:
                col.add_post(NAME, title, "", "page", tags=["post/page"])
                n_pages += 1

    if n_pages:
        col.note(f"[confluence] space '{space or '?'}': {n_pages} pages → voice")
    return consumed
