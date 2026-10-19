#!/usr/bin/env python3
"""
lint_claims.py - every message is checked against the seller's own facts before it can leave.

    python3 lint_claims.py DRAFT [--channel email|linkedin_invite|linkedin_dm|x_dm|whatsapp|form]
                           [--json]

DRAFT is the message body as text or Markdown (a frontmatter block is ignored).

RED (exit 1) - the send guard blocks the message at every autonomy level:
  - a [CONFIRM ...] marker or an unfilled {{placeholder}} left in
  - a term from offer.md's "## Do not claim" list
  - a number that appears nowhere in the profile or its materials (years, dates, small bare
    numbers <= 12 and numbers inside URLs are ignored - but "3 customers" or "five pilots" is a
    claim, and is checked)
  - an email without the opt-out line (sending.md `opt_out`)
  - over the channel's limit (a LinkedIn connection note is 300 characters)
AMBER (reported, does not stop):
  - an email over 160 words (long first emails go unread)
  - no question in a first touch (nothing to answer)

The number logic is ported from the fundraising plugin's linter.
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sales_profile as prof  # noqa: E402

NUM = re.compile(r"(?<![\w.])([$€£]?\d[\d,]*(?:\.\d+)?)\s*(%|k|m|mm|bn|b|x|\+)?(?![\w])", re.I)
URL = re.compile(r"https?://\S+|\b[\w.-]+\.(?:com|vc|io|ai|co|org|net|app|dev)\S*", re.I)
DATE = re.compile(r"\b(19|20)\d\d(-\d\d(-\d\d)?)?\b")
TIME = re.compile(r"\b\d{1,2}[:.]\d\d\b|\b\d{1,2}\s?(am|pm)\b", re.I)
REF = re.compile(r"\b(art(icle)?\.?|§|section|no\.|version|v|step|day)\s?\d+(\.\d+)*\b|#\d+", re.I)
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30}
CLAIM_NOUN = (r"(?:[a-z-]+\s+){0,2}(companies|company|customers|clients|users|teams|pilots|"
              r"deployments|integrations|countries|years|employees|engineers|partners|brains|"
              r"sources|hours|days|weeks|percent)\b")
SMALL = re.compile(r"\b(\d{1,2}|" + "|".join(WORDS) + r")\+?\s+" + CLAIM_NOUN, re.I)
LIMITS = {"linkedin_invite": 300, "linkedin_dm": 1900, "x_dm": 1000, "whatsapp": 1500, "form": 3000}


def _num(tok, unit=""):
    try:
        v = float(tok.replace(",", "").lstrip("$€£"))
    except ValueError:
        return None
    return round(v * {"k": 1e3, "m": 1e6, "mm": 1e6, "b": 1e9, "bn": 1e9}.get((unit or "").lower(), 1), 4)


def numbers_in(text):
    text = TIME.sub(" ", REF.sub(" ", DATE.sub(" ", URL.sub(" ", text))))
    out = []
    for m in NUM.finditer(text):
        v = _num(m.group(1), m.group(2))
        if v is None or (v <= 12 and not m.group(2) and not m.group(1).startswith(("$", "€", "£"))):
            continue
        out.append((m.group(0).strip(), v))
    for m in SMALL.finditer(URL.sub(" ", text)):
        t = m.group(1).lower()
        v = WORDS.get(t)
        if v is None:
            try:
                v = float(t)
            except ValueError:
                continue
        out.append((m.group(0).strip(), float(v)))
    return out


def known(corpus):
    vals = {v for _, v in numbers_in(corpus)}
    for w, n in WORDS.items():
        if re.search(r"\b" + w + r"\b", corpus, re.I):
            vals.add(float(n))
    for m in re.finditer(r"\b\d[\d,]*(?:\.\d+)?\b", corpus):
        v = _num(m.group(0))
        if v is not None:
            vals.add(v)
    return vals


def body_of(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            return text[end + 4:]
    return text


def lint(text, channel="email", pdir=None, first_touch=False):
    body = body_of(text)
    red, amber = [], []
    if re.search(r"\[CONFIRM[^\]]*\]", body, re.I):
        red.append("a [CONFIRM] marker is still in the message")
    if re.search(r"\{\{[^}]+\}\}|<[A-Z][A-Z _-]{2,}>", body):
        red.append("an unfilled placeholder is still in the message")
    low = body.lower()
    for term in prof.section("offer", "Do not claim", pdir):
        t = term.strip().strip("`\"'").lower()
        if len(t) >= 3 and t in low:
            red.append(f"do-not-claim term «{term}»")
    ok = known(prof.corpus(pdir))
    for tok, v in numbers_in(body):
        if v not in ok:
            red.append(f"«{tok}» is not in your profile or materials — a claim needs a source")
    if channel == "email":
        opt = prof.sending(pdir).get("opt_out", "")
        if opt and opt.lower()[:24] not in low:
            red.append("the opt-out line is missing")
        words = len(re.findall(r"\w+", body))
        if words > 160:
            amber.append(f"{words} words — a first email over 160 words often goes unread")
    lim = LIMITS.get(channel)
    if lim and len(body.strip()) > lim:
        red.append(f"{len(body.strip())} characters — over the {channel} limit of {lim}")
    if first_touch and "?" not in body:
        amber.append("no question — give them one thing to answer")
    return {"red": sorted(set(red)), "amber": amber, "ok": not red}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("draft")
    ap.add_argument("--channel", default="email")
    ap.add_argument("--first-touch", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        text = open(a.draft, encoding="utf-8").read()
    except OSError as e:
        print(f"cannot read {a.draft}: {e}", file=sys.stderr)
        return 2
    r = lint(text, a.channel, first_touch=a.first_touch)
    if a.json:
        print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        for x in r["red"]:
            print(f"RED    {x}")
        for x in r["amber"]:
            print(f"AMBER  {x}")
        print("PASS" if r["ok"] else "STOP — fix the red lines; never invent the missing fact")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
