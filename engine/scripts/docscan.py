#!/usr/bin/env python3
"""
docscan.py — the deterministic, local sensitivity scanner for document stores.

Every file a document-store source (`git_docs`, `google_drive`) walks gets exactly
ONE tier. Only `clean` (and `unverified`, a binary with no extractable text) may
carry content or a file copy into the brain; every other tier becomes a
metadata-only STUB. This is plain code: no AI, no network, nothing leaves the
machine. Reasons are rule ids only — the matched text is never stored or printed.

Tiers, in evaluation order (first decisive one wins; all reasons are kept):
    excluded        not a document (OS litter, .git internals, dependencies, bytecode)
    sensitive-path  a folder on the path is a sensitive class (secrets, env vars, pen-tests…)
    sensitive-name  the filename / extension is credential material (with false-positive guards)
    archive         zip/tar/… — entry names listed, never extracted
    encrypted       a password-protected OOXML / PDF
    too-large       bigger than the scan cap — never read, so never trusted
    secret-detected a content rule fired (gitleaks-style patterns, Luhn cards, IBANs)
    pii-dense       many distinct e-mail addresses / phone numbers (a contact list)
    cloud-only      a placeholder whose bytes are not on disk (never opened)
    unverified      a binary with no extractable text — copied, flagged; stubbed when
                    a neighbour in the same folder is flagged
    clean

Rules: engine/mappings/docs/sensitivity.json (+ per-company overrides merged by id).

CLI:
    python3 docscan.py scan <folder> [--rules overrides.json] [--json]   # metadata-only preview
    python3 docscan.py audit <brain>                                     # must report 0 hits
"""
import argparse
import fnmatch
import json
import math
import os
import re
import sys
import zipfile
import zlib
from collections import Counter
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent
RULES_FILE = ENGINE_DIR / "mappings" / "docs" / "sensitivity.json"

STUB_TIERS = {"sensitive-path", "sensitive-name", "archive", "encrypted", "too-large",
              "secret-detected", "pii-dense", "cloud-only", "neighbour-flagged"}
IMPORT_TIERS = {"clean", "unverified"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\w.])\+?\d[\d ().-]{8,}\d(?![\w.])")
DATEISH_RE = re.compile(r"^[\d\s./-]+$")


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------

_LIST_KEYS = ("exclude", "sensitive_paths", "sensitive_names", "name_allow", "content_rules")


def _merge(base, over):
    """Merge an override rules dict into `base` (by `id` for rule lists; dicts
    shallow-merged; scalars replaced). `{"id": x, "disabled": true}` removes x."""
    for k, v in (over or {}).items():
        if k.startswith("_"):
            continue
        if k in _LIST_KEYS and isinstance(v, list):
            cur = {r.get("id"): r for r in base.get(k, []) if isinstance(r, dict)}
            order = [r.get("id") for r in base.get(k, []) if isinstance(r, dict)]
            for r in v:
                if not isinstance(r, dict) or not r.get("id"):
                    continue
                if r.get("disabled"):
                    cur.pop(r["id"], None)
                    continue
                if r["id"] not in cur:
                    order.append(r["id"])
                cur[r["id"]] = r
            base[k] = [cur[i] for i in order if i in cur]
        elif isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


class Rules:
    """Compiled sensitivity rules."""

    def __init__(self, data):
        self.data = data
        self.limits = data.get("limits", {})
        self.policies = data.get("policies", {})
        self.text_exts = set(data.get("text_exts", []))
        self.ooxml_exts = set(data.get("ooxml_exts", []))
        self.pdf_exts = set(data.get("pdf_exts", []))
        self.media_exts = set(data.get("media_exts", []))
        self.archive_exts = set(data.get("archive_exts", []))
        self.content = []
        for r in data.get("content_rules", []):
            try:
                self.content.append((r, re.compile(r["regex"]),
                                     re.compile(r["line_guard"]) if r.get("line_guard") else None))
            except re.error:
                continue
        self.placeholder = re.compile(data.get("placeholder_guard") or r"^$")
        self.hash_guard = re.compile(data.get("value_hash_guard") or r"^$")
        self.entropy_guard = re.compile(data.get("entropy_guard") or r"^$")
        self.allow = [(r, re.compile(r["regex"], re.I)) for r in data.get("name_allow", [])]
        card = data.get("card_rule") or {}
        self.test_pans = set(card.get("test_pans", []))
        self.card_min = int(card.get("min_hits", 1))
        iban = data.get("iban_rule") or {}
        self.iban_re = re.compile(iban["regex"]) if iban.get("regex") else None
        pii = data.get("pii_dense") or {}
        self.pii_emails = int(pii.get("emails", 20))
        self.pii_phones = int(pii.get("phones", 10))

    @property
    def max_scan_bytes(self):
        return int(self.limits.get("max_scan_bytes", 20 * 1024 * 1024))


def load_rules(extra_mapping_dirs=None, override_path=None):
    """Shipped rules → each `--mappings <dir>/docs/sensitivity.json` → a link
    file's own `rules.sensitivity` (later wins, merged by id)."""
    data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    for d in extra_mapping_dirs or ():
        p = Path(d) / "docs" / "sensitivity.json"
        if p.is_file():
            _merge(data, json.loads(p.read_text(encoding="utf-8")))
    if override_path and Path(override_path).is_file():
        _merge(data, json.loads(Path(override_path).read_text(encoding="utf-8")))
    return Rules(data)


# ---------------------------------------------------------------------------
# name / path rules
# ---------------------------------------------------------------------------

def _tokens(stem):
    """Lowercase whole-word tokens of a filename stem (split on -_ . space and
    camelCase boundaries)."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", stem)
    return [t for t in re.split(r"[^A-Za-z0-9&]+", s.lower()) if t]


def _kebab(stem):
    return "-".join(_tokens(stem))


def is_excluded(entry, rules):
    """Rule id when the path is not a document at all (still a coverage row)."""
    rel = entry["rel"]
    segs = rel.split("/")
    name = entry["name"]
    ext = os.path.splitext(name)[1].lower()
    for r in rules.data.get("exclude", []):
        if name in (r.get("names") or ()):
            return r["id"]
        if set(segs[:-1]) & set(r.get("segments") or ()):
            return r["id"]
        if ext and ext in (r.get("exts") or ()):
            return r["id"]
    return None


def _allowed(rule_id, name_low, rules):
    for r, rx in rules.allow:
        if rule_id in (r.get("applies_to") or ()) and rx.search(name_low):
            return True
    return False


def path_reasons(entry, rules, dir_modes=None, root_mode=None):
    """Reasons from the folder path (segments) — sensitive-path tier."""
    reasons = []
    segs = [s.lower() for s in entry["rel"].split("/")[:-1]]
    for r in rules.data.get("sensitive_paths", []):
        hit = False
        for s in segs:
            if s in (r.get("segments") or ()):
                hit = True
            elif any(s.endswith(x) for x in (r.get("segment_suffixes") or ())):
                hit = True
            elif any(s.startswith(x) for x in (r.get("segment_prefixes") or ())):
                hit = True
            if hit:
                break
        if hit:
            reasons.append(r["id"])
    if dir_modes and root_mode is not None and not (root_mode & 0o077 == 0):
        parts = entry["rel"].split("/")[:-1]
        for i in range(1, len(parts) + 1):
            m = dir_modes.get("/".join(parts[:i]))
            if m is not None and (m & 0o077) == 0:
                reasons.append("mode-private")
                break
    return reasons


def name_reasons(entry, rules):
    """Reasons from the filename / extension — sensitive-name tier."""
    name = entry["name"]
    low = name.lower()
    stem = os.path.splitext(name)[0]
    toks = set(_tokens(stem))
    keb = _kebab(stem)
    ext = os.path.splitext(low)[1]
    reasons = []
    for r in rules.data.get("sensitive_names", []):
        rid = r["id"]
        hit = False
        if toks & set(r.get("tokens") or ()):
            hit = True
        if not hit and any(p in keb for p in (r.get("phrases") or ())):
            hit = True
        if not hit and any(low.startswith(p) for p in (r.get("prefixes") or ())):
            hit = True
        if not hit and ext and ext in (r.get("exts") or ()):
            hit = True
        if not hit and any(fnmatch.fnmatch(low, g) for g in (r.get("globs") or ())):
            hit = True
        # an image / diagram called "…token…" is a picture of a flow, not a credential
        # (an SVG's text is still content-scanned for real secrets)
        if hit and rid == "name-token" and ext in (".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"):
            hit = False
        if hit and not _allowed(rid, keb.replace("-", "-") + " " + low, rules):
            reasons.append(rid)
    return reasons


# ---------------------------------------------------------------------------
# text extraction (stdlib only)
# ---------------------------------------------------------------------------

_XML_TEXT_RE = re.compile(rb">([^<]{1,4000})<")
_OOXML_PARTS = re.compile(
    r"^(word/(document|comments|footnotes|endnotes|header\d*|footer\d*)\.xml|"
    r"xl/sharedStrings\.xml|xl/worksheets/sheet\d+\.xml|"
    r"ppt/slides/slide\d+\.xml|ppt/notesSlides/notesSlide\d+\.xml|"
    r"docProps/core\.xml|docProps/custom\.xml)$")


def _xml_text(raw):
    import html
    out = []
    for m in _XML_TEXT_RE.finditer(raw):
        t = m.group(1).decode("utf-8", "replace").strip()
        if t:
            out.append(html.unescape(t))
    return " ".join(out)


def extract_ooxml(data, cap):
    """(text, method, encrypted, meta) from a .docx/.xlsx/.pptx byte string.
    meta = {"title", "creator"} from docProps/core.xml (names only)."""
    import io
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":       # OLE container = encrypted OOXML
        return "", "ooxml", True, {}
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return "", "ooxml-unreadable", False, {}
    parts, total, meta = [], 0, {}
    for info in z.infolist():
        if not _OOXML_PARTS.match(info.filename):
            continue
        if info.file_size > cap:
            continue
        try:
            raw = z.read(info)
        except Exception:
            continue
        if info.filename == "docProps/core.xml":
            for tag in ("title", "creator"):
                m = re.search(rb"<(?:dc:)?" + tag.encode() + rb"[^>]*>([^<]{1,300})<", raw)
                if m:
                    meta[tag] = m.group(1).decode("utf-8", "replace").strip()
        txt = _xml_text(raw)
        # formulas/inline values in sheets carry raw text too
        parts.append(txt)
        total += len(txt)
        if total > cap:
            break
    return "\n".join(parts), "ooxml", False, meta


_PDF_STREAM_RE = re.compile(rb"stream\r?\n")
_PDF_TJ_RE = re.compile(rb"\((?:\\.|[^\\)]){0,2000}\)\s*Tj|\[[^\]]{0,4000}\]\s*TJ|<[0-9A-Fa-f\s]{1,4000}>\s*Tj")
_PDF_STR_RE = re.compile(rb"\((?:\\.|[^\\)]){0,2000}\)")
_PDF_MAX_STREAM = 4 * 1024 * 1024      # never inflate more than this per stream


def _pdf_unescape(b):
    b = b[1:-1]
    b = re.sub(rb"\\([nrtbf()\\])", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t",
                                               b"b": b"", b"f": b"", b"(": b"(", b")": b")",
                                               b"\\": b"\\"}[m.group(1)], b)
    b = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), b)
    return b.decode("latin-1", "replace")


def extract_pdf(data, cap):
    """Best-effort PDF text with the stdlib: inflate FlateDecode content streams
    (bounded; image streams skipped) and pull text-showing operators.
    Returns (text, method, encrypted). Linear time — every pattern is bounded."""
    encrypted = b"/Encrypt" in data[:4096] or b"/Encrypt" in data[-8192:]
    out, total = [], 0
    pos = 0
    n = len(data)
    while pos < n and total <= cap:
        m = _PDF_STREAM_RE.search(data, pos)
        if not m:
            break
        start = m.end()
        end = data.find(b"endstream", start)
        if end == -1:
            break
        pos = end + 9
        head = data[max(0, m.start() - 400):m.start()]
        if b"/Image" in head or b"/XObject" in head and b"/Form" not in head:
            continue                       # image data: no text, skip the inflate
        raw = data[start:end]
        if b"/FlateDecode" in head:
            try:
                d = zlib.decompressobj()
                raw = d.decompress(raw, _PDF_MAX_STREAM)
            except Exception:
                continue
        if b"BT" not in raw and b"Tj" not in raw and b"TJ" not in raw:
            continue
        for op in _PDF_TJ_RE.finditer(raw):
            seg = op.group(0)
            if seg.startswith(b"<"):
                hx = re.sub(rb"[^0-9A-Fa-f]", b"", seg.split(b">")[0])
                try:
                    out.append(bytes.fromhex(hx.decode()).decode("latin-1", "replace"))
                except Exception:
                    pass
            else:
                out.extend(_pdf_unescape(x) for x in _PDF_STR_RE.findall(seg))
            total += len(seg)
    # metadata dictionary strings too (/Title, /Author …)
    for x in re.findall(rb"/(?:Title|Author|Subject|Keywords)\s*(\((?:\\.|[^\\)]){0,500}\))", data[:65536]):
        out.append(_pdf_unescape(x))
    return " ".join(out), "pdf-partial", encrypted


def decode_text(data):
    for enc in ("utf-8", "utf-16"):
        try:
            if enc == "utf-16" and not data[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", "replace")


def extract_text(data, ext, rules, inner_ext=""):
    """(text, method, encrypted, meta) for a file's bytes, or ("", "none", False, {})."""
    cap = rules.max_scan_bytes
    if ext in rules.text_exts:
        return decode_text(data[:cap]), "text", False, {}
    if ext in rules.ooxml_exts:
        t, m, enc, meta = extract_ooxml(data, cap)
        return t, m, enc, meta
    if ext in rules.pdf_exts:
        t, m, enc = extract_pdf(data, cap)
        return t, m, enc, {}
    return "", "none", False, {}


# ---------------------------------------------------------------------------
# content rules
# ---------------------------------------------------------------------------

def _entropy(s):
    if not s:
        return 0.0
    c = Counter(s)
    n = len(s)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def _luhn(digits):
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_CARD_RE = re.compile(r"(?<![\d.-])[3-6](?:[ -]?\d){12,18}(?![\d-])")


def _card_hits(text, rules):
    n = 0
    for m in _CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if not 13 <= len(digits) <= 19 or digits in rules.test_pans:
            continue
        if len(set(digits)) <= 2:
            continue
        if re.search(r"(\d)\1{5,}", digits):        # 6+ identical digits in a row = a test card
            continue
        if _luhn([int(c) for c in digits]):
            n += 1
    return n


def content_reasons(text, rules):
    """Rule ids (with counts) whose patterns hit `text`. Never returns matches."""
    hits = Counter()
    if not text:
        return hits
    lines_cache = None
    for r, rx, line_guard in rules.content:
        vg = r.get("value_group")
        n = 0
        for m in rx.finditer(text):
            if vg or r.get("value_guard"):
                val = (m.group(vg) if vg else m.group(0).split("=", 1)[-1]).strip().strip("\"'")
                if rules.placeholder.match(val) or rules.hash_guard.match(val.lower()):
                    continue
                if r.get("value_guard") and (val.startswith("$") or val.startswith("<")
                                             or val.lower() in ("true", "false", "none", "null")):
                    continue
                if r.get("min_entropy"):
                    if rules.entropy_guard.search(val) or _entropy(val) < float(r["min_entropy"]):
                        continue
                if r["id"] == "generic-assignment":
                    # a value that is clearly prose / a type / a code reference, not a secret
                    # (`user.password_hash`, `req.body.token`, `PASSWORD_FIELD`, `string`)
                    if re.fullmatch(r"[A-Za-z_][A-Za-z_]*(?:\.[A-Za-z_][A-Za-z_0-9]*)+(?:\(\))?", val) \
                            or re.fullmatch(r"[a-z]+(?:_[a-z]+)+", val):
                        continue
                    if (len(set(val)) < 5 or re.fullmatch(r"[a-z]+", val)
                            or re.fullmatch(r"[A-Z_]+", val)
                            or re.fullmatch(r"[a-zA-Z]+\(.*", val)
                            or val.lower().startswith(("http://", "https://"))):
                        continue
            if line_guard is not None:
                s = text.rfind("\n", 0, m.start()) + 1
                e = text.find("\n", m.end())
                line = text[s:e if e != -1 else len(text)]
                if line_guard.search(line):
                    continue
            n += 1
        if n >= int(r.get("min_hits", 1)):
            hits[r["id"]] += n
    c = _card_hits(text, rules)
    if c >= rules.card_min:
        hits["card-luhn"] += c
    if rules.iban_re is not None:
        ib = [m for m in rules.iban_re.finditer(text) if _iban_ok(m.group(0))]
        if ib:
            hits["iban"] += len(ib)
    return hits


def _iban_ok(s):
    s = re.sub(r"\s", "", s).upper()
    if not 15 <= len(s) <= 34:
        return False
    r = s[4:] + s[:4]
    try:
        return int("".join(str(int(ch, 36)) for ch in r)) % 97 == 1
    except ValueError:
        return False


def pii_counts(text):
    emails = {m.group(0).lower() for m in EMAIL_RE.finditer(text or "")}
    phones = set()
    for m in PHONE_RE.finditer(text or ""):
        s = m.group(0)
        d = re.sub(r"\D", "", s)
        if len(d) < 9 or len(d) > 15:
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:\s*[-–]\s*\d{4}-\d{2}-\d{2})?", s.strip()):
            continue
        # number LISTS (SVG paths, coordinates, table rows) are not phones: a phone's
        # digit groups have 2+ digits (bar a "+1" country code) and there are <= 5
        groups = re.findall(r"\d+", s)
        tail = groups[1:] if s.lstrip().startswith("+") else groups
        if any(len(g) < 2 for g in tail) or len(groups) > 5 or "." in s:
            continue
        phones.add(d)
    return len(emails), len(phones)


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def archive_listing(data, ext, cap=200):
    """Entry names of a zip (never extracted); [] for other archive kinds."""
    import io
    if ext != ".zip" and data[:4] != b"PK\x03\x04":
        return []
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        return [i.filename for i in z.infolist()][:cap]
    except Exception:
        return []


def classify(entry, data, rules, dir_modes=None, root_mode=None):
    """Classify one walked file. `data` = its bytes (None when not read: cloud-only,
    symlink, too large). Returns a verdict dict:
      {tier, reasons[], scan_method, scan_chars, text, meta, archive_entries}
    `text` is returned to the caller ONLY so a clean document's body can become
    its note; it must be discarded for every non-clean tier (the Collector
    enforces that again)."""
    v = {"tier": "clean", "reasons": [], "scan_method": "none", "scan_chars": 0,
         "text": "", "meta": {}, "archive_entries": []}
    ext = entry["ext"]
    inner = entry.get("inner_ext") or ""
    pr = path_reasons(entry, rules, dir_modes, root_mode)
    nr = name_reasons(entry, rules)
    decisive = [r for r in pr if r != "mode-private"]
    v["reasons"] = pr + nr
    if decisive:
        v["tier"] = "sensitive-path"
    elif nr:
        v["tier"] = "sensitive-name"
    if entry.get("cloud_only"):
        if v["tier"] == "clean":
            v["tier"] = "cloud-only"
        v["reasons"].append("cloud-only-placeholder")
        return v
    if data is None:
        if v["tier"] == "clean":
            v["tier"] = "too-large"
            v["reasons"].append("too-large-to-scan")
        return v
    if ext in rules.archive_exts:
        v["archive_entries"] = archive_listing(data, ext, int(rules.limits.get("archive_list_cap", 200)))
        bad = [n for n in v["archive_entries"]
               if name_reasons({"name": n.rsplit("/", 1)[-1], "rel": n, "ext": os.path.splitext(n)[1].lower()}, rules)]
        if bad:
            v["reasons"].append("archive-sensitive-entry")
        if v["tier"] == "clean":
            v["tier"] = "archive"
        v["reasons"].append("archive-not-extracted")
        return v
    text, method, encrypted, meta = extract_text(data, ext, rules, inner)
    v["scan_method"], v["meta"] = method, meta
    v["scan_chars"] = len(text)
    if encrypted:
        if v["tier"] == "clean":
            v["tier"] = "encrypted"
        v["reasons"].append("encrypted")
        return v
    hits = content_reasons(text, rules)
    if hits:
        v["reasons"].extend(f"{k}×{n}" for k, n in sorted(hits.items()))
        if v["tier"] == "clean":
            v["tier"] = "secret-detected"
    ne, np_ = pii_counts(text)
    if ne >= rules.pii_emails or np_ >= rules.pii_phones:
        v["reasons"].append(f"pii-dense(e{ne},p{np_})")
        if v["tier"] == "clean":
            v["tier"] = "pii-dense"
    if v["tier"] == "clean":
        if ext in rules.media_exts:
            v["scan_method"] = "none"
        elif method == "pdf-partial" and len(text.strip()) < int(rules.policies.get("pdf_min_chars", 200)):
            v["tier"] = "unverified"
            v["reasons"].append("pdf-text-not-extractable")
        elif method in ("none", "ooxml-unreadable") and ext not in rules.media_exts:
            v["tier"] = "unverified"
            v["reasons"].append("binary-not-scannable")
        v["text"] = text
    return v


def apply_neighbour_policy(verdicts, rules, clean_siblings=None):
    """`unverified` files in a folder that also holds a flagged file are stubbed
    (policy `neighbour_flagged: stub`); a partial PDF with a clean same-stem
    sibling (its md/docx source) is trusted. `verdicts` = {rel: verdict}."""
    flagged_dirs = {rel.rsplit("/", 1)[0] if "/" in rel else ""
                    for rel, v in verdicts.items() if v["tier"] in STUB_TIERS - {"cloud-only", "too-large"}}
    pol = rules.policies.get("neighbour_flagged", "stub")
    unscan = rules.policies.get("unscannable", "copy-unverified")
    for rel, v in verdicts.items():
        if v["tier"] != "unverified":
            continue
        if clean_siblings and rel in clean_siblings and "pdf-text-not-extractable" in v["reasons"]:
            v["tier"] = "clean"
            v["reasons"].append("trusted-via-clean-source")
            continue
        d = rel.rsplit("/", 1)[0] if "/" in rel else ""
        if unscan == "stub" or (pol == "stub" and d in flagged_dirs):
            v["tier"] = "neighbour-flagged" if d in flagged_dirs else "unverified-stubbed"
            v["reasons"].append("neighbour-flagged" if d in flagged_dirs else "policy-unscannable-stub")
    return verdicts


def is_importable(tier):
    return tier in IMPORT_TIERS


# ---------------------------------------------------------------------------
# CLIs
# ---------------------------------------------------------------------------

def scan_folder(root, rules, link=None):
    """Classify every file under `root` (read-only). Yields (entry, verdict)."""
    import doclink
    lk = link or {"root_path": Path(root).resolve(), "include": ["**"], "exclude": []}
    modes = doclink.dir_modes(lk["root_path"])
    root_mode = modes.get(".", modes.get("", 0o755))
    out = {}
    entries = {}
    for e in doclink.walk(lk):
        if e.get("is_dir"):
            continue
        entries[e["rel"]] = e
        ex = is_excluded(e, rules)
        if ex or e["user_excluded"] or e["is_symlink"]:
            out[e["rel"]] = {"tier": "excluded", "reasons": [ex or ("symlink" if e["is_symlink"] else "user-exclude")],
                             "scan_method": "none", "scan_chars": 0, "text": "", "meta": {}, "archive_entries": []}
            continue
        data = None
        if not e["cloud_only"] and e["size"] <= rules.max_scan_bytes:
            data = doclink.read_bytes(e["abspath"], lk["root_path"])
        out[e["rel"]] = classify(e, data, rules, modes, root_mode)
    apply_neighbour_policy(out, rules)
    for rel in sorted(out):
        yield entries[rel], out[rel]


def audit(vault, rules=None):
    """Re-run the CONTENT rules over a generated brain. Every hit is a leak.
    Returns a list of (relpath, [rule ids])."""
    rules = rules or load_rules()
    hits = []
    vault = Path(vault)
    for p in sorted(vault.rglob("*")):
        if not p.is_file() or ".obsidian" in p.parts or p.name == "_GENERATED.json":
            continue
        ext = p.suffix.lower()
        try:
            data = p.read_bytes()
        except Exception:
            continue
        if len(data) > rules.max_scan_bytes:
            continue
        text, method, enc, _ = extract_text(data, ext if ext else ".txt", rules)
        if not text and ext in (".md", ".json", ".txt", ""):
            text = decode_text(data)
        rs = content_reasons(text, rules)
        if rs:
            hits.append((str(p.relative_to(vault)), sorted(rs)))
    return hits


def _cmd_scan(args):
    rules = load_rules(override_path=args.rules)
    tiers = Counter()
    rows = []
    for e, v in scan_folder(args.folder, rules):
        tiers[v["tier"]] += 1
        rows.append({"path": e["rel"], "tier": v["tier"], "reasons": v["reasons"],
                     "scan": v["scan_method"], "size": e["size"]})
    if args.json:
        print(json.dumps({"tiers": dict(tiers), "files": rows}, indent=1))
    else:
        for r in rows:
            if args.all or r["tier"] not in ("clean",):
                print(f"{r['tier']:<18} {r['path']}  [{', '.join(r['reasons'])}]")
        print("\n" + " · ".join(f"{k}: {n}" for k, n in tiers.most_common()))
    return 0


def _cmd_audit(args):
    hits = audit(args.brain)
    for rel, rs in hits:
        print(f"LEAK? {rel}  [{', '.join(rs)}]")
    print(f"audit: {len(hits)} file(s) with secret-pattern hits")
    return 1 if hits else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic local sensitivity scanner (no AI, no network).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="metadata-only preview of how a folder would be tiered")
    s.add_argument("folder")
    s.add_argument("--rules", default=None, help="per-company override rules JSON")
    s.add_argument("--json", action="store_true")
    s.add_argument("--all", action="store_true", help="also list clean files")
    a = sub.add_parser("audit", help="scan a generated brain for secret patterns (must be 0)")
    a.add_argument("brain")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return {"scan": _cmd_scan, "audit": _cmd_audit}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
