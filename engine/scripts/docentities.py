#!/usr/bin/env python3
"""
docentities.py — deterministic entity mining for the document-store sources.

Runs ONLY over documents the sensitivity scanner tiered `clean` (their text is
already going into the brain) — never over a metadata-only stub.

  extract_people(text)  people named WITH a role: "Jane Doe — Co-founder & CTO",
                        "CEO: Jane Doe", a team table row, "**Jane Doe**, Advisor".
                        Precision-biased: a name alone, or a role alone, is not
                        enough (a wrong person is worse than a missed one).
  extract_goals(text)   goal / objective / OKR / milestone statements: bullets under
                        a "Goals"/"Objectives"/"OKRs"/"Milestones"/"Roadmap"/"Targets"
                        heading, and lines that say "Goal: …" / "Objective: …".
  pick_logo(...)        the company's own logo among the walked image files, by
                        filename only (e.g. `<company>-logo.svg`, `logo.png`).
  match_org_logo(...)   a counterparty's logo (`<vendor>.svg`, `<customer>-logo.png`).

Stdlib only, zero network, no AI.
"""
import re

ROLE_RE = re.compile(
    r"(?i)\b(co[- ]?founders?|founders?|founding (?:engineer|partner|member)|"
    r"ceo|cto|coo|cfo|cmo|cpo|cro|ciso|cio|chief [a-z]+ officer|"
    r"president|chair(?:man|woman|person)?|board (?:member|director|observer)|"
    r"non[- ]executive director|independent director|"
    r"advis[oe]rs?|advisory board(?: member)?|mentors?|"
    r"(?:angel )?investors?|general partner|managing partner|venture partner|"
    r"managing director|vice president|vp(?: of)? [a-z]+|svp(?: of)? [a-z]+|"
    r"head of [a-z]+(?: [a-z]+)?|director of [a-z]+(?: [a-z]+)?|general counsel|"
    r"(?:engineering|product|design|sales|marketing|operations|technical|tech) lead|"
    r"lead (?:engineer|developer|designer|architect)|principal engineer|"
    r"(?:product|program|project|account|engagement) manager|"
    r"solutions? architect|software engineer|developer)\b")

ROLE_CLASS = [
    ("investor", re.compile(r"(?i)\binvest|\bvc\b|venture partner|general partner|managing partner|\bfund\b|capital|angel")),
    ("founder", re.compile(r"(?i)founder|founding")),
    ("board", re.compile(r"(?i)board|chair|non[- ]executive|independent director")),
    ("advisor", re.compile(r"(?i)advis|mentor")),
    ("investor", re.compile(r"(?i)investor|general partner|managing partner|venture partner|angel")),
    ("executive", re.compile(r"(?i)\b(ceo|cto|coo|cfo|cmo|cpo|cro|ciso|cio|chief|president|managing director|vice president|vp|svp|general counsel)\b")),
    ("team", re.compile(r".")),
]

_NAME_TOKEN = r"[A-Z][a-zà-öø-ÿ'’]+(?:-[A-Z][a-zà-öø-ÿ'’]+)?"
_NAME = rf"{_NAME_TOKEN}(?: (?:van|von|de|da|del|di|la|le|bin|al)?\s?{_NAME_TOKEN}){{1,3}}"
NAME_RE = re.compile(rf"(?<![\w@./])({_NAME})(?![\w@])")

# Words that never appear in a person's name (organisations, places, documents, roles…)
STOP = set("""
the our this that these those your their his her its a an and or for with from to of in on at by as
team teams company companies group inc ltd llc gmbh corp corporation co plc sa ag labs lab capital ventures
partners partner fund funds program programme accelerator foundation university school institute
airlines airline airways air aviation bank pay payments card cards wallet platform studio brain link
api apis sdk app apps web website portal cloud data system systems service services solution solutions
product products project projects market markets sales marketing engineering operations finance legal
board advisory advisor advisors adviser investor investors founder founders cofounder co ceo cto coo cfo
chief officer president director directors head lead manager vice senior junior principal staff
global international national regional europe european america american asia asian africa middle east
north south west east united states kingdom london paris berlin new york san francisco
january february march april may june july august september october november december
monday tuesday wednesday thursday friday saturday sunday q1 q2 q3 q4
overview summary introduction appendix annex section page table figure diagram chapter part step phase
plan roadmap strategy goals goal objectives objective milestones milestone vision mission deck pitch
google microsoft amazon apple meta openai anthropic oracle salesforce hubspot slack notion github
privacy policy terms security compliance risk audit report analysis review proposal response
key features feature benefits benefit pricing price model models version release
agent agents prep interview launch mobile event events owner owners document documents management
executive executives approval approvals required approver change changes commander incident incidents
specific role roles super admin admins administrator third party liaison token tokens connect recover
copilot beta alpha after before login logout application applications functional drill primary secondary
contact contacts support customer customers user users request requests test tests testing feature module
developer developers portal dashboard settings flow flows process workflow procedure escalation emergency
backup recovery access control controls model summary overview details note notes draft final update
updates status open closed next last first all any each other more less high low medium critical major
minor quick start demo sandbox production staging live dev founders fund funds venture ventures capital
signatory signature name title date email phone address department division unit office committee
officer officers member members responsible accountable consulted informed owner raci sponsor stakeholder
""".split())

GOAL_HEAD_RE = re.compile(r"(?i)^(#{1,4})\s*(?:our\s+|key\s+|strategic\s+|company\s+|\d{4}\s+|q[1-4]\s+)?"
                          r"(goals?|objectives?|okrs?|milestones?|targets?|priorities|roadmap|north star|"
                          r"what we (?:will|want to) (?:achieve|do)|success (?:metrics|criteria)|kpis?)\b.*$")
GOAL_LINE_RE = re.compile(r"(?i)^\s*(?:[-*]\s*)?(?:\*\*)?(goal|objective|okr|milestone|target|north star|"
                          r"mission|vision)(?:\*\*)?\s*[:—–-]\s*(.{8,240})$")


def _is_name(cand):
    toks = cand.replace("-", " ").split()
    if not 2 <= len(toks) <= 4:
        return False
    for t in toks:
        tl = t.lower().strip("'’")
        if tl in STOP or len(tl) < 2:
            return False
    if any(t.isupper() and len(t) > 1 for t in toks):
        return False
    return True


def _role_class(role):
    for cls, rx in ROLE_CLASS:
        if rx.search(role):
            return cls
    return "team"


_ROLE_HEADING_RE = re.compile(r"^\s*(?i:" + ROLE_RE.pattern[4:] + r")\s+(?!of\b|at\b|and\b|&)[A-Z][a-z]")


def _role_ok(role):
    return bool(ROLE_RE.match(role.strip())) and not _ROLE_HEADING_RE.match(role.strip())


def _clean_role(role):
    role = re.split(r"\s[·—–|]\s|\(|\)|\[|;", role)[0]
    role = re.sub(r"[*_`|]+", " ", role)
    role = re.sub(r"\s+", " ", role).strip(" ,;:—–-()")
    # a tail cut mid-phrase ("…Digital Product and") loses its dangling joiner
    while True:
        r2 = re.sub(r"(?i)[\s,&]+(?:and|of|the|for|at|&)$", "", role).strip(" ,;:—–-")
        if r2 == role:
            break
        role = r2
    return role[:80]


def extract_people(text):
    """{name: {"role": str, "class": str, "hits": n}} — people named next to a role."""
    out = {}
    if not text:
        return out

    def add(name, role):
        name = re.sub(r"\s+", " ", name).strip()
        if not _is_name(name):
            return
        role = _clean_role(role)
        cur = out.get(name)
        if cur is None:
            out[name] = {"role": role, "class": _role_class(role), "hits": 1}
        else:
            cur["hits"] += 1
            if len(role) > len(cur["role"]) and _role_class(role) != "team":
                cur["role"], cur["class"] = role, _role_class(role)

    lines = [re.sub(r"^\s*(?:>\s*)*(?:[-*+]|\d+[.)])?\s*", "", re.sub(r"[*_`#]", "", l)).strip()
             for l in text.splitlines()]
    lines = [l for l in lines if l]
    for i, l in enumerate(lines[:-1]):
        nxt = lines[i + 1]
        if NAME_RE.fullmatch(l) and _is_name(l) and len(nxt) <= 80 and _role_ok(nxt):
            add(l, nxt)
        elif len(l) <= 60 and _role_ok(l) and NAME_RE.fullmatch(nxt) and _is_name(nxt):
            add(nxt, l)
    for m in re.finditer(r"(?<![\w])([A-Z][a-z]{2,15}) \((" + ROLE_RE.pattern[4:] + r")\)", text, re.I):
        first, role = m.group(1), m.group(2)
        if first[0].isupper() and first.lower() not in STOP:
            out.setdefault("__first__", {})[first] = role

    for raw in text.splitlines():
        line = raw.strip()
        if not line or len(line) > 400:
            continue
        # a markdown table row: a name cell + a role cell
        if line.startswith("|") and line.count("|") >= 3:
            cells = [c.strip(" *_`") for c in line.strip("|").split("|")]
            names = [c for c in cells if NAME_RE.fullmatch(c or "") and _is_name(c)]
            roles = [c for c in cells if c and _role_ok(c) and c not in names]
            if len(names) == 1 and roles:
                add(names[0], roles[0])
            continue
        plain = re.sub(r"[*_`]", "", line)
        plain = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", plain)
        plain = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", plain)
        # "Jane Doe — Co-founder & CTO" / "Jane Doe, CEO" / "Jane Doe (Advisor)"
        for m in NAME_RE.finditer(plain):
            rest = plain[m.end():m.end() + 90]
            mm = re.match(r"\s*(?:[—–\-,|(]|\bis\b|\bas\b|\bour\b)\s*(?:the\s+|our\s+|a\s+|an\s+)?(.{2,80})", rest)
            if mm and _role_ok(mm.group(1)):
                role_m = ROLE_RE.match(mm.group(1).strip())
                tail = mm.group(1)[:role_m.end() + 40].split(")")[0].split(";")[0]
                add(m.group(1), tail)
                continue
            # "CEO: Jane Doe" / "Co-founder & CTO — Jane Doe"
            before = plain[max(0, m.start() - 70):m.start()]
            mb = re.search(r"(" + ROLE_RE.pattern[4:] + r"[^.:;|]{0,40}?)\s*[:—–-]\s*$", before, re.I)
            if mb:
                add(m.group(1), mb.group(1))
    return out


def extract_goals(text, max_items=40):
    """Goal statements: bullets under a goals-like heading (until the next heading of
    the same or higher level) and explicit "Goal: …" lines. [(heading, text)]."""
    out, seen = [], set()
    cur_level, cur_head = 0, ""
    in_fence = False
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            lvl = len(h.group(1))
            gm = GOAL_HEAD_RE.match(line)
            if gm and re.search(r"(?i)target\s+(client|customer|market|audience|segment|user|persona|account)s?", line):
                gm = None                         # "Target customers" describes a market, not a goal
            if gm:
                cur_level, cur_head = lvl, re.sub(r"[#*_`]", "", h.group(2)).strip()
            elif cur_level and lvl <= cur_level:
                cur_level, cur_head = 0, ""
            continue
        gl = GOAL_LINE_RE.match(line)
        if gl:
            item = re.sub(r"[*_`]", "", gl.group(2)).strip()
            key = item.lower()
            if key not in seen:
                seen.add(key)
                out.append((gl.group(1).title(), item))
            continue
        if cur_level:
            b = re.match(r"^\s*(?:[-*+]|\d+[.)]|- \[[ xX]\])\s+(.*)$", line)
            if b:
                item = re.sub(r"[*_`]", "", b.group(1)).strip()
                if item.endswith(":"):          # a sub-heading bullet, not a goal
                    continue
                item = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", item)
                if 8 <= len(item) <= 240 and item.lower() not in seen:
                    seen.add(item.lower())
                    out.append((cur_head, item))
        if len(out) >= max_items:
            break
    return out


LOGO_EXTS = (".svg", ".png", ".webp", ".jpg", ".jpeg")


def _stem_tokens(name):
    stem = re.sub(r"\.[a-z0-9]+$", "", name.lower())
    return [t for t in re.split(r"[^a-z0-9]+", stem) if t]


def pick_logo(rels, entity_slug, sizes=None):
    """The company's own logo among image paths, by filename. Returns a rel or None.
    Score: logo/icon/mark words, the company's own name, preferred formats; dark /
    white / mono / favicon variants and third-party names lose."""
    want = [t for t in re.split(r"[^a-z0-9]+", (entity_slug or "").lower()) if t]
    best, best_s = None, 0
    for rel in rels:
        name = rel.rsplit("/", 1)[-1]
        low = name.lower()
        if not low.endswith(LOGO_EXTS):
            continue
        toks = _stem_tokens(name)
        s = 0
        if "logo" in toks or "logotype" in toks or "wordmark" in toks:
            s += 6
        elif "icon" in toks or "mark" in toks or "brandmark" in toks:
            s += 3
        else:
            continue
        joined = "".join(toks)
        if want and ("".join(want) in joined or all(w in toks for w in want)):
            s += 8
        elif want and len([t for t in toks if t not in ("logo", "icon", "mark", "white", "dark", "black",
                                                           "light", "color", "colour", "mono", "small",
                                                           "large", "full", "square", "round", "transparent",
                                                           "v1", "v2", "v3", "2x", "3x")]) > 0:
            s -= 4          # another brand's logo ("acme-logo.png" in a vendor folder)
        if any(t in toks for t in ("white", "dark", "black", "mono", "inverse", "negative")):
            s -= 2
        if "favicon" in toks:
            s -= 2
        s += {".svg": 2, ".png": 2, ".webp": 1}.get(low[low.rfind("."):], 0)
        s -= rel.count("/") * 0.1
        if sizes and sizes.get(rel, 0) > 1_000_000:
            continue
        if s > best_s:
            best, best_s = rel, s
    return best if best_s >= 6 else None


def match_org_logo(rels, org_name):
    """A counterparty's logo by filename: the stem (minus logo words) equals the org
    name or its first word ("mastercard.svg" → "Mastercard MDES")."""
    org_toks = [t for t in re.split(r"[^a-z0-9]+", org_name.lower()) if t]
    if not org_toks:
        return None
    full = "".join(org_toks)
    for rel in sorted(rels, key=lambda r: (r.count("/"), r)):
        name = rel.rsplit("/", 1)[-1]
        if not name.lower().endswith(LOGO_EXTS):
            continue
        toks = [t for t in _stem_tokens(name) if t not in ("logo", "icon", "mark", "svg", "png")]
        j = "".join(toks)
        if j and (j == full or (len(org_toks) > 1 and j == org_toks[0] and len(j) >= 5)):
            return rel
    return None
