#!/usr/bin/env python3
"""
mailto.py - build a pre-filled `mailto:` link (RFC 6068). Opening it only starts a NEW
message in the founder's own mail app; nothing is ever sent by this plugin.

    python3 mailto.py --to a@b.c --subject "Hello" --body-file email-body.txt
    python3 mailto.py --to a@b.c --subject "Hello" --body "short text"

Prints JSON: {"url": "mailto:…", "fallback": false, "length": N}

Some mail apps truncate very long URLs, so a link longer than LIMIT drops the body and
keeps the recipient and subject (`fallback: true`); the note that carries the button
always holds the full body to copy.
"""
import argparse, json, sys
from urllib.parse import quote

LIMIT = 1800


def _enc(s):
    # CRLF line breaks per RFC 6068; everything outside unreserved is percent-encoded —
    # including "|", so a link can sit inside a Markdown table cell
    return quote((s or "").replace("\r\n", "\n").replace("\n", "\r\n"), safe="")


def build(to="", subject="", body="", cc="", limit=LIMIT):
    """(url, fallback). `to`/`cc` may be comma-separated."""
    def url_with(b):
        q = []
        if cc:
            q.append("cc=" + _enc(cc))
        if subject:
            q.append("subject=" + _enc(subject))
        if b:
            q.append("body=" + _enc(b))
        addr = ",".join(quote(a.strip(), safe="@.+-_") for a in (to or "").split(",") if a.strip())
        return "mailto:" + addr + ("?" + "&".join(q) if q else "")
    url = url_with(body)
    if len(url) <= limit:
        return url, False
    return url_with(""), True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default="")
    ap.add_argument("--cc", default="")
    ap.add_argument("--subject", default="")
    ap.add_argument("--body", default="")
    ap.add_argument("--body-file")
    ap.add_argument("--limit", type=int, default=LIMIT)
    a = ap.parse_args()
    body = a.body
    if a.body_file:
        body = open(a.body_file, encoding="utf-8").read()
    url, fb = build(a.to, a.subject, body, a.cc, a.limit)
    print(json.dumps({"url": url, "fallback": fb, "length": len(url)}))


if __name__ == "__main__":
    main()
