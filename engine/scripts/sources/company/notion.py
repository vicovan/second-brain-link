#!/usr/bin/env python3
"""
notion.py — Notion workspace-export adapter (company subject).

A Notion "Export all workspace content" (Markdown + CSV) names every page
`<Title> <32-hex-page-id>.md` and every database `<Title> <32-hex-id>.csv` /
`…_all.csv`. Pages → 30-voice knowledge notes (title + a bounded, PII-stripped
excerpt — the institutional wiki is the company's written voice); database rows
with a Name/Title column → interests (light). Markdown is near-perfect input:
we are Markdown-first ourselves.
"""
import re

from ..common import read_csv, norm_file

NAME = "notion"
SUBJECT = "company"
QUARANTINE = set()

_HEXID = re.compile(r"\s+[0-9a-f]{32}(?:_all)?$", re.I)
_EXCERPT_CHARS = 400


def _pages(file_index, suffix):
    """Every export file of `suffix` whose stem carries the Notion 32-hex id."""
    out = []
    for ps in file_index.values():
        for p in ps:
            if p.suffix.lower() == suffix and _HEXID.search(p.stem):
                out.append(p)
    return out


def detect(file_index):
    """True if Notion-style `<Title> <32-hex>.md` pages are present."""
    return bool(_pages(file_index, ".md"))


def extract(root, file_index, all_paths, col):
    """Parse a Notion export into the Collector. Returns consumed keys."""
    consumed = set()
    col.subject = "company"

    # pages → voice (title + bounded excerpt; strip_pii runs inside add_post).
    # The export nests subpages in folders named after their parent page — that
    # path is the breadcrumb (real context: "Projects / Roadmap" ≠ "HR / Roadmap").
    # Intra-export links ([X](X%20<hex>.md)) become plain "→ X" references —
    # NOT [[wikilinks]]: pages render as voice notes (post-N.md), so a wikilink
    # to the page TITLE would dangle and break the no-dangling-links invariant.
    _MDLINK = re.compile(r"\[([^\]]+)\]\((?:[^)]*%20)?[0-9a-f]{32}(?:\.md|\.csv)?\)", re.I)
    n_pages = 0
    for p in sorted(_pages(file_index, ".md")):
        consumed.add(norm_file(p.name))
        title = _HEXID.sub("", p.stem).strip()
        crumbs = [_HEXID.sub("", part).strip() for part in p.parent.parts
                  if _HEXID.search(part)]
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            body = ""
        # skip the duplicated H1 Notion puts on line 1, keep a short excerpt
        lines = [ln for ln in body.splitlines() if ln.strip()]
        if lines and lines[0].lstrip("# ").strip().lower() == title.lower():
            lines = lines[1:]
        excerpt = _MDLINK.sub(r"→ \1", " ".join(lines))[:_EXCERPT_CHARS]
        crumb_txt = (" / ".join(crumbs) + " / ") if crumbs else ""
        tags = ["post/page"]
        if crumbs:
            tags.append("page/" + re.sub(r"[^a-z0-9]+", "-", crumbs[0].lower()).strip("-"))
        col.add_post(NAME, f"{crumb_txt}{title}" + (f" — {excerpt}" if excerpt else ""),
                     "", "page", tags=tags)
        n_pages += 1

    # databases (CSV) → light interests from the Name/Title column
    n_rows = 0
    for p in sorted(_pages(file_index, ".csv")):
        consumed.add(norm_file(p.name))
        db = _HEXID.sub("", p.stem).strip()
        for r in read_csv(p):
            nm = (r.get("Name") or r.get("Title") or "").strip()
            if nm:
                col.add_interest(NAME, f"{db}: {nm}" if db else nm)
                n_rows += 1

    if n_pages:
        col.note(f"[notion] {n_pages} pages → voice, {n_rows} database rows → interests")
    return consumed
