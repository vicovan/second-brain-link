#!/usr/bin/env python3
"""
knockout.py — find the questions that reject an application automatically, BEFORE any CV
is written.

Fast, generic rejections are rarely about the CV. Greenhouse, Ashby and Lever let an employer
auto-reject on a handful of answers: right to work in a named country, where the candidate
lives, a required language, degree or clearance, a salary figure outside the band. An
application that answers one of those "wrong" is gone within hours however good the CV is,
and every token spent tailoring it was wasted.

This reads the job description (and, once the form is open, its question text) and checks
each such requirement against the `## Knock-outs` block in the user's
`profile/application-answers.md`.

    PASS   nothing found that the profile cannot meet
    FLAG   something to look at, or to answer carefully — the job may proceed
    STOP   a requirement the profile cannot truthfully meet — skip before building a CV

Every finding quotes the sentence it came from, verbatim, so the decision can be checked.
Deterministic, stdlib only, zero network. The model still reads the posting; this makes sure
the knock-outs are never the thing it skimmed past.

Usage:
    knockout.py --jd posting.txt [--form questions.txt] [--answers application-answers.md] [--json]
    cat posting.txt | knockout.py --jd -

Exit code: 0 PASS or FLAG, 1 STOP, 2 usage/profile error.
"""
import argparse, json, os, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
for p in (HERE, HERE.parent.parent / "job-scout" / "scripts"):
    sys.path.insert(0, str(p))

# ------------------------------------------------------------------------------------------
# Places. Enough to recognise where a posting says the work is. Codes are ISO-3166 alpha-2,
# plus the groups the profile may name (EU, EEA).
# ------------------------------------------------------------------------------------------
EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
      "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
EEA = EU | {"IS", "LI", "NO"}
GROUPS = {"EU": EU, "EEA": EEA, "EU/EEA": EEA, "GCC": {"AE", "SA", "QA", "KW", "BH", "OM"}}

PLACES = {
    "GB": ["united kingdom", "uk", "u.k.", "britain", "england", "scotland", "wales", "london",
           "manchester", "edinburgh", "bristol", "cambridge", "oxford", "belfast"],
    "US": ["united states", "usa", "u.s.", "us-based", "new york", "san francisco", "seattle",
           "boston", "austin", "chicago", "los angeles", "bay area"],
    "CA": ["canada", "toronto", "vancouver", "montreal"],
    "CH": ["switzerland", "zurich", "zürich", "geneva", "lausanne", "basel", "zug", "bern"],
    "AE": ["united arab emirates", "uae", "dubai", "abu dhabi"],
    "SA": ["saudi arabia", "ksa", "riyadh", "jeddah"],
    "QA": ["qatar", "doha"],
    "IL": ["israel", "tel aviv"],
    "SG": ["singapore"], "IN": ["india", "bangalore", "bengaluru"], "AU": ["australia", "sydney"],
    "DE": ["germany", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne"],
    "FR": ["france", "paris", "lyon"], "ES": ["spain", "madrid", "barcelona", "valencia"],
    "NL": ["netherlands", "amsterdam", "rotterdam", "eindhoven", "utrecht"],
    "IE": ["ireland", "dublin"], "PT": ["portugal", "lisbon", "porto"],
    "IT": ["italy", "milan", "rome"], "PL": ["poland", "warsaw", "krakow", "kraków", "wroclaw"],
    "RO": ["romania", "bucharest", "cluj", "iasi", "iași"], "SE": ["sweden", "stockholm"],
    "DK": ["denmark", "copenhagen"], "FI": ["finland", "helsinki", "espoo"],
    "NO": ["norway", "oslo"], "BE": ["belgium", "brussels"], "AT": ["austria", "vienna"],
    "CZ": ["czech", "prague"], "EE": ["estonia", "tallinn"], "LT": ["lithuania", "vilnius"],
    "HU": ["hungary", "budapest"], "GR": ["greece", "athens"], "LU": ["luxembourg"],
}
_PLACE_RE = [(code, re.compile(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", re.I))
             for code, names in PLACES.items() for n in names]
# "EU"/"Europe" as the named region of a requirement.
_REGION_RE = [("EU", re.compile(r"\b(?:EU|EEA|European Union|Europe(?:an)?)\b"))]

LANGS = ["german", "french", "spanish", "italian", "dutch", "polish", "portuguese", "swedish",
         "danish", "norwegian", "finnish", "czech", "hungarian", "romanian", "greek", "hebrew",
         "arabic", "mandarin", "chinese", "japanese", "korean", "russian", "turkish", "hindi",
         "english"]

# Rough FX to USD — good enough to compare against a floor; the skill says to check live rates
# for anything close.
FX = {"USD": 1.0, "$": 1.0, "EUR": 1.10, "€": 1.10, "GBP": 1.30, "£": 1.30, "CHF": 1.15,
      "AED": 0.27, "SAR": 0.27, "PLN": 0.25, "SEK": 0.095, "NOK": 0.094, "DKK": 0.147,
      "CAD": 0.73, "SGD": 0.75}


# ------------------------------------------------------------------------------------------
# Profile
# ------------------------------------------------------------------------------------------

def _answers_path(explicit):
    if explicit:
        return pathlib.Path(explicit)
    try:
        from paths import profile_dir
        p = pathlib.Path(profile_dir()) / "application-answers.md"
        if p.exists():
            return p
    except Exception:
        pass
    return None


def _codes(values):
    out = set()
    for v in values:
        v = v.strip()
        if not v:
            continue
        up = v.upper()
        if up in GROUPS:
            out |= GROUPS[up]
            out.add(up)
        elif len(up) == 2:
            out.add(up)
        else:
            out |= {c for c, rx in _PLACE_RE if rx.search(v)}
    return out


def load_profile(path):
    """Parse the `## Knock-outs` block: `- key: value` lines, comma-separated lists."""
    txt = pathlib.Path(path).read_text(encoding="utf-8")
    m = re.search(r"^##\s+[\d.]*\s*Knock-?outs[^\n]*\n(.*?)(?=^##\s|\Z)", txt, re.S | re.M | re.I)
    if not m:
        return None
    raw = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"\s*[-*]\s*([a-z_]+)\s*:\s*(.*?)\s*(?:#.*)?$", line)
        if mm:
            raw[mm.group(1)] = mm.group(2)
    lst = lambda k: [x.strip() for x in raw.get(k, "").split(",") if x.strip()]
    prof = {
        "right_to_work": _codes(lst("right_to_work")),
        "sponsorship_acceptable": _codes(lst("sponsorship_acceptable")),
        "based_in": _codes(lst("based_in")),
        "relocate_to": _codes(lst("relocate_to")),
        "nationalities": _codes(lst("nationalities")),
        "languages": {x.lower() for x in lst("languages")},
        "degrees": " ".join(lst("degrees")).lower(),
        "clearances": lst("clearances"),
        "years": int(re.sub(r"\D", "", raw.get("years_experience", "0")) or 0),
        "floor_usd": 0,
        "raw": raw,
    }
    f = re.match(r"([A-Z]{3}|[$€£])\s*([\d,.]+)\s*(k)?", raw.get("salary_floor", "").strip(), re.I)
    if f:
        amt = float(f.group(2).replace(",", "")) * (1000 if f.group(3) else 1)
        prof["floor_usd"] = amt * FX.get(f.group(1).upper(), FX.get(f.group(1), 1.0))
    return prof


# ------------------------------------------------------------------------------------------
# Scanning
# ------------------------------------------------------------------------------------------

def sentences(text):
    text = re.sub(r"[ \t]+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+|\n+|•|·(?=\s)", text)
    return [p.strip(" -*\t") for p in parts if len(p.strip()) > 3]


def places_in(s):
    found = {c for c, rx in _PLACE_RE if rx.search(s)}
    for code, rx in _REGION_RE:
        if rx.search(s):
            found.add(code)
    return found


def _covered(codes, allowed):
    """True if every named place is inside the allowed set (a region counts if named)."""
    if not codes:
        return True
    return all(c in allowed or (c == "EU" and ("EU" in allowed or EU <= allowed)) for c in codes)


RTW = re.compile(r"right to work|work(?:ing)? authori[sz]ation|authori[sz]ed to work|eligible to work|"
                 r"eligibility to work|work permit|visa|sponsor", re.I)
NO_SPONSOR = re.compile(r"(?:no|not|unable to|cannot|can['’]t|won['’]t|will not|do not|don['’]t)\s+"
                        r"(?:\w+\s+){0,3}(?:provide |offer )?(?:visa )?sponsor|without (?:visa )?sponsorship|"
                        r"must (?:already )?(?:have|hold) (?:the |full |existing )?(?:right|authori[sz]ation|eligibility)|"
                        r"must be (?:legally )?(?:authori[sz]ed|eligible) to work", re.I)
YES_SPONSOR = re.compile(r"(?:we|will|can|happy to|able to)\s+(?:\w+\s+){0,2}sponsor|sponsorship (?:is )?"
                         r"(?:available|provided|offered|possible)|visa support|relocation (?:and visa )?support", re.I)
BASED = re.compile(r"(?:must|should|need to|needs to|required to|will need to|have to)\s+(?:\w+\s+){0,2}"
                   r"(?:be )?(?:based|located|living|reside|resident|live)\b|"
                   r"(?:only|exclusively)\s+(?:\w+\s+){0,3}(?:candidates|applicants)?\s*(?:based|located|residing) in|"
                   r"(?:based|located|residing) in [^.]{0,40}\bonly\b|"
                   r"(?:are you|do you (?:currently )?(?:live|reside)|currently (?:based|located|living))", re.I)
NATIONALITY = re.compile(r"\b(?:nationals? only|citizens? only|citizenship (?:is )?required|must be a "
                         r"(?:\w+ )?(?:national|citizen)|(?:emirati|saudi|qatari|gcc|uae|british|us|u\.s\.) "
                         r"(?:nationals?|citizens?(?:hip)?)|emiratisation|emiratization|saudi[sz]ation|"
                         r"nationali[sz]ation)\b", re.I)
CLEARANCE = re.compile(r"\b(?:security clearance|SC clearance|DV clearance|NV1|NV2|TS/SCI|top secret|"
                       r"eligible for (?:security )?clearance|BPSS)\b", re.I)
REQUIRED = re.compile(r"\b(?:required|requirement|must|mandatory|essential|fluent|fluency|native|"
                      r"business[- ]level|professional (?:working )?proficiency|C1|C2)\b", re.I)
OPTIONAL = re.compile(r"\b(?:nice to have|a plus|is a plus|bonus|preferred|advantage|desirable|ideally)\b", re.I)
DEGREE = re.compile(r"\b(PhD|Ph\.D\.?|doctorate|master['’]?s(?: degree)?|MSc|M\.Sc\.?|MBA|"
                    r"bachelor['’]?s(?: degree)?|BSc|B\.Sc\.?|degree in)\b", re.I)
EQUIV = re.compile(r"or equivalent|equivalent (?:practical |professional )?experience", re.I)
YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?years", re.I)
ONSITE = re.compile(r"(\d)\s*(?:days?|x)\s*(?:a|per|/)\s*week\s*(?:in|at|from)?\s*(?:the|our)?\s*office|"
                    r"\bon-?site\b|\bin-office\b|\boffice-based\b|\bfully on-?site\b|\brelocat", re.I)
MONEY = re.compile(r"(USD|EUR|GBP|CHF|AED|SAR|PLN|SEK|NOK|DKK|CAD|SGD|[$€£])\s?(\d[\d,.]*)\s?(k|K|m|M)?"
                   r"(?:\s?(?:-|–|—|to)\s?(?:USD|EUR|GBP|CHF|AED|[$€£])?\s?(\d[\d,.]*)\s?(k|K|m|M)?)?")


def _amount(num, suf):
    v = float(num.replace(",", ""))
    if suf and suf.lower() == "k":
        v *= 1000
    elif suf and suf.lower() == "m":
        v *= 1_000_000
    return v


def scan(text, prof, source="jd"):
    findings = []  # (level, kind, quote, why)

    def add(level, kind, quote, why):
        findings.append({"level": level, "kind": kind, "quote": quote[:300], "why": why,
                         "source": source})

    allowed_live = prof["based_in"] | prof["right_to_work"]
    allowed_move = allowed_live | prof["relocate_to"]
    whole_sponsor = any(YES_SPONSOR.search(x) and not NO_SPONSOR.search(x) for x in sentences(text))

    for s in sentences(text):
        where = places_in(s)

        # 1. Right to work.
        if RTW.search(s):
            need = where - {"EU"} if where - {"EU"} else where
            unmet = {c for c in need if not _covered({c}, prof["right_to_work"])}
            if YES_SPONSOR.search(s) and not NO_SPONSOR.search(s):
                if unmet:
                    add("FLAG", "right_to_work", s, f"sponsorship offered for {', '.join(sorted(unmet))}")
            elif NO_SPONSOR.search(s) or (source == "form" and unmet):
                if unmet:
                    if unmet <= prof["sponsorship_acceptable"] and whole_sponsor:
                        add("FLAG", "right_to_work", s, "needs sponsorship; posting mentions sponsorship")
                    else:
                        add("STOP", "right_to_work", s,
                            f"requires existing right to work in {', '.join(sorted(unmet))}")
                elif not need and source == "form":
                    add("FLAG", "right_to_work", s, "right-to-work question with no country — answer per profile §2")
            elif unmet:
                add("FLAG", "right_to_work", s, f"work authorisation mentioned for {', '.join(sorted(unmet))}")

        # 2. Where the person must be.
        if BASED.search(s) and where:
            if not _covered(where, allowed_move):
                add("STOP", "location", s, f"must be based in {', '.join(sorted(where))}")
            elif not _covered(where, allowed_live):
                add("FLAG", "location", s,
                    f"requires relocating to {', '.join(sorted(where))} — a real commitment")

        # 3. Nationality and clearance.
        if NATIONALITY.search(s):
            add("STOP", "nationality", s, "citizenship gate — residency does not satisfy it")
        if CLEARANCE.search(s) and not prof["clearances"]:
            lvl = "FLAG" if OPTIONAL.search(s) else "STOP"
            add(lvl, "clearance", s, "security clearance usually requires citizenship or long residency")

        # 4. Languages.
        low = s.lower()
        for lang in LANGS:
            if re.search(rf"\b{lang}\b", low) and lang not in prof["languages"]:
                if OPTIONAL.search(s):
                    add("FLAG", "language", s, f"{lang.title()} is a plus")
                elif REQUIRED.search(s) or source == "form":
                    add("STOP", "language", s, f"{lang.title()} required")
                break

        # 5. Degrees.
        d = DEGREE.search(s)
        if d and REQUIRED.search(s) and not OPTIONAL.search(s):
            deg = d.group(1).lower()
            have = prof["degrees"]
            need_phd = deg.startswith(("phd", "ph.d", "doctor"))
            need_master = deg.startswith(("master", "msc", "m.sc", "mba"))
            ok = (("phd" in have or "doctor" in have) if need_phd else
                  any(t in have for t in ("master", "msc", "mba", "phd")) if need_master else bool(have))
            if not ok:
                add("FLAG" if EQUIV.search(s) else "STOP", "degree", s, f"{d.group(1)} required")

        # 6. Years.
        for y in YEARS.finditer(s):
            n = int(y.group(1))
            if prof["years"] and n > prof["years"] and REQUIRED.search(s + " required"):
                add("FLAG", "years", s, f"asks {n}+ years; profile says {prof['years']}")

        # 7. On-site / relocation commitments.
        if ONSITE.search(s) and source == "form":
            add("FLAG", "commitment", s, "answering yes commits to on-site/relocation — check profile")

    # 8. Salary — published band against the floor, sentence by sentence so a funding
    #    round in the next sentence is never mistaken for pay.
    if prof["floor_usd"]:
        for s in sentences(text):
            if re.search(r"funding|raised|series [a-e]\b|valuation|revenue|\barr\b|customers|users", s, re.I):
                continue
            for m in MONEY.finditer(s):
                cur = m.group(1)
                fx = FX.get(cur.upper(), FX.get(cur))
                if not fx:
                    continue
                lo = _amount(m.group(2), m.group(3))
                hi = _amount(m.group(4), m.group(5) or m.group(3)) if m.group(4) else lo
                if hi < 1000:        # a stray "$5" — not a salary
                    continue
                if re.search(r"month|/mo\b|per mo", s, re.I):
                    lo, hi = lo * 12, hi * 12
                elif hi < 20000:     # small numbers without a period marker are not annual pay
                    continue
                open_top = not m.group(4) and re.search(
                    r"(?:starting|from|at least|minimum|min\.?)\s+(?:at\s+)?" + re.escape(m.group(0)[:3])
                    + r"|" + re.escape(m.group(0)) + r"\s*\+", s, re.I)
                lo_usd, hi_usd = lo * fx, hi * fx
                if hi_usd < prof["floor_usd"] and not open_top:
                    add("STOP", "salary", s, f"published top of band ≈ ${hi_usd:,.0f}/yr, below the floor "
                                             f"${prof['floor_usd']:,.0f}")
                elif lo_usd < prof["floor_usd"]:
                    add("FLAG", "salary", s, f"band starts ≈ ${lo_usd:,.0f}/yr, below the floor "
                                             f"${prof['floor_usd']:,.0f}")
    return findings


def verdict(findings):
    if any(f["level"] == "STOP" for f in findings):
        return "STOP"
    if any(f["level"] == "FLAG" for f in findings):
        return "FLAG"
    return "PASS"


def _read(src):
    if src == "-":
        return sys.stdin.read()
    return pathlib.Path(src).read_text(encoding="utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--jd", required=True, help="posting text file, or - for stdin")
    ap.add_argument("--form", help="the form's question text, once the form is open")
    ap.add_argument("--answers", help="profile/application-answers.md (default: resolved)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    ans = _answers_path(a.answers)
    prof = load_profile(ans) if ans and ans.exists() else None
    if not prof:
        print("NO KNOCK-OUT PROFILE: add a '## Knock-outs' section to profile/application-answers.md "
              "(run job-search:job-onboarding). Without it every job is unscreened.", file=sys.stderr)
        sys.exit(2)

    findings = scan(_read(a.jd), prof, "jd")
    if a.form:
        findings += scan(_read(a.form), prof, "form")
    v = verdict(findings)
    if a.json:
        print(json.dumps({"verdict": v, "findings": findings}, indent=2, ensure_ascii=False))
    else:
        for f in findings:
            print(f"{f['level']:4}  {f['kind']:13} {f['why']}\n      “{f['quote']}”")
        print(f"VERDICT: {v}")
    sys.exit(1 if v == "STOP" else 0)


if __name__ == "__main__":
    main()
