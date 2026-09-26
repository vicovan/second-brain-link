#!/usr/bin/env python3
"""
lint_cv.py — the gates a CV and its form answers must pass before anything is submitted.

Every rule here already existed as prose in the playbook, and the prose was ignored: CVs went
out with roles out of date order, a "Why <Company>" section, a summary that named the
candidate's own gap, and no answers recorded. A rule a model can skip is a suggestion. These
are checks that FAIL, and `learn.py log-outcome --status applied` refuses to log a submission
unless `gates.json` says they passed.

Zero network, zero tokens, stdlib only.

Usage:
    lint_cv.py cv <cv.md> [--profile profile.md] [--keywords "a;b;c"] [--fit fit.md]
    lint_cv.py answers <answers.json> [--profile profile.md]
    lint_cv.py review <app dir> --verdict shortlist|maybe|reject [--reason "..."]
    lint_cv.py status <app dir>

Every mode writes its result into `<app dir>/gates.json` (the folder the file lives in) under
its own key — `cv`, `answers`, `review` — so the ledger can check all three at submit time.
Exit code 1 on any FAIL.
"""
import argparse, datetime, json, os, pathlib, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv_md  # noqa: E402

# --------------------------------------------------------------------------------------
# Vocabulary. Kept here, not in the playbook, so the playbook and the gate cannot drift:
# the playbook points at this file.
# --------------------------------------------------------------------------------------

# Phrases that mark text as generated, or as filler, on a CV or in a form answer.
BANNED = [
    "proven track record", "track record of success", "results-driven", "results driven",
    "passionate about", "leverag", "spearhead", "seamless", "cutting-edge", "cutting edge",
    "robust and scalable", "best-in-class", "best in class", "deep dive", "synergy",
    "synergies", "at the intersection of", "fast-paced", "a journey", "unlock value",
    "unlocking", "drive impact", "driving impact", "holistic", "world-class", "world class",
    "dynamic environment", "thought leader", "go-getter", "self-starter", "detail-oriented",
    "team player", "hit the ground running", "game-changer", "game changer", "paradigm",
    "revolutioniz", "revolutionis", "transformative", "empower", "elevate", "delve",
    "tapestry", "testament to", "navigate the complexities", "ever-evolving", "ever evolving",
    "in today's", "landscape of", "realm of", "harness the power", "i am writing to",
    "i am excited", "i'm excited", "thrilled to", "perfect fit", "ideal candidate",
    "dream job", "look no further", "wealth of experience", "extensive experience",
    "responsible for", "helped to", "various", "stakeholder alignment",
]
# A banned stem inside a proper noun the user's OWN profile names — an employer, a product,
# a title ("Empower…", "Elevate…") — is a fact, not a cliché. Exemptions therefore come from
# the profile at run time, never from a list in this file: a hardcoded name here would be
# one real person's employer shipped to everyone.
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9&'.-]*")

# "It's not X, it's Y" and its cousins — the most recognisable machine cadence.
NEG_PARALLEL = [
    r"\bnot just\b[^.;:]{1,80}\bbut\b",
    r"\bnot only\b[^.;:]{1,80}\bbut\b",
    r"\bisn['’]t (?:just |only |about )?[^.;:]{1,60}[.;,—–-]\s*(?:it|this|that)['’]s\b",
    r"\bit['’]s not (?:about )?[^.;:]{1,60}[,;—–-]\s*it['’]s\b",
    r"\bnot [a-z]+ to [^.;:]{1,40}, (?:they are|it is|these are) [^.]{1,40}\b",
    r"\b(?:are|is) not adjacent to\b",
]

# A candidate volunteering the reason to reject them. Gaps belong in fit.md and interview
# prep; on a CV or in a free-text answer they are read by a screener as the answer.
SELF_DISQUALIFY = [
    r"\bI have not\b", r"\bI haven['’]t\b", r"\bI have never\b", r"\bI['’]ve never\b",
    r"\bI do not have\b", r"\bI don['’]t have\b", r"\bI lack\b", r"\bnot my depth\b",
    r"\bnot my (?:strongest|core|primary) \b", r"\bhas not worked\b", r"\bhave not worked\b",
    r"\bno direct experience\b", r"\blimited experience\b", r"\bwhile I (?:have not|haven['’]t)\b",
    r"\bnot as (?:CIO|CEO|CTO|VP)\b", r"\bnot (?:at|inside) a\b[^.]{0,40}\bscale\b",
    r"\bI am not\b", r"\bI['’]m not\b", r"\bbelow (?:your|the) (?:bar|requirement)\b",
    r"\balthough I\b", r"\bdespite (?:not|my lack)\b",
]

# Placeholders and internal instructions that must never reach an employer.
PLACEHOLDER = [
    r"\bDEFLECT\b", r"\bTBD\b", r"\bTODO\b", r"\[ADD", r"\bSTOP and ask\b", r"<[a-z][a-z _-]*>",
    r"\bXX+\b", r"\blorem\b",
]

FIRST_PERSON = r"\b(I|I['’]m|I['’]ve|I['’]d|I['’]ll|my|me|mine|myself)\b"

EM_DASH_MAX = 4          # two per page on a two-page CV
BOLD_LEAD_MAX = 0.5      # share of bullets per role that may open with a bold lead-in


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _gates_path(p):
    p = pathlib.Path(p)
    return (p if p.is_dir() else p.parent) / "gates.json"


def _write_gate(path, key, payload):
    g = {}
    if path.exists():
        try:
            g = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            g = {}
    g[key] = payload
    path.write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _banned_hits(text, profile_text=""):
    low = text.lower()
    known = {w.lower() for w in _WORD.findall(profile_text or "")}
    for w in set(_WORD.findall(text)):
        wl = w.lower()
        if wl in known and any(b in wl for b in BANNED):
            low = re.sub(r"(?<![a-z0-9])" + re.escape(wl) + r"(?![a-z0-9])", " ", low)
    return sorted({b for b in BANNED if b in low})


def _regex_hits(text, patterns, flags=re.I):
    out = []
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            out.append(m.group(0))
    return out


# --------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------

_MONTH = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def _one_date(s, end=False):
    s = s.strip().lower()
    if not s:
        return None
    if s.startswith(("present", "current", "now", "today")):
        return (9999, 12)
    m = re.search(r"(\d{1,2})/(\d{4})", s)
    if m:
        return (int(m.group(2)), int(m.group(1)))
    m = re.search(r"([a-z]{3})[a-z]*\.?\s+(\d{4})", s)
    if m and m.group(1) in _MONTH:
        return (int(m.group(2)), _MONTH[m.group(1)])
    m = re.search(r"(\d{4})", s)
    if m:
        return (int(m.group(1)), 12 if end else 1)
    return None


def parse_range(dates):
    """'07/2021 – 04/2022' → ((2021,7),(2022,4)). Either end may be None."""
    if not dates:
        return (None, None)
    parts = re.split(r"\s*[–—-]\s*|\s+to\s+", dates.strip(), maxsplit=1)
    start = _one_date(parts[0])
    end = _one_date(parts[1], end=True) if len(parts) > 1 else start
    return (start, end)


# --------------------------------------------------------------------------------------
# Profile facts (for the fact gate)
# --------------------------------------------------------------------------------------

_NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)*)(\s?%|\+|x\b|k\b|m\b|bn\b)?", re.I)


def _numbers(text):
    """Numbers that make a claim. Years, months in dates and single digits are not claims."""
    out = set()
    clean = re.sub(r"\b\d{1,2}/\d{4}\b", " ", text)            # 07/2021
    clean = re.sub(r"\b(?:19|20)\d\d\b", " ", clean)            # 2021
    clean = re.sub(r"\+\d[\d\s]{7,}", " ", clean)               # phone numbers
    clean = re.sub(r"https?://\S+|<[^>]+>", " ", clean)         # urls
    for m in _NUM.finditer(clean):
        n = m.group(1).replace(",", "")
        if len(n.replace(".", "")) < 2 and "." not in n:
            continue
        out.add(n)
    return out


def _profile_text(p):
    return pathlib.Path(p).read_text(encoding="utf-8") if p else ""


# --------------------------------------------------------------------------------------
# The CV gate
# --------------------------------------------------------------------------------------

def _fit_keywords(fit):
    """Keywords from fit.md: the list under a heading containing 'keyword'."""
    if not fit or not pathlib.Path(fit).exists():
        return []
    txt = pathlib.Path(fit).read_text(encoding="utf-8")
    m = re.search(r"^#+ [^\n]*keyword[^\n]*\n(.*?)(?=^#+ |\Z)", txt, re.S | re.I | re.M)
    if not m:
        return []
    kws = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith(("-", "*")):
            kws += [k.strip(" `*") for k in re.split(r"[;,·]", line.lstrip("-* ")) if k.strip()]
    return kws


def lint_cv(md_path, profile=None, keywords=None, fit=None):
    text = pathlib.Path(md_path).read_text(encoding="utf-8")
    c = cv_md.md_to_content(text)
    fails, warns = [], []

    sections = c.get("sections", [])
    heads = [s.get("heading", "") for s in sections]

    # 1. No "Why …" section — that content belongs in the cover letter and the form.
    why = [h for h in heads if re.match(r"\s*why\b", h, re.I)]
    if why:
        fails.append(f"'{why[0]}' section on the CV — move it to the cover letter / why-answers")

    # Collect prose by where it sits.
    summary, prose, bullets_by_role = "", [], []
    roles = []
    for s in sections:
        h = s.get("heading", "").lower()
        cur = None
        for b in s.get("blocks", []):
            t = b.get("type")
            if t == "paragraph":
                prose.append(b.get("text", ""))
                if "summary" in h or "profile" in h:
                    summary += " " + b.get("text", "")
            elif t == "role":
                cur = {"title": b.get("title", ""),
                       "org": re.split(r"\s*[·|]\s*", b.get("org") or "")[0].strip(),
                       "dates": b.get("dates", ""), "bullets": []}
                roles.append(cur)
                if b.get("scope"):
                    prose.append(b["scope"])
            elif t == "bullet":
                full = ((b.get("lead") or "") + " " + (b.get("text") or "")).strip()
                prose.append(full)
                if cur is not None and "experience" in h:
                    cur["bullets"].append(b)
            elif t == "kv":
                for it in b.get("items", []):
                    prose.append(" ".join(str(x) for x in (it if isinstance(it, (list, tuple)) else [it])))
    body = "\n".join(prose)

    # 2. Chronology — strictly reverse by start date. Relevance is shown by depth, never order.
    starts = [(r, parse_range(r["dates"])[0]) for r in roles]
    dated = [(r, s) for r, s in starts if s]
    for (a, sa), (b, sb) in zip(dated, dated[1:]):
        if sb > sa:
            fails.append(f"roles out of date order: '{a['org'] or a['title']}' ({a['dates']}) "
                         f"is listed above '{b['org'] or b['title']}' ({b['dates']})")
    undated = [r["org"] or r["title"] for r, s in starts if not s]
    if undated:
        warns.append(f"roles with no parseable dates: {', '.join(undated)}")
    # Overlaps are allowed but reported — the playbook decides how they are framed.
    rng = [(r, parse_range(r["dates"])) for r in roles]
    ov = []
    for i, (a, (sa, ea)) in enumerate(rng):
        for b, (sb, eb) in rng[i + 1:]:
            if sa and ea and sb and eb and sa < eb and sb < ea:
                ov.append(f"{a['org'] or a['title']} ∩ {b['org'] or b['title']}")
    if ov:
        warns.append("overlapping roles (frame per profile policy): " + "; ".join(ov[:6]))

    # 3. Voice.
    fp = sorted(set(re.findall(FIRST_PERSON, summary + "\n" + "\n".join(
        (b.get("lead") or "") + " " + (b.get("text") or "") for r in roles for b in r["bullets"]))))
    if fp:
        fails.append(f"first person on the CV ({', '.join(fp)}) — write implied-subject")
    hits = _banned_hits(body, _profile_text(profile))
    if hits:
        fails.append(f"banned phrases: {', '.join(hits)}")
    np_ = _regex_hits(body, NEG_PARALLEL)
    if np_:
        fails.append(f"negative-parallel cadence: {np_[0]!r}")
    sd = _regex_hits(body, SELF_DISQUALIFY)
    if sd:
        fails.append(f"self-disqualifying line: {sd[0]!r} — gaps go in fit.md, not on the CV")
    ph = _regex_hits(body, PLACEHOLDER, 0)
    if ph:
        fails.append(f"placeholder left in: {ph[0]!r}")
    dashes = body.count("—") + body.count(" – ")
    if dashes > EM_DASH_MAX:
        fails.append(f"{dashes} em-dashes in prose (max {EM_DASH_MAX})")
    for r in roles:
        bs = r["bullets"]
        if len(bs) >= 3:
            lead = sum(1 for b in bs if b.get("lead"))
            if lead / len(bs) > BOLD_LEAD_MAX:
                fails.append(f"{r['org'] or r['title']}: {lead}/{len(bs)} bullets have bold lead-ins "
                             f"(max half)")
    sw = len(summary.split())
    if summary and not (60 <= sw <= 130):
        warns.append(f"summary is {sw} words (aim 90–120)")

    # 4. Fact gate — numbers, employers, titles must exist in the profile.
    ptxt = _profile_text(profile)
    if ptxt:
        plow = ptxt.lower()
        pnums = _numbers(ptxt)
        missing = sorted(n for n in _numbers(body + " " + c.get("headline", "")) if n not in pnums)
        if missing:
            fails.append(f"numbers not in the profile: {', '.join(missing[:10])}")
        for r in roles:
            org = r["org"]
            if org and org.lower() not in plow:
                fails.append(f"employer not in the profile: '{org}'")
            title = (r["title"] or "").strip()
            if title and title.lower() not in plow:
                fails.append(f"title not in the profile's allowed list: '{title}'")
        for verb in ("built", "created", "designed", "invented", "authored"):
            for m in re.finditer(rf"\b{verb} ([A-Z][\w.+-]+)", body):
                tool = m.group(1)
                if tool.lower() in plow and not re.search(rf"\b{verb}\b[^.\n]{{0,40}}{re.escape(tool)}",
                                                          ptxt, re.I):
                    warns.append(f"'{verb} {tool}' — profile shows use of {tool}, check it was built")

    # 5. Keywords: the fit file's list must be on the page, the top five in the summary.
    kws = [k for k in (keywords or "").split(";") if k.strip()] or _fit_keywords(fit)
    if kws:
        low = (body + " " + c.get("headline", "")).lower()
        absent = [k for k in kws if k.lower() not in low]
        if absent:
            warns.append(f"fit keywords not on the page: {', '.join(absent[:10])}")
        top_absent = [k for k in kws[:5] if k.lower() not in (summary + c.get('headline', '')).lower()]
        if top_absent:
            warns.append(f"top keywords missing from the summary: {', '.join(top_absent)}")
        for r in roles[:3]:
            if r["bullets"]:
                first = ((r["bullets"][0].get("lead") or "") + " " + r["bullets"][0].get("text", "")).lower()
                if not any(k.lower() in first for k in kws):
                    warns.append(f"{r['org'] or r['title']}: first bullet carries no fit keyword")

    return fails, warns


# --------------------------------------------------------------------------------------
# The answers gate
# --------------------------------------------------------------------------------------

def _iter_answers(obj, prefix=""):
    """Yield (question, answer, maxlength). Accepts {q: a}, nested dicts, or a list of
    {question, answer, maxlength} objects. Keys starting with '_' are metadata."""
    if isinstance(obj, list):
        for it in obj:
            if isinstance(it, dict) and "answer" in it:
                yield it.get("question", "?"), it.get("answer"), it.get("maxlength")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("_"):
                continue
            if isinstance(v, dict) and "answer" in v:
                yield k, v.get("answer"), v.get("maxlength")
            elif isinstance(v, (dict, list)):
                yield from _iter_answers(v, f"{prefix}{k}.")
            else:
                yield f"{prefix}{k}", v, None


def lint_answers(path, profile=None):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    fails, warns = [], []
    items = list(_iter_answers(data))
    if not items:
        return ["answers.json holds no answers"], []
    ptxt = _profile_text(profile)
    pnums = _numbers(ptxt) if ptxt else set()
    for q, a, maxlen in items:
        if a is None or (isinstance(a, str) and not a.strip()):
            warns.append(f"empty answer: {q}")
            continue
        if not isinstance(a, str):
            continue
        ph = _regex_hits(a, PLACEHOLDER, 0)
        if ph:
            fails.append(f"{q}: placeholder or internal instruction {ph[0]!r}")
        if maxlen and len(a) > int(maxlen):
            fails.append(f"{q}: {len(a)} chars > maxlength {maxlen}")
        if len(a) < 120:          # short factual answers are not prose
            continue
        hits = _banned_hits(a, ptxt)
        if hits:
            fails.append(f"{q}: banned phrases {', '.join(hits)}")
        np_ = _regex_hits(a, NEG_PARALLEL)
        if np_:
            fails.append(f"{q}: negative-parallel cadence {np_[0]!r}")
        sd = _regex_hits(a, SELF_DISQUALIFY)
        if sd:
            fails.append(f"{q}: volunteers a gap {sd[0]!r}")
        if a.count("—") > 1:
            fails.append(f"{q}: {a.count('—')} em-dashes (max 1)")
        if ptxt:
            extra = sorted(n for n in _numbers(a) if n not in pnums)
            if extra:
                fails.append(f"{q}: numbers not in the profile {', '.join(extra[:6])}")
    return fails, warns


# --------------------------------------------------------------------------------------

def _report(kind, target, fails, warns):
    for w in warns:
        print("WARN:", w)
    for f in fails:
        print("FAIL:", f)
    ok = not fails
    print("RESULT:", "PASS" if ok else "FAIL")
    gp = _gates_path(target)
    _write_gate(gp, kind, {"pass": ok, "file": pathlib.Path(target).name, "at": _now(),
                           "fails": fails, "warns": warns})
    print(f"gate '{kind}' recorded in {gp}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("cv")
    g.add_argument("md"); g.add_argument("--profile"); g.add_argument("--keywords")
    g.add_argument("--fit")
    g = sub.add_parser("answers")
    g.add_argument("json"); g.add_argument("--profile")
    g = sub.add_parser("review")
    g.add_argument("appdir"); g.add_argument("--verdict", required=True,
                                             choices=["shortlist", "maybe", "reject"])
    g.add_argument("--reason", default="")
    g = sub.add_parser("status")
    g.add_argument("appdir")
    a = ap.parse_args()

    if a.cmd == "cv":
        f, w = lint_cv(a.md, a.profile, a.keywords, a.fit)
        sys.exit(_report("cv", a.md, f, w))
    if a.cmd == "answers":
        f, w = lint_answers(a.json, a.profile)
        sys.exit(_report("answers", a.json, f, w))
    if a.cmd == "review":
        gp = _gates_path(a.appdir)
        _write_gate(gp, "review", {"pass": a.verdict == "shortlist", "verdict": a.verdict,
                                   "reason": a.reason, "at": _now()})
        print(f"review '{a.verdict}' recorded in {gp}")
        sys.exit(0)
    if a.cmd == "status":
        ok, why = gates_ok(a.appdir)
        print("GATES:", "PASS" if ok else "FAIL — " + why)
        sys.exit(0 if ok else 1)


def gates_ok(appdir):
    """(ok, reason). All three gates present and passing. Used by learn.py."""
    gp = _gates_path(appdir)
    if not gp.exists():
        return False, "no gates.json — run lint_cv.py cv / answers / review"
    try:
        g = json.loads(gp.read_text(encoding="utf-8"))
    except ValueError:
        return False, "gates.json unreadable"
    for k in ("cv", "answers", "review"):
        if k not in g:
            return False, f"gate '{k}' not run"
        if not g[k].get("pass"):
            extra = g[k].get("verdict") or "; ".join(g[k].get("fails", [])[:2])
            return False, f"gate '{k}' failed ({extra})"
    return True, "ok"


if __name__ == "__main__":
    main()
