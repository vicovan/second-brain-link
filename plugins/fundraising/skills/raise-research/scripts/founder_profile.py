#!/usr/bin/env python3
"""
founder_profile.py - read the founder's profile. Never writes it (raise-onboarding owns it).

The profile is six Markdown files under <render dir>/profile/. Two of them carry
machine-readable settings in YAML-style frontmatter, parsed here with the stdlib only
(flat keys; lists as [a, b, c]; numbers as numbers):

    round.md    the round and the ordered filter chain
    answers.md  the autonomy level and the per-run submit cap

company.md's "## Do not claim" section is the do-not-claim list lint_claims.py enforces.

    python3 founder_profile.py            # print what was parsed, and what is missing
"""
import os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import profile_dir  # noqa: E402

FILES = ("company.md", "founder.md", "round.md", "answers.md", "stories.md")
FILTERS = ("floor", "geo", "thesis", "access", "entity", "exclusions")

ROUND_DEFAULTS = {
    "min_net_cash": 0,
    "currency": "USD",
    "geography_ok": [],
    "relocation": "no",
    "entities_ok": [],
    "entity_now": "none",
    "cofounder": "closed",
    "exclusions": [],
    "thesis_keywords": [],
    "filter_order": list(FILTERS),
    "max_research_agents": 3,
}


def _scalar(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []
    v = v.strip("'\"")
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    return v


def frontmatter(text):
    """Flat YAML-ish frontmatter → dict. Unknown shapes are kept as strings."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out = {}
    for line in text[3:end].split("\n"):
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            out[m.group(1).replace("-", "_")] = _scalar(m.group(2))
    return out


def read(name, pdir=None):
    p = pathlib.Path(pdir or profile_dir()) / name
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def round_settings(pdir=None):
    s = dict(ROUND_DEFAULTS)
    txt = read("round.md", pdir)
    if txt:
        s.update(frontmatter(txt))
    order = [f for f in s.get("filter_order") or [] if f in FILTERS]
    s["filter_order"] = order + [f for f in FILTERS if f not in order]
    for k in ("geography_ok", "entities_ok", "exclusions", "thesis_keywords"):
        if isinstance(s.get(k), str):
            s[k] = [s[k]] if s[k] else []
    return s


def level(pdir=None):
    """Autonomy level from answers.md. Missing or unreadable → supervised, always."""
    txt = read("answers.md", pdir) or ""
    fm = frontmatter(txt)
    lv = str(fm.get("level", "")).strip().lower()
    if not lv:
        m = re.search(r"^\s*level:\s*([a-z]+)", txt, re.M)
        lv = m.group(1).lower() if m else ""
    return lv if lv in ("supervised", "autonomous") else "supervised"


def max_submits(pdir=None):
    fm = frontmatter(read("answers.md", pdir) or "")
    try:
        return max(0, int(fm.get("max_submits_per_run", 5)))
    except (TypeError, ValueError):
        return 5


def do_not_claim(pdir=None):
    """Terms under '## Do not claim' in company.md. One bullet per term; the term is the
    text before an em dash / colon, lower-cased. Backticks and quotes are stripped."""
    txt = read("company.md", pdir) or ""
    m = re.search(r"^##\s+Do not claim\s*$(.*?)(?=^##\s|\Z)", txt, re.M | re.S | re.I)
    if not m:
        return []
    terms = []
    for line in m.group(1).split("\n"):
        b = re.match(r"^\s*[-*]\s+(.+)$", line)
        if not b:
            continue
        t = re.split(r"\s+—\s+|\s+-\s+|:\s", b.group(1), maxsplit=1)[0]
        t = t.strip().strip("`*\"'").lower()
        if t:
            terms.append(t)
    return terms


def facts_corpus(pdir=None):
    """Everything the founder has stated as fact — the only source numbers may come from."""
    return "\n".join(read(f, pdir) or "" for f in FILES)


def missing(pdir=None):
    return [f for f in FILES if read(f, pdir) is None]


def main():
    pdir = profile_dir()
    print(f"profile dir : {pdir}")
    print(f"missing     : {', '.join(missing(pdir)) or 'none'}")
    print(f"level       : {level(pdir)}  (max submits per run: {max_submits(pdir)})")
    rs = round_settings(pdir)
    for k in sorted(rs):
        print(f"round.{k:<20} {rs[k]}")
    print(f"do-not-claim: {do_not_claim(pdir)}")


if __name__ == "__main__":
    main()
