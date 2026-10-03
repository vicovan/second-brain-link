#!/usr/bin/env python3
"""
doctax.py — the document taxonomy: where each document's note lives, what kind of
document it is, which counterparty it is about, and how versions / renders /
duplicates group together. Inferred from PATH SEGMENTS and FILENAME TOKENS only —
never from content — so it is the same for a clean document and a sensitive stub.

Rules: engine/mappings/docs/taxonomy.json (generic, company-agnostic) + optional
per-company overrides (prepended, so they win) in the user's data dir.

Pure functions; no I/O except loading the rule files.
"""
import json
import os
import re
import unicodedata
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent
RULES_FILE = ENGINE_DIR / "mappings" / "docs" / "taxonomy.json"

_VERSION_RES = [
    (re.compile(r"(?i)[-_ .]?\(\s*(\d{1,2})\s*\)$"), "copy"),                # "Deck (1)"
    (re.compile(r"(?i)[-_ .]v(\d+(?:\.\d+)*)$"), "v"),                       # -v2, _V2.1
    (re.compile(r"(?i)[-_ .]r(\d{1,2})$"), "r"),                             # -r1
    (re.compile(r"(?i)[-_ .](final|draft|updated|original|corrected|old|new|latest|copy|revised)$"), "word"),
    (re.compile(r"(?i)[-_ .]more[-_ ]?info(?:[-_ ]?(\d+))?$"), "more-info"),
]
_DATE_RES = [
    re.compile(r"(?<!\d)(20\d{2})[-_.](0[1-9]|1[0-2])[-_.]([0-2]\d|3[01])(?!\d)"),
    re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])([0-2]\d|3[01])(?:[-_T]\d{4,6})?(?!\d)"),
]


def load_rules(extra_mapping_dirs=None, override_path=None):
    data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    overs = []
    for d in extra_mapping_dirs or ():
        p = Path(d) / "docs" / "taxonomy.json"
        if p.is_file():
            overs.append(json.loads(p.read_text(encoding="utf-8")))
    if override_path and Path(override_path).is_file():
        overs.append(json.loads(Path(override_path).read_text(encoding="utf-8")))
    data.setdefault("entities", {})
    data.setdefault("exclude", [])
    for o in overs:
        data["rules"] = list(o.get("rules", [])) + [
            r for r in data["rules"] if r.get("id") not in {x.get("id") for x in o.get("rules", [])}]
        for k in ("entities",):
            data[k] = {**data.get(k, {}), **(o.get(k) or {})}
        data["exclude"] = list(data.get("exclude", [])) + list(o.get("exclude", []))
        for k in ("categories",):
            data[k] = {**data.get(k, {}), **(o.get(k) or {})}
        for k in ("topic_tokens", "asset_dirs"):
            if o.get(k):
                data[k] = list(dict.fromkeys(list(data.get(k, [])) + list(o[k])))
    return data


# ---------------------------------------------------------------------------
# tokens / names
# ---------------------------------------------------------------------------

def ascii_fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    return s.encode("ascii", "ignore").decode("ascii")


def kebab(s):
    s = ascii_fold(s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s)
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return re.sub(r"-{2,}", "-", s)[:90] or "untitled"


def tokens(s):
    s = ascii_fold(s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    return [t for t in re.split(r"[^A-Za-z0-9&]+", s.lower()) if t]


def nice_title(stem):
    """The note title: the original stem, whitespace normalised, separators kept
    readable ("SBL-Deck-FACTS" stays as is; "Deck  (1)" → "Deck (1)")."""
    t = re.sub(r"\s+", " ", (stem or "").replace(" ", " ").replace(" ", " ")).strip()
    return t or "Untitled"


def stem_of(name):
    """Filename without extension; `X.docx.md` → `X`."""
    low = name.lower()
    m = re.search(r"\.(docx|xlsx|pptx|pdf|doc|xls|ppt|html?)\.(md|txt)$", low)
    if m:
        return name[: -len(m.group(0))]
    return os.path.splitext(name)[0]


def entity_name(raw, rules):
    """Canonical counterparty name from a raw token string ("northwind-data" →
    "Northwind Data"), via per-company aliases first."""
    raw = (raw or "").strip(" -_.")
    if not raw:
        return ""
    aliases = rules.get("entities") or {}
    for key in (raw, raw.lower(), kebab(raw)):
        if key in aliases:
            a = aliases[key]
            # an alias with an empty name means "this token is not an entity"
            # (e.g. the company's own name prefixing its internal documents)
            nm = (a.get("name") if isinstance(a, dict) else a) or ""
            return str(nm)
    # an alias that is a whole-token PREFIX of the raw name wins too
    # ("Northwind-DCS" → the "Northwind" alias; "Initech-Airline" → "Initech" = not an entity)
    kr = kebab(raw)
    for key in sorted(aliases, key=len, reverse=True):
        kk = kebab(key)
        if kk and kr.startswith(kk + "-"):
            a = aliases[key]
            return str((a.get("name") if isinstance(a, dict) else a) or "")
    toks = [t for t in re.split(r"[-_ ]+", ascii_fold(raw)) if t]
    if not toks:
        return ""
    if kebab(raw) in set(rules.get("topic_tokens", [])):
        return ""
    words = []
    for t in toks:
        words.append(t if (t.isupper() and len(t) <= 4) or any(c.isupper() for c in t[1:]) else t.capitalize())
    return " ".join(words)


def entity_kind_override(name, rules):
    aliases = rules.get("entities") or {}
    for v in aliases.values():
        if isinstance(v, dict) and v.get("name") == name and v.get("kind"):
            return v["kind"]
    return ""


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def _seg_match(segs, when):
    lows = [s.lower() for s in segs]
    if set(lows) & {x.lower() for x in when.get("segment_any", [])}:
        return True
    for s in lows:
        if any(s.startswith(p.lower()) for p in when.get("segment_prefix_any", [])):
            return True
        if any(s.endswith(p.lower()) for p in when.get("segment_suffix_any", [])):
            return True
    return False


def _name_match(stem, when):
    toks = tokens(stem)
    keb = "-" + "-".join(toks) + "-"
    for t in when.get("name_token_any", []):
        tt = "-" + "-".join(tokens(t)) + "-"
        if tt in keb:
            return True
    for mk in when.get("name_marker_any", []):
        if mk.lower() in stem.lower():
            return True
    return False


def _entity_from(spec, rel, stem, rules):
    if not spec:
        return ""
    segs = rel.split("/")[:-1]
    if spec == "name_prefix":
        for mk in sorted(rules.get("entity_prefix_markers", []), key=len, reverse=True):
            i = stem.lower().find(mk.lower())
            if i > 0:
                return entity_name(stem[:i], rules)
        return ""
    if spec.startswith("segment_after_prefix:"):
        prefixes = spec.split(":", 1)[1].split("|")
        for s in segs:
            for p in prefixes:
                if s.lower().startswith(p) and len(s) > len(p):
                    return entity_name(s[len(p):], rules)
        return ""
    if spec.startswith("segment_after:"):
        names = spec.split(":", 1)[1].split("|")
        for i, s in enumerate(segs):
            if s.lower() in names and i + 1 < len(segs):
                return entity_name(segs[i + 1], rules)
        return ""
    return ""


def is_tax_excluded(rel, rules):
    """Per-company exclude (e.g. a folder that belongs to another entity)."""
    for x in rules.get("exclude", []):
        pat = x.get("path") or x.get("glob") or ""
        if not pat:
            continue
        pat = pat.rstrip("/")
        if rel == pat or rel.startswith(pat + "/") or Path(rel).match(pat):
            return x.get("reason") or "excluded by company rules"
    return None


def classify(rel, rules):
    """→ {category, doc_type, entity, entity_kind, authored_by, rule}."""
    segs = rel.split("/")
    name = segs[-1]
    stem = stem_of(name)
    dirsegs = segs[:-1]
    out = {"category": "inbox", "doc_type": "", "entity": "", "entity_kind": "",
           "authored_by": "internal", "rule": ""}
    # Folder signals outrank filename tokens: pass 1 matches rules on the path's
    # folder segments only; pass 2 (nothing matched) on the filename tokens.
    # Pass 3 (rules marked "fallback") applies only when nothing else matched.
    matched = None
    main = [r for r in rules.get("rules", []) if not r.get("fallback")]
    fall = [r for r in rules.get("rules", []) if r.get("fallback")]
    for r in main:
        w = r.get("when") or {}
        if any(k.startswith("segment") for k in w) and _seg_match(dirsegs, w):
            matched = r
            break
    if matched is None:
        for r in main:
            w = r.get("when") or {}
            if any(k.startswith("name") for k in w) and _name_match(stem, w):
                matched = r
                break
    if matched is None:
        for r in fall:
            w = r.get("when") or {}
            if (any(k.startswith("segment") for k in w) and _seg_match(dirsegs, w)) or \
                    (any(k.startswith("name") for k in w) and _name_match(stem, w)):
                matched = r
                break
    for r in ([matched] if matched else []):
        out["category"] = r.get("category", "inbox")
        out["rule"] = r.get("id", "")
        if r.get("doc_type"):
            out["doc_type"] = r["doc_type"]
        if r.get("authored_by"):
            out["authored_by"] = r["authored_by"]
        ent = entity_name(r["entity"], rules) if r.get("entity") else \
            _entity_from(r.get("entity_from"), rel, stem, rules)
        if ent:
            out["entity"] = ent
            out["entity_kind"] = entity_kind_override(ent, rules) or r.get("entity_kind", "counterparty")
        break
    if not out["entity"]:
        # a filename that STARTS with a known alias is about that entity anywhere
        aliases = rules.get("entities") or {}
        low = kebab(stem)
        for key, val in sorted(aliases.items(), key=lambda kv: -len(kv[0])):
            k = kebab(key)
            if k and (low == k or low.startswith(k + "-")):
                nm = (val.get("name") if isinstance(val, dict) else val) or ""
                if not nm:
                    break
                out["entity"] = nm
                out["entity_kind"] = (val.get("kind") if isinstance(val, dict) else "") or "counterparty"
                break
    if not out["doc_type"]:
        out["doc_type"] = doc_type(name, dirsegs, rules)
    return out


def doc_type(name, dirsegs, rules):
    dt = rules.get("doc_types", {})
    low = name.lower()
    ext = os.path.splitext(low)[1]
    stem = stem_of(name)
    toks = "-" + "-".join(tokens(stem)) + "-"
    for r in dt.get("by_token", []):
        if any(("-" + "-".join(tokens(t)) + "-") in toks for t in r["tokens"]):
            # binary media never become e.g. a "runbook" by name alone
            if dt.get("by_ext", {}).get(ext) in ("image", "video", "audio", "font", "archive", "code", "config"):
                break
            return r["doc_type"]
    for r in dt.get("by_segment", []):
        if {s.lower() for s in dirsegs} & set(r["segments"]):
            return r["doc_type"]
    if ext in dt.get("by_ext", {}):
        return dt["by_ext"][ext]
    return dt.get("default", "document")


def is_asset_path(rel, rules):
    segs = [s.lower() for s in rel.split("/")[:-1]]
    return bool(set(segs) & {a.lower() for a in rules.get("asset_dirs", [])})


# ---------------------------------------------------------------------------
# versions / dates
# ---------------------------------------------------------------------------

def version_info(stem, dirsegs, rules):
    """(version_key, version_label, rank_tuple). version_key strips version and
    date tokens so variants of one document group together."""
    s = nice_title(stem)
    label, num, hint = "", None, ""
    changed = True
    while changed:
        changed = False
        for rx, kind in _VERSION_RES:
            m = rx.search(s)
            if m:
                tok = m.group(1) or ""
                if kind == "v":
                    try:
                        num = float(tok.split(".")[0] + "." + "".join(tok.split(".")[1:]) if "." in tok else tok)
                    except ValueError:
                        num = None
                    label = label or f"v{tok}"
                elif kind == "r":
                    label = label or f"r{tok}"
                    num = num if num is not None else float(tok)
                elif kind == "copy":
                    label = label or f"copy {tok}"
                elif kind == "more-info":
                    label = label or f"more-info {tok}".strip()
                    num = num if num is not None else float(tok or 1)
                else:
                    hint = hint or tok.lower()
                    label = label or tok.lower()
                s = s[: m.start()]
                changed = True
                break
    date = date_in_name(s)
    key_base = s
    for rx in _DATE_RES:
        key_base = rx.sub("", key_base)
    key = kebab(key_base) or kebab(stem)
    seg_hint = ""
    ranks = rules.get("version_hint_rank", {})
    for sgm in reversed([x.lower() for x in dirsegs]):
        if re.fullmatch(r"v\d+", sgm) or sgm in ranks:
            seg_hint = sgm
            break
    hint = hint or seg_hint
    if not label and seg_hint:
        label = seg_hint
    if re.fullmatch(r"v\d+", hint or ""):
        num = num if num is not None else float(hint[1:])
        hint_rank = ranks.get("v", 2)
    else:
        hint_rank = ranks.get(hint, 2 if num is not None else 1) if hint else (2 if num is not None else 1)
    rank = (hint_rank, num if num is not None else 0.0, date or "")
    return key, label, rank


def date_in_name(s):
    for rx in _DATE_RES:
        m = rx.search(s or "")
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{y}-{mo}-{d}"
    return ""


def category_path(category, entity):
    """Folder path of a category under the docs layer, with an entity sub-folder
    for counterparty categories."""
    parts = [p for p in category.split("/") if p]
    if entity and category in ("customers", "sales/rfps", "engineering/vendors"):
        parts.append(kebab(entity))
    return "/".join(parts)
