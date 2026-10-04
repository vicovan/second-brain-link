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
    lint_cv.py cv <cv.md> [--profile profile.md] [--keywords "a;b;c"] [--fit fit.md] [--posting posting.md]
    lint_cv.py answers <answers.json> [--profile profile.md]
    lint_cv.py review <app dir> --verdict shortlist|maybe|reject [--reads-generated] [--reason "..."]
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
    # abstract self-description standing in for a fact — seen in generated CVs that drew
    # "reads generated" from reviewers
    "first-class", "first class", "in one seat", "the normal case", "product substance",
    "single mandate", "as a matter of course", "-level ownership",
    # filler a recruiter has read on every CV that day — it names no thing and no result
    "best practices", "cross-functional collaboration", "high-performing team", "key initiatives",
    "innovative solutions", "scalable solutions", "modern data stack", "fostered a culture",
    "drove alignment", "strategic initiatives", "wide range of", "a variety of", "successfully",
    "effectively", "efficiently", "instrumental in", "played a key role", "worked closely with",
]

# A bullet must carry at least one anchor a reader can picture: a number, or a name (a product,
# customer, market, standard, system). These capitalised words do not count — every CV has them.
GENERIC_CAPS = {"AI", "API", "APIs", "SaaS", "B2B", "B2C", "ML", "LLM", "LLMs", "CEO", "CTO",
                "CPO", "VP", "IT", "UI", "UX", "QA", "HR", "R&D", "KPI", "KPIs", "OKR", "OKRs"}
_NUMBER_WORDS = re.compile(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                           r"fifteen|twenty|thirty|forty|fifty|hundreds?|thousands?|millions?|"
                           r"billions?|dozens?|double[ds]?|tripled?|halved?)\b", re.I)
GENERIC_PER_ROLE = 1

# Consistency: a reader who notices "organise" beside "authorize", or "CTO" beside "Chief
# Technology Officer", reads a page assembled from parts. One choice, everywhere.
SPELLING = [  # (British stem, American stem)
    ("organis", "organiz"), ("authoris", "authoriz"), ("optimis", "optimiz"),
    ("prioritis", "prioritiz"), ("standardis", "standardiz"), ("tokenis", "tokeniz"),
    ("modernis", "moderniz"), ("customis", "customiz"), ("centralis", "centraliz"),
    ("recognis", "recogniz"), ("specialis", "specializ"), ("analys", "analyz"),
    ("defence", "defense"), ("licence", "license"), ("behaviour", "behavior"),
    ("colour", "color"), ("centre", "center"), ("travell", "travel"),
]
TITLE_FORMS = [("CTO", "Chief Technology Officer"), ("CEO", "Chief Executive Officer"),
               ("CPO", "Chief Product Officer"), ("CIO", "Chief Information Officer"),
               ("COO", "Chief Operating Officer"), ("VP", "Vice President")]
_PAST_IRREGULAR = set("""built led ran made set wrote took gave grew drove won cut sold brought
began became kept held met chose found taught spent sent shipped""".split())

# Words that are a tell when the CV uses them and the posting does not: system-design jargon a
# hiring manager has to translate. Allowed when the posting itself says them.
POSTING_ONLY = ["deterministic", "orchestrat", "end to end", "end-to-end", "paradigm",
                "spreading activation", "pagerank", "idempoten", "synergis"]
# Fine once, a tic when repeated.
CAPPED = {"end to end": 1, "end-to-end": 1}

# A bullet whose first clause is a label followed by a colon and a list — the `**Lead:** a, b,
# c` shape. Once is a rhythm; on every bullet it is the template.
COLON_BULLET = re.compile(r"^[^:.;]{3,90}:\s")
COLON_PER_ROLE, COLON_PER_CV = 1, 3

# Sentence length caps. A recruiter reads in short bursts; a 45-word sentence is skipped.
SUMMARY_SENT_MAX, BULLET_SENT_MAX = 28, 32
SUMMARY_WORDS = (55, 90)

# "VP-level", "director-level scope" — a candidate describing a level instead of a title they
# held. It echoes the posting and reads as tailoring.
LEVEL_ECHO = re.compile(r"\b(?:vp|svp|evp|director|head|principal|staff|executive|exec|c-suite|"
                        r"cto|cpo|cio|chief|senior|lead|manager)[- ]level\b|\bscope equivalent\b|"
                        r"\b[\w-]+-scope\b", re.I)
HEADLINE_MAX = 80
JARGON_PER_BULLET = 3
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


_STOP = set("""the and for with from into over that this their your our are was were has have had
will would can could about across while within without under using used other more most than
then also such only each both very team teams work working role roles years year experience""".split())


def _sentences(text):
    text = re.sub(r"\*\*|\*", "", text)
    return [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])", text.strip()) if x.strip()]


def _date_style(dates):
    """'m' for MM/YYYY tokens, 'y' for bare years, per token; empty when undated."""
    out = set()
    for tok in re.split(r"\s*[–—-]\s*", dates or ""):
        tok = tok.strip()
        if re.fullmatch(r"\d{1,2}/\d{4}", tok):
            out.add("m")
        elif re.fullmatch(r"\d{4}", tok):
            out.add("y")
        elif re.fullmatch(r"[A-Za-z]{3,9}\.? \d{4}", tok):
            out.add("mon")
    return out


def _core_title(role):
    """The title without a team qualifier: 'VP Product - Back of House' -> 'VP Product'."""
    return re.split(r"\s*,\s*|\s+[-–—(|]\s*", (role or "").strip())[0].strip()


def _jargon(text):
    """Acronyms (MDES, DASP) and inner-capital product names (ConnexPay) in a bullet."""
    toks = re.findall(r"\b[A-Z][A-Z0-9]{1,}s?\b|\b[A-Z][a-z]+[A-Z][A-Za-z]+\b", text)
    return [t for t in toks if t not in ("AI", "API", "APIs", "US", "UK", "EU", "UAE", "CTO",
                                         "CEO", "VP", "ML", "SaaS")]


def _has_kw(k, text):
    """Whole-word keyword match: 'AI' must not match inside 'air-gapped'."""
    return re.search(r"(?<![a-z0-9])" + re.escape(k.lower()) + r"(?![a-z0-9])", text) is not None


def _anchored(text, own=()):
    """True if a bullet names something specific: a number, or a capitalised name that is not
    the bullet's first word, not one of the words every CV carries, and not the role's own
    employer (naming your own company in its own role adds nothing a reader did not know)."""
    plain = re.sub(r"\*\*|\*|\[|\]\([^)]*\)", "", text).strip()
    if re.search(r"\d", plain) or _NUMBER_WORDS.search(plain):
        return True
    words = re.findall(r"[A-Za-z][\w&.+'-]*", plain)
    own = {w.lower() for w in own}
    return any(w[0].isupper() and w.strip(".") not in GENERIC_CAPS
               and w.strip(".'s").lower() not in own for w in words[1:])


def _sibling(fit, name):
    if not fit:
        return None
    p = pathlib.Path(fit).parent / name
    return p if p.exists() else None


def lint_cv(md_path, profile=None, keywords=None, fit=None, posting=None):
    text = pathlib.Path(md_path).read_text(encoding="utf-8")
    c = cv_md.md_to_content(text)
    fails, warns = [], []

    sections = c.get("sections", [])
    heads = [s.get("heading", "") for s in sections]

    # 1. No "Why …" section — that content belongs in the cover letter and the form.
    why = [h for h in heads if re.match(r"\s*why\b", h, re.I)]
    if why:
        fails.append(f"'{why[0]}' section on the CV — move it to the cover letter / why-answers")

    # 1b. No skills block above the work history — a grid of labelled skill groups (or a wall
    # of terms) at the top reads as generated and pushes the evidence below the fold. Skills are
    # one plain line at the end.
    exp_at = next((i for i, h in enumerate(heads) if re.search(r"experience|employment|career", h, re.I)),
                  len(heads))
    for s_ in sections[:exp_at]:
        h_ = s_.get("heading", "")
        if re.search(r"competenc|skills|expertise|technolog", h_, re.I) or \
                any(b.get("type") == "kv" for b in s_.get("blocks", [])):
            fails.append(f"'{h_}' sits above the work history — move skills to one plain "
                         f"'## Skills' line at the end")
            break

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
                       "org_full": re.split(r"\s*·\s*", b.get("org") or "")[0],
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
            # year-only ranges ("2021 – 2022", "2022 – 2025") share a boundary year without
            # overlapping; only count it when the overlap is more than that one year
            yearly = re.fullmatch(r"\s*\d{4}\s*[–—-]\s*(\d{4}|present|now)\s*", a["dates"] or "", re.I) \
                and re.fullmatch(r"\s*\d{4}\s*[–—-]\s*(\d{4}|present|now)\s*", b["dates"] or "", re.I)
            if yearly and sa and ea and sb and eb and (sa[0] == eb[0] or sb[0] == ea[0]):
                continue
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
    if summary and sw > SUMMARY_WORDS[1] + 10:
        fails.append(f"summary is {sw} words (max {SUMMARY_WORDS[1]}) — cut it; the six-second "
                     f"read stops at the third line")
    elif summary and not (SUMMARY_WORDS[0] <= sw <= SUMMARY_WORDS[1]):
        warns.append(f"summary is {sw} words (aim {SUMMARY_WORDS[0]}–{SUMMARY_WORDS[1]})")

    # 3b. Rhythm — the tells that are about shape, not vocabulary.
    ss = _sentences(summary)
    long_s = [x for x in ss if len(x.split()) > SUMMARY_SENT_MAX]
    if long_s:
        fails.append(f"summary sentence of {len(long_s[0].split())} words (max {SUMMARY_SENT_MAX}): "
                     f"{long_s[0][:70]!r}…")
    if len(ss) >= 2 and not any(len(x.split()) < 12 for x in ss):
        warns.append("no summary sentence under 12 words — even lengths read as generated")
    colon_total = 0
    for r in roles:
        n = 0
        for b in r["bullets"]:
            full = ((b.get("lead") or "") + " " + (b.get("text") or "")).strip()
            plain = re.sub(r"\*\*|\*", "", full)
            if (b.get("lead") or "").rstrip().endswith(":") or COLON_BULLET.match(plain):
                n += 1
            for x in _sentences(full):
                if len(x.split()) > BULLET_SENT_MAX:
                    fails.append(f"{r['org'] or r['title']}: a {len(x.split())}-word sentence "
                                 f"(max {BULLET_SENT_MAX}): {x[:60]!r}…")
                    break
        colon_total += n
        if n > COLON_PER_ROLE:
            fails.append(f"{r['org'] or r['title']}: {n} 'Label: a, b, c' bullets (max "
                         f"{COLON_PER_ROLE} per role) — open with a verb instead")
    if colon_total > COLON_PER_CV:
        fails.append(f"{colon_total} 'Label: a, b, c' bullets on the CV (max {COLON_PER_CV})")

    # 3c. Vocabulary the posting did not ask for, and repeated tics.
    ppath = posting or _sibling(fit, "posting.md")
    ptext = _profile_text(ppath).lower() if ppath else ""
    blow = body.lower()
    pj = [w for w in POSTING_ONLY if w in blow and w not in ptext]
    if pj:
        fails.append(f"jargon the posting does not use: {', '.join(pj)} — say what it did for "
                     f"the business instead")
    for w, cap in CAPPED.items():
        k = blow.count(w)
        if k > cap and w in ptext:
            fails.append(f"'{w}' used {k}× (max {cap})")
    for r in roles[:3]:
        for b in r["bullets"]:
            full = (b.get("lead") or "") + " " + (b.get("text") or "")
            j = [t for t in _jargon(full) if t.lower() not in ptext]
            if len(j) > JARGON_PER_BULLET:
                warns.append(f"{r['org'] or r['title']}: {len(j)} acronyms/product names in one "
                             f"bullet ({', '.join(j[:5])}) — a recruiter cannot read it")
                break

    # 3d. Headline and title echo.
    target = (c.get("target") or {}).get("role", "")
    head = c.get("headline", "") or ""
    core = _core_title(target)
    if core and head:
        hl = head.lower()
        if core.lower() not in hl and target.lower() not in hl:
            fails.append(f"headline does not carry the target title '{core}'")
        elif hl.find(core.lower()) > 0 and hl.find(target.lower()) != 0:
            fails.append(f"headline puts something in front of the target title '{core}'")
        if len(head) > max(HEADLINE_MAX, len(target) + 30):
            fails.append(f"headline is {len(head)} characters (max {HEADLINE_MAX}) — title plus one "
                         f"short differentiator")
    rest = "\n".join(p for p in prose if p not in summary)
    le = LEVEL_ECHO.search(rest + "\n" + head)
    if le:
        fails.append(f"level/scope echo {le.group(0)!r} — state the team, the reach or the result "
                     f"instead of a level")
    if core and len(core.split()) >= 2 and core.lower() in rest.lower():
        fails.append(f"target title '{core}' repeated in the body — headline and summary only")

    # 3f. Role-line descriptors in Title Case, like the rest of the role line.
    small = {"a", "an", "and", "for", "of", "the", "to", "in", "on", "at", "by", "or", "with"}
    for s_ in sections:
        for b in s_.get("blocks", []):
            if b.get("type") != "role" or "·" not in (b.get("org") or ""):
                continue
            desc = b["org"].split("·", 1)[1].strip()
            low_words = [w for w in re.findall(r"[A-Za-z][\w'-]*", desc)
                         if w[0].islower() and w.lower() not in small]
            if low_words:
                warns.append(f"role descriptor not in Title Case: '{desc}'")

    # 3g. Consistency.
    allt = (summary + "\n" + body).lower()
    gb_hits, us_hits = [], []
    for gb, us in SPELLING:
        if us == "travel":
            g = re.search(r"\btravell(?:ed|ing|er)", allt)
            u = re.search(r"\btravel(?:ed|ing|er)\b", allt)
        else:
            g, u = re.search(r"\b" + gb, allt), re.search(r"\b" + us, allt)
        if g:
            gb_hits.append(g.group(0))
        if u:
            us_hits.append(u.group(0))
    if gb_hits and us_hits:
        fails.append(f"spelling mixes British ({', '.join(gb_hits[:3])}…) and American "
                     f"({', '.join(us_hits[:3])}…) — pick one, matching the posting")
    titles = " ".join((r["title"] or "") for r in roles)
    for short, long_ in TITLE_FORMS:
        if re.search(rf"\b{short}\b", titles) and long_.lower() in titles.lower():
            fails.append(f"role titles mix '{short}' and '{long_}' — use one form throughout")
    all_b = [((b.get("lead") or "") + " " + (b.get("text") or "")).strip()
             for r in roles for b in r["bullets"]]
    ends = {t.rstrip()[-1:] == "." for t in all_b if t}
    if len(ends) > 1:
        fails.append("some bullets end with a full stop and some do not — make them all the same")
    dashes_used = {m for r in roles for m in re.findall(r"\d\s*([–—-])\s*(?:\d|present)", r["dates"] or "", re.I)}
    if len(dashes_used) > 1:
        fails.append(f"date ranges use different dashes ({' '.join(sorted(dashes_used))}) — use one")
    for r in roles:
        ended = not re.search(r"present|now|current", r["dates"] or "", re.I)
        tenses = set()
        for b in r["bullets"]:
            w = re.sub(r"\*\*|\*", "", (b.get("lead") or "") + " " + (b.get("text") or "")).split()
            if not w:
                continue
            f = w[0].lower().strip(":,")
            if f.endswith("ed") or f in _PAST_IRREGULAR:
                tenses.add("past")
            elif f.endswith("s") and not f.endswith("ss") and len(f) > 3:
                tenses.add("present")
        if ended and "present" in tenses:
            fails.append(f"{r['org'] or r['title']}: present tense in a role that has ended — past tense")
        elif len(tenses) > 1:
            warns.append(f"{r['org'] or r['title']}: bullets mix present and past tense")

    # 3e. Dates: one format throughout.
    styles = set()
    for r in roles:
        styles |= _date_style(r["dates"])
    if len(styles) > 1:
        fails.append("dates mix formats (" + ", ".join(sorted({'m': 'MM/YYYY', 'y': 'YYYY',
                     'mon': 'Mon YYYY'}[x] for x in styles)) + ") — use one throughout")

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

        # 6. Relevance — every bullet in the three most recent roles must serve the posting.
        # A bullet sharing no word with the fit keywords answers a question nobody asked.
        vocab = {w for k in kws for w in re.findall(r"[a-z][a-z0-9+#/-]{3,}", k.lower())} - _STOP
        vocab |= {k.lower() for k in kws}
        for r in roles[:3]:
            off = []
            for b in r["bullets"]:
                full = ((b.get("lead") or "") + " " + (b.get("text") or "")).lower()
                words = set(re.findall(r"[a-z][a-z0-9+#/-]{3,}", full))
                if not (words & vocab) and not any(_has_kw(k, full) for k in kws):
                    off.append(full[:50])
            if len(off) > 1:
                fails.append(f"{r['org'] or r['title']}: {len(off)} bullets share nothing with the "
                             f"fit keywords (max 1) — cut or re-point: {off[0]!r}…")
    if fit and pathlib.Path(fit).exists() and not re.search(
            r"^#+ [^\n]*bullet plan", pathlib.Path(fit).read_text(encoding="utf-8"), re.I | re.M):
        warns.append("fit.md has no '## Bullet plan' — map each critical requirement to one proof first")

    # 6b. Specificity — a bullet that could sit on any other candidate's CV is not read. Every
    # bullet in the three most recent roles needs an anchor (a number or a name).
    for r in roles[:3]:
        loose = [((b.get("lead") or "") + " " + (b.get("text") or "")).strip()
                 for b in r["bullets"]]
        own = re.findall(r"[A-Za-z][\w&-]*", r.get("org_full") or r["org"] or "")
        loose = [t for t in loose if not _anchored(t, own)]
        for t in loose:
            warns.append(f"{r['org'] or r['title']}: generic bullet (no number, no name): {t[:60]!r}…")
        if len(loose) > GENERIC_PER_ROLE:
            fails.append(f"{r['org'] or r['title']}: {len(loose)} bullets with no number and no name "
                         f"(max {GENERIC_PER_ROLE}) — say which product, customer, market or system, "
                         f"or cut it")

    # 7. Countable scope — a recent role with no figure at all gives a recruiter nothing to weigh.
    for r in roles[:3]:
        if r["bullets"] and not any(re.search(r"\d", (b.get("lead") or "") + (b.get("text") or ""))
                                    for b in r["bullets"]):
            warns.append(f"{r['org'] or r['title']}: no countable scope (team, sites, users, volume)")

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
    g.add_argument("--fit"); g.add_argument("--posting", help="posting.md (default: beside --fit)")
    g = sub.add_parser("answers")
    g.add_argument("json"); g.add_argument("--profile")
    g = sub.add_parser("review")
    g.add_argument("appdir"); g.add_argument("--verdict", required=True,
                                             choices=["shortlist", "maybe", "reject"])
    g.add_argument("--reason", default="")
    g.add_argument("--reads-generated", action="store_true",
                   help="the reviewer said it reads as AI-written — blocks like a maybe")
    g = sub.add_parser("status")
    g.add_argument("appdir")
    a = ap.parse_args()

    if a.cmd == "cv":
        f, w = lint_cv(a.md, a.profile, a.keywords, a.fit, a.posting)
        sys.exit(_report("cv", a.md, f, w))
    if a.cmd == "answers":
        f, w = lint_answers(a.json, a.profile)
        sys.exit(_report("answers", a.json, f, w))
    if a.cmd == "review":
        gp = _gates_path(a.appdir)
        ok = a.verdict == "shortlist" and not a.reads_generated
        _write_gate(gp, "review", {"pass": ok, "verdict": a.verdict
                                   + (" (reads generated)" if a.reads_generated else ""),
                                   "reads_generated": a.reads_generated,
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
