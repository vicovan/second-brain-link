#!/usr/bin/env python3
"""
taste.py - derive what the engine refuses to: what kind of place each pin is, and how much
you love it. The engine hands over facts (names, lists, ratings, your review text); taste is
an interpretation, so it is made here, where the user can see it and correct it.

For every place record from places.py it adds:

    category   coffee | ramen | museum | viewpoint | ...   (references/category-lexicon.md)
    group      drink | food | culture | sight | nature | shop | work | event | transport | other
    price_band $ | $$ | $$$ | -      (the category's default, a hint only)
    love       0.0 .. 1.0            your rating, saved lists, visits and review words

and summarises it into a CANDIDATE `taste.md` - a proposal travel-onboarding shows the user
to confirm, never a file this script writes over a confirmed one.

    python3 taste.py                     # the candidate taste.md, on stdout
    python3 taste.py --json              # every place, with category/love
    python3 taste.py --out <file>        # write the candidate (refuses to overwrite)

Heuristics only. An ambiguous name stays `other`; the skill may ask the model about those,
but this script never calls a model and never touches the network.
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import reference  # noqa: E402
import places as _places  # noqa: E402

FAVOURITE_LIST = re.compile(r"\b(favou?rites?|loved?|best|top)\b", re.I)
WANT_LIST = re.compile(r"\b(want to go|to visit|wishlist|bucket|someday|next)\b", re.I)


def load_lexicon(path=None):
    """[(category, group, band, [words])] in file order, plus {'+': [...], '-': [...]}."""
    p = pathlib.Path(path) if path else reference("category-lexicon.md")
    cats, review = [], {"+": [], "-": []}
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return cats, review
    for line in text.split("\n"):
        m = re.match(r"^-\s*([a-z][a-z-]*)\s*\(([^,]+),\s*([^)]+)\)\s*:\s*(.+)$", line.strip())
        if m:
            words = [w.strip().lower() for w in m.group(4).split(",") if w.strip()]
            cats.append((m.group(1), m.group(2).strip(), m.group(3).strip(), words))
            continue
        m = re.match(r"^-\s*love([+-])\s*:\s*(.+)$", line.strip())
        if m:
            review[m.group(1)] = [w.strip().lower() for w in m.group(2).split(",") if w.strip()]
    return cats, review


def _hits(text, words):
    n = 0
    for w in words:
        if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", text):
            n += 1
    return n


def classify(rec, lexicon):
    cats, _ = lexicon
    hay = " ".join([rec.get("name") or ""] + list(rec.get("lists") or []) +
                   [t.split("/")[-1] for t in rec.get("tags") or [] if "/tag/" in t] +
                   [rec.get("review") or ""]).lower()
    best, best_n = None, 0
    for cat in cats:
        n = _hits(hay, cat[3])
        if n > best_n:
            best, best_n = cat, n
    if not best:
        return "other", "other", "-"
    return best[0], best[1], best[2]


def love_score(rec, lexicon):
    """0..1. A rating dominates when present; lists, visits and review words nudge it."""
    _, review = lexicon
    r = rec.get("rating")
    score = (float(r) - 1) / 4 if r is not None else 0.5
    lists = " ".join(rec.get("lists") or [])
    if FAVOURITE_LIST.search(lists):
        score += 0.2
    elif WANT_LIST.search(lists):
        score += 0.1           # intent, not proof of love
    if rec.get("visited") and rec.get("saved"):
        score += 0.05
    m = re.search(r"(\d+) visit", rec.get("review") or "")
    if m and int(m.group(1)) >= 3:
        score += 0.1
    text = (rec.get("review") or "").lower()
    score += 0.05 * _hits(text, review["+"]) - 0.1 * _hits(text, review["-"])
    return round(max(0.0, min(1.0, score)), 2)


def enrich(recs, lexicon=None):
    lex = lexicon or load_lexicon()
    for r in recs:
        r["category"], r["group"], r["price_band"] = classify(r, lex)
        r["love"] = love_score(r, lex)
    return recs


def _link(rec):
    return f"[[{rec['title']}]]"


def candidate_md(recs, owner=""):
    """The proposal. Every line cites the notes it came from, so the user can check it."""
    today = datetime.date.today().isoformat()
    by_cat = {}
    for r in recs:
        by_cat.setdefault(r["category"], []).append(r)
    loved = sorted((r for r in recs if r["love"] >= 0.75 and r.get("rating") is not None),
                   key=lambda r: (-r["love"], r["name"]))
    disliked = sorted((r for r in recs if r.get("rating") is not None and r["rating"] <= 2),
                      key=lambda r: r["name"])
    ranked = sorted(((c, rs) for c, rs in by_cat.items() if c != "other"),
                    key=lambda cr: (-sum(x["love"] for x in cr[1]) / len(cr[1]) * min(len(cr[1]), 5), cr[0]))
    lines = ["---", "type: travel-profile", "title: Taste",
             "tags: [travel, profile]", f"owner: {owner}", f"updated: {today}",
             "status: candidate", "---", "",
             "# Taste", "",
             "> **Candidate — proposed by `taste.py` from your own places, not yet confirmed.** "
             "Every line cites the notes it came from. Correct anything wrong; delete what does "
             "not fit. Once you confirm, `status: candidate` becomes `status: confirmed`.", ""]
    lines += ["## What you love", ""]
    if loved:
        for r in loved[:12]:
            why = f"★{r['rating']:g}" + (f" — “{r['review'][:90]}”" if r.get("review") else "")
            lines.append(f"- **{r['category']}** — {_link(r)} ({r.get('city') or '?'}) {why}")
    else:
        lines.append("- _No ratings in the brain yet — nothing to go on but saved lists._")
    lines += ["", "## The kinds of places you keep", ""]
    for c, rs in ranked[:10]:
        avg = sum(x["love"] for x in rs) / len(rs)
        ex = ", ".join(_link(x) for x in sorted(rs, key=lambda x: -x["love"])[:3])
        lines.append(f"- **{c}** — {len(rs)} place(s), love {avg:.2f} · e.g. {ex}")
    lines += ["", "## Not for you", ""]
    if disliked:
        for r in disliked:
            lines.append(f"- **{r['category']}** — {_link(r)} ★{r['rating']:g}"
                         + (f" — “{r['review'][:90]}”" if r.get("review") else ""))
    else:
        lines.append("- _Nothing rated low._")
    lines += ["", "## Pace, stays and budget", "",
              "- Pace: _ask — not derivable from places_",
              "- Hotel style: _ask_", "- Neighbourhood: _ask_",
              "- Price comfort: " + (", ".join(sorted({r['price_band'] for r in loved if r['price_band'] != '-'}))
                                     or "_ask_") + " (from the places you loved; a hint)",
              "", f"_Derived from {len(recs)} places._", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--brain")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--owner", default="")
    a = ap.parse_args()
    recs = enrich(_places.load(a.brain))
    if a.json:
        print(json.dumps(recs, ensure_ascii=False, indent=1))
        return 0
    md = candidate_md(recs, a.owner)
    if a.out:
        out = pathlib.Path(a.out)
        if out.exists():
            print(f"refusing to overwrite {out} - show the user the candidate instead", file=sys.stderr)
            return 2
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(out)
        return 0
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
