#!/usr/bin/env python3
"""
lint_claims.py - the facts file is a gate, not a reference.

Runs on EVERY application answer set and EVERY email draft before it reaches a form or
a Gmail draft. Red stops that one application or email at every autonomy level.

    python3 lint_claims.py DRAFT [DRAFT ...] [--out gates.json] [--profile DIR]

DRAFT is Markdown (an email note or answers.md) or answers.json:
    {"fields": [{"label": "...", "answer": "...", "required": true,
                 "limit": {"n": 500, "unit": "chars|words|unknown"}}]}

RED (exit 1):
  - a [CONFIRM ...] marker left in
  - a term from company.md's "## Do not claim" list
  - a number that appears nowhere in the founder's own profile files
    (years, dates, bare small numbers ≤ 12 and numbers inside URLs are ignored — but a small
    count before a checkable noun, "five startups" or "3 exits", is a claim and is checked)
  - an answer over its limit, or a required field left empty
  - an email whose `hook_stamp:` is 📋 or ⚠ (the personal hook rests on an unverified claim)
AMBER (reported, does not stop):
  - a limit whose unit was never tested ("unknown") — type one character and watch the counter
  - an email with no `to:` address yet
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import founder_profile as prof  # noqa: E402

NUM = re.compile(r"(?<![\w.])([$€£]?\d[\d,]*(?:\.\d+)?)\s*(%|k|m|mm|bn|b|x|\+)?(?![\w])", re.I)
URL = re.compile(r"https?://\S+|\b[\w.-]+\.(?:com|vc|io|ai|co|org|net)\S*", re.I)
DATE = re.compile(r"\b(19|20)\d\d(-\d\d(-\d\d)?)?\b")
# references, not claims: "GDPR Art. 20", "§ 4", "Batch 37", "Series A", "v1.2"
REF = re.compile(r"\b(art(icle)?\.?|§|section|chapter|no\.|batch|cohort|class|round|version|v)\s?\d+(\.\d+)*\b|#\d+", re.I)


def norm_num(tok, unit=""):
    t = tok.replace(",", "").lstrip("$€£")
    try:
        v = float(t)
    except ValueError:
        return None
    u = (unit or "").lower()
    v *= {"k": 1e3, "m": 1e6, "mm": 1e6, "b": 1e9, "bn": 1e9}.get(u, 1)
    return round(v, 4)


def numbers_in(text):
    text = URL.sub(" ", text)
    text = DATE.sub(" ", text)
    text = REF.sub(" ", text)
    out = []
    for m in NUM.finditer(text):
        v = norm_num(m.group(1), m.group(2))
        if v is None:
            continue
        if v <= 12 and not m.group(2) and not m.group(1).startswith(("$", "€", "£")):
            continue
        out.append((m.group(0).strip(), v))
    return out


WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30}
# A small count is still a claim when it counts something a reader would check.
CLAIM_NOUN = (r"(?:[a-z-]+\s+){0,2}(companies|company|startups?|ventures|exits?|years|customers|"
              r"clients|users|founders|employees|engineers|developers|countries|partners|pilots|"
              r"patents|awards|apps|products|teams)\b")
SMALL = re.compile(r"\b(\d{1,2}|" + "|".join(WORDS) + r")\+?\s+" + CLAIM_NOUN, re.I)


def small_claims(text):
    """Small counts before a checkable noun — "five startups", "3 exits" — digits or words."""
    out = []
    for m in SMALL.finditer(URL.sub(" ", text)):
        tok = m.group(1).lower()
        v = WORDS.get(tok, None)
        if v is None:
            try:
                v = int(tok)
            except ValueError:
                continue
        out.append((m.group(0).strip(), float(v)))
    return out


def known_numbers(corpus):
    vals = set()
    for _, v in numbers_in(corpus):
        vals.add(v)
    for _, v in small_claims(corpus):
        vals.add(v)
    for w, n in WORDS.items():
        if re.search(r"\b" + w + r"\b", corpus, re.I):
            vals.add(float(n))
    for m in re.finditer(r"(?<![\w.])(\d{1,2})(?![\w.])", corpus):
        vals.add(float(m.group(1)))
    # a "25" in the facts also licenses "25+" and a "609" licenses "609 tests"
    return vals


def load_draft(path):
    p = pathlib.Path(path)
    txt = p.read_text(encoding="utf-8")
    if p.suffix == ".json":
        data = json.loads(txt)
        fields = data.get("fields") if isinstance(data, dict) else data
        return "json", fields or [], data if isinstance(data, dict) else {}
    fm = prof.frontmatter(txt)
    body = txt.split("\n---", 2)[-1] if txt.startswith("---") else txt
    return "md", [{"label": p.name, "answer": body}], fm


def count(text, unit):
    return len(text.split()) if unit == "words" else len(text)


def lint(paths, pdir=None):
    corpus = prof.facts_corpus(pdir)
    have = known_numbers(corpus)
    banned = prof.do_not_claim(pdir)
    red, amber = [], []
    if not corpus.strip():
        red.append("no profile found — run raise-onboarding before drafting anything")
    for path in paths:
        kind, fields, meta = load_draft(path)
        name = pathlib.Path(path).name
        if kind == "md":
            hs = str(meta.get("hook_stamp", "")).strip()
            if hs in ("📋", "⚠"):
                red.append(f"{name}: the personal hook rests on an unverified claim ({hs}) — verify it or drop it")
            if meta.get("type") == "fundraising-email" and not meta.get("to"):
                amber.append(f"{name}: no `to:` address yet")
        for f in fields:
            label = f.get("label") or f.get("question") or "field"
            ans = str(f.get("answer") or "")
            where = f"{name} · {label[:60]}"
            if f.get("required") and not ans.strip():
                red.append(f"{where}: required field is empty")
            if re.search(r"\[\s*CONFIRM", ans, re.I):
                red.append(f"{where}: a [CONFIRM] marker is still in the text")
            low = ans.lower()
            for t in banned:
                # "pre-revenue" / "non-users" are honest negations, not claims: a hyphenated
                # prefix never matches a do-not-claim term
                if re.search(r"(?<![\w-])" + re.escape(t) + r"(?![\w-])", low):
                    red.append(f"{where}: do-not-claim term «{t}»")
            for tok, v in small_claims(ans):
                if v not in have:
                    red.append(f"{where}: «{tok}» — a count the profile does not state")
            for tok, v in numbers_in(ans):
                if v not in have:
                    red.append(f"{where}: «{tok}» is not in the profile — every number must trace to it")
            lim = f.get("limit") or {}
            if lim.get("n"):
                unit = (lim.get("unit") or "unknown").lower()
                if unit == "unknown":
                    amber.append(f"{where}: limit {lim['n']} with an untested unit — test the counter before pasting")
                    n = count(ans, "chars")
                    if n > lim["n"] and len(ans.split()) > lim["n"]:
                        red.append(f"{where}: over {lim['n']} in both characters and words")
                elif count(ans, unit) > lim["n"]:
                    red.append(f"{where}: {count(ans, unit)} {unit} > limit {lim['n']}")
    return {"ok": not red, "red": red, "amber": amber, "checked": [str(p) for p in paths]}


REVIEW_VERDICTS = ("take-meeting", "maybe", "pass")


def _gates(pkg):
    p = pathlib.Path(pkg)
    return p / "gates.json" if p.is_dir() else p


def _read(gp):
    try:
        return json.loads(gp.read_text(encoding="utf-8")) if gp.is_file() else {}
    except (OSError, ValueError):
        return {}


def _recompute(g):
    lint_ok = (g.get("lint") or {}).get("ok", False)
    rev = g.get("review") or {}
    dom = g.get("dom") or {}
    g["ok"] = bool(lint_ok and rev.get("pass") and dom.get("ok", True))
    return g


def gates_ok(pkg):
    """(ok, why) — lint green AND an investor review that passed (take-meeting, or maybe
    after one round of fixes) AND, for a form, the DOM check."""
    g = _read(_gates(pkg))
    if not g:
        return False, "no gates.json — run the lint and the investor review"
    if "lint" not in g:
        return False, "lint not run"
    if not g["lint"].get("ok"):
        return False, "lint red: " + "; ".join(g["lint"].get("red", [])[:2])
    rev = g.get("review")
    if not rev:
        return False, "investor review not run"
    if not rev.get("pass"):
        return False, f"review '{rev.get('verdict')}': {rev.get('reason', '')}"
    if "dom" in g and not g["dom"].get("ok", True):
        return False, "form fields did not verify"
    return True, "PASS" + (" (flagged: maybe)" if rev.get("flag") else "")


def review_main(argv):
    ap = argparse.ArgumentParser(prog="lint_claims.py review")
    ap.add_argument("pkg")
    ap.add_argument("--verdict", required=True, choices=REVIEW_VERDICTS)
    ap.add_argument("--reason", default="")
    ap.add_argument("--round", type=int, default=1,
                    help="2 = the second review after applying top_fixes once")
    a = ap.parse_args(argv)
    gp = _gates(a.pkg)
    g = _read(gp)
    # maybe on the second round is allowed through, flagged; pass never is
    ok = a.verdict == "take-meeting" or (a.verdict == "maybe" and a.round >= 2)
    g["review"] = {"pass": ok, "verdict": a.verdict, "reason": a.reason, "round": a.round,
                   "flag": "maybe" if (a.verdict == "maybe" and ok) else None,
                   "at": datetime.datetime.now().replace(microsecond=0).isoformat()}
    _recompute(g)
    gp.parent.mkdir(parents=True, exist_ok=True)
    gp.write_text(json.dumps(g, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"review '{a.verdict}' (round {a.round}) recorded in {gp} — gates {'PASS' if g['ok'] else 'FAIL'}")
    return 0


def status_main(argv):
    ap = argparse.ArgumentParser(prog="lint_claims.py status")
    ap.add_argument("pkg")
    a = ap.parse_args(argv)
    ok, why = gates_ok(a.pkg)
    print("GATES:", "PASS" if ok else "FAIL — " + why)
    return 0 if ok else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("review", "status"):
        fn = review_main if sys.argv[1] == "review" else status_main
        sys.exit(fn(sys.argv[2:]))
    ap = argparse.ArgumentParser()
    ap.add_argument("drafts", nargs="+")
    ap.add_argument("--out", help="write gates.json here (default: beside the first draft)")
    ap.add_argument("--profile", help="profile dir (default: resolved by paths.py)")
    a = ap.parse_args()
    res = lint(a.drafts, a.profile)
    out = pathlib.Path(a.out) if a.out else pathlib.Path(a.drafts[0]).parent / "gates.json"
    try:
        prev = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    except (OSError, ValueError):
        prev = {}
    prev["lint"] = res
    _recompute(prev) if "review" in prev else prev.update({"ok": res["ok"] and prev.get("dom", {}).get("ok", True)})
    prev["red"] = res["red"] + prev.get("dom", {}).get("red", [])
    out.write_text(json.dumps(prev, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
