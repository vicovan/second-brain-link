#!/usr/bin/env python3
"""
check_pdf.py — see the CV the way an ATS sees it, and grade it.

Usage:
    python3 check_pdf.py CV.pdf --keywords "Kubernetes;Terraform;distributed systems"
                        [--title "VP Engineering"] [--max-pages 2] [--show] [--png DIR]

Checks: page count, text extractability, reading order of the contact block,
keyword coverage (case-insensitive, counts), target-title presence, stray
replacement characters (font problems), phone/email in the first 300 chars, and — with
PyMuPDF — orphaned bullet lines: a wrapped bullet whose second half fell back to the left
margin, which reads to a human as a broken document. `--png DIR` renders each page so the
layout can be looked at, not only parsed.
Exit code 1 if any hard check fails.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from pyenv import require as _require   # may re-exec this process
except ImportError:
    def _require(_m, _p=""):
        return False

import argparse, re, shutil, subprocess, sys

def extract(pdf):
    if shutil.which("pdftotext"):
        return subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True).stdout
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(pdf).pages)
    except ImportError:
        pass
    try:
        import fitz
        return "\n".join(p.get_text() for p in fitz.open(pdf))
    except ImportError:
        (_require("pypdf", "pypdf") or sys.exit(
        "Need pdftotext (poppler) or pypdf.\n"
        "  interpreter: %s\n"
        "  fix: %s -m pip install pypdf   (or: brew install poppler)" % (sys.executable, sys.executable)))

def pages(pdf):
    try:
        from pypdf import PdfReader
        return len(PdfReader(pdf).pages)
    except ImportError:
        if shutil.which("pdfinfo"):
            out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
            m = re.search(r"Pages:\s+(\d+)", out)
            return int(m.group(1)) if m else -1
    return -1

def orphans(pdf):
    """Lines that start lower-case at the left margin straight after an indented (bullet) line.
    A wrapped bullet keeps its hanging indent; a line that loses it was split off the bullet.
    Returns None when PyMuPDF is not installed."""
    try:
        import fitz
    except ImportError:
        return None
    out = []
    for pno, page in enumerate(fitz.open(pdf), 1):
        lines = []
        for blk in page.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                t = "".join(sp["text"] for sp in ln["spans"]).strip()
                if t:
                    lines.append((round(ln["bbox"][1], 1), ln["bbox"][0], t))
        lines.sort()
        if not lines:
            continue
        margin = min(x for _, x, _ in lines)
        prev = None
        for y, x, t in lines:
            at_margin = x - margin < 3
            # the previous line is part of a bullet: it opens with the glyph, or it sits at the
            # bullet's hanging indent (a skills-table value column sits much further right)
            in_bullet = prev and (prev[2][:1] in "•–-" or 5 < prev[1] - margin < 25)
            if in_bullet and at_margin and t[0].islower():
                out.append(f"p{pno}: {t[:60]!r}")
            prev = (y, x, t)
    return out

def render_png(pdf, outdir, dpi=80):
    try:
        import fitz
    except ImportError:
        return []
    os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(pdf))[0]
    paths = []
    for i, page in enumerate(fitz.open(pdf), 1):
        p = os.path.join(outdir, f"{base}-p{i}.png")
        page.get_pixmap(dpi=dpi).save(p)
        paths.append(p)
    return paths

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--keywords", default="", help="';'-separated must-have keywords")
    ap.add_argument("--nice", default="", help="';'-separated nice-to-have keywords")
    ap.add_argument("--title", default="", help="target job title that must appear")
    ap.add_argument("--name", help="the candidate name that must appear at the top")
    ap.add_argument("--max-pages", type=int, default=2)
    ap.add_argument("--show", action="store_true", help="print extracted text")
    ap.add_argument("--text", action="store_true",
                    help="print only the extracted text (what a screener receives) and exit")
    ap.add_argument("--png", metavar="DIR", help="render each page to DIR as PNG (needs PyMuPDF)")
    a = ap.parse_args()

    txt = extract(a.pdf)
    if a.text:
        print(txt)
        sys.exit(0)
    low = txt.lower()
    fails, warns = [], []

    n = pages(a.pdf)
    print(f"pages: {n}")
    if n > a.max_pages: fails.append(f"{n} pages > {a.max_pages}")

    head = txt[:300]
    if not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", head): fails.append("email not in first 300 chars")
    if not re.search(r"\+\d[\d\s]{7,}", head): fails.append("phone not in first 300 chars")
    if a.name and a.name.lower() not in low[:120]:
        fails.append(f"name {a.name!r} not at top")

    if "\ufffd" in txt or "?" in re.sub(r"[^\w?]", "", txt[:200]):
        fails.append("replacement characters found — font/diacritics problem")
    if len(txt.strip()) < 1500: fails.append("very little extractable text — is it an image?")

    if a.title and a.title.lower() not in low:
        fails.append(f"target title not found verbatim: '{a.title}'")

    def cov(kws, label, need):
        missing, weak = [], []
        for k in [k.strip() for k in kws.split(";") if k.strip()]:
            c = low.count(k.lower())
            if c == 0: missing.append(k)
            elif c < need: weak.append(f"{k}({c})")
        print(f"{label}: {len(missing)} missing, {len(weak)} below {need}x")
        if missing: print("   missing:", ", ".join(missing))
        if weak: print("   weak:   ", ", ".join(weak))
        return missing

    if a.keywords:
        miss = cov(a.keywords, "must-have keywords", 2)
        if miss: fails.append(f"missing must-have keywords: {', '.join(miss)}")
    if a.nice:
        cov(a.nice, "nice-to-have keywords", 1)

    if shutil.which("pdffonts"):
        f = subprocess.run(["pdffonts", a.pdf], capture_output=True, text=True).stdout
        base14 = ("Helvetica", "Times", "Courier", "Symbol", "ZapfDingbats")
        for line in f.splitlines()[2:]:
            if re.search(r"\bno\b", line) and not line.startswith(base14):
                warns.append(f"font not embedded: {line.split()[0]}")

    orph = orphans(a.pdf)
    if orph is None:
        warns.append("PyMuPDF not installed — orphaned-bullet check skipped (pip install pymupdf)")
    elif orph:
        fails.append(f"{len(orph)} bullet line(s) broke off to the left margin: " + "; ".join(orph[:3]))
    if a.png:
        imgs = render_png(a.pdf, a.png)
        print("page images: " + (", ".join(imgs) if imgs else "none (needs PyMuPDF)"))

    if a.show:
        print("\n----- extracted text -----\n" + txt)

    for w in warns: print("WARN:", w)
    for f in fails: print("FAIL:", f)
    print("RESULT:", "PASS" if not fails else "FAIL")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
