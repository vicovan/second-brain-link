#!/usr/bin/env python3
"""
build_cv.py — render a CV content JSON into an ATS-safe PDF (and optionally DOCX).

Usage:
    python3 build_cv.py cv.md [--out DIR] [--max-pages 2] [--docx]

Takes the CV Markdown the model wrote (a .json content file is still accepted). Requires
reportlab (pip install reportlab); DOCX export additionally needs python-docx — optional.

The Markdown format is documented in ../SKILL.md ("The CV Markdown format"). Inline markup
in any text field:  **bold**   [link text](https://url)
The builder auto-shrinks type/spacing in small steps until the document fits
--max-pages (default 2), so write the content, not the layout.
"""
import argparse, json, os, re, sys, glob, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from pyenv import require as _require   # may re-exec this process
except ImportError:
    def _require(_m, _p=""):
        return False

# Studio inherits launchd's PATH, so `python3` there is often the system 3.9 with no
# reportlab. Look for one that has it and re-exec, rather than silently producing no PDF.
_require("reportlab", "reportlab")

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, HRFlowable, KeepTogether)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAVE_REPORTLAB = True
except ImportError:
    # Degrade, do not crash. The Markdown CV is the real artifact; the PDF is a
    # rendering of it. A missing optional dependency must not lose the user's work.
    HAVE_REPORTLAB = False

# Palette — deliberately restrained. A CV that shouts colour reads as generated;
# ink, one grey and a hairline read as designed. The only saturated thing is a link.
# Defined only when reportlab is available - without it nothing below is reached,
# and importing this module must still succeed so `--help` and the notice work.
if HAVE_REPORTLAB:
    INK = colors.HexColor("#14171C")     # body text and role titles
    BLUE = colors.HexColor("#1F4E8C")    # section headings, headline, links - deep, not web-blue
    MUTED = colors.HexColor("#5C636D")   # dates, context lines, bullet glyphs
    RULE = colors.HexColor("#C3D0E0")    # hairlines, tinted to match the blue
    LINK = BLUE
    DARK, GREY, ACCENT = INK, MUTED, BLUE  # back-compat aliases

# ---------------------------------------------------------------- fonts
FONT_CANDIDATES = [
    # (regular, bold) — first pair found wins. Unicode coverage matters (Zürich, Kraków, Iaşi).
    ("Carlito-Regular.ttf", "Carlito-Bold.ttf"),
    ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
    ("Arial.ttf", "Arial Bold.ttf"),
    ("arial.ttf", "arialbd.ttf"),
    ("Helvetica.ttc", None),
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
]
FONT_DIRS = [
    "/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/Library/Fonts"), "/Library/Fonts",
    "/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
    "C:/Windows/Fonts",
]

def _find(name):
    for d in FONT_DIRS:
        if not os.path.isdir(d):
            continue
        hits = glob.glob(os.path.join(d, "**", name), recursive=True)
        if hits:
            return hits[0]
    return None

def register_fonts():
    for reg, bold in FONT_CANDIDATES:
        r = _find(reg)
        b = _find(bold) if bold else None
        if r and (b or not bold):
            try:
                pdfmetrics.registerFont(TTFont("CV", r))
                pdfmetrics.registerFont(TTFont("CV-Bold", b or r))
                pdfmetrics.registerFontFamily("CV", normal="CV", bold="CV-Bold",
                                              italic="CV", boldItalic="CV-Bold")
                return "CV", "CV-Bold", os.path.basename(r)
            except Exception:
                continue
    # Fallback: built-in Helvetica (WinAnsi only — diacritics will be replaced)
    return "Helvetica", "Helvetica-Bold", "Helvetica(builtin)"

# ---------------------------------------------------------------- markup
_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}

def md(text, unicode_ok=True):
    """Convert **bold** and [text](url) to reportlab paragraph markup."""
    if not unicode_ok:
        text = (text.replace("ș", "s").replace("Ș", "S").replace("ț", "t")
                    .replace("Ț", "T").replace("ă", "a").replace("â", "a").replace("î", "i"))
    out, i = [], 0
    # protect links first
    parts = re.split(r"(\[[^\]]+\]\([^)]+\))", text)
    for p in parts:
        m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", p)
        if m:
            label = "".join(_ESC.get(c, c) for c in m.group(1))
            url = m.group(2)
            out.append(f'<link href="{url}" color="#1F4E8C"><u>{label}</u></link>')
        else:
            s = "".join(_ESC.get(c, c) for c in p)
            s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
            s = re.sub(r"\*([^*\n]+?)\*", r"<i>\1</i>", s)   # *emphasis* -> italic
            out.append(s)
    return "".join(out)

# ---------------------------------------------------------------- build
def build(content, out_pdf, scale=1.0, font=("Helvetica", "Helvetica-Bold"), unicode_ok=True):
    REG, BOLD = font
    base = 9.8 * scale
    lead = base * 1.38          # airier than the usual template — a page that breathes
    styles = {
        "name": ParagraphStyle("name", fontName=BOLD, fontSize=21 * scale, leading=24 * scale,
                               textColor=INK, spaceAfter=2 * scale),
        "headline": ParagraphStyle("headline", fontName=REG, fontSize=10.6 * scale,
                                   leading=13.4 * scale, textColor=BLUE, spaceAfter=4 * scale),
        "contact": ParagraphStyle("contact", fontName=REG, fontSize=base * 0.97, leading=lead,
                                  textColor=INK),
        "status": ParagraphStyle("status", fontName=REG, fontSize=base * 0.93, leading=lead * 0.95,
                                 textColor=MUTED),
        "h": ParagraphStyle("h", fontName=BOLD, fontSize=base * 0.96, leading=base * 1.25,
                            textColor=BLUE, spaceBefore=10 * scale, spaceAfter=0, keepWithNext=1),
        "sub": ParagraphStyle("sub", fontName=BOLD, fontSize=base, leading=lead, textColor=INK,
                              spaceBefore=5 * scale, spaceAfter=1, keepWithNext=1),
        "p": ParagraphStyle("p", fontName=REG, fontSize=base, leading=lead, textColor=INK,
                            spaceAfter=3.5 * scale),
        "role": ParagraphStyle("role", fontName=REG, fontSize=base * 1.06, leading=lead * 1.02,
                               textColor=INK),
        "meta": ParagraphStyle("meta", fontName=REG, fontSize=base * 0.9, leading=lead * 0.92,
                               textColor=MUTED, spaceAfter=1.5 * scale),
        "dates": ParagraphStyle("dates", fontName=REG, fontSize=base * 0.93, leading=lead * 1.05,
                                textColor=MUTED, alignment=TA_RIGHT),
        "b": ParagraphStyle("b", fontName=REG, fontSize=base, leading=lead, textColor=INK,
                            leftIndent=10, bulletIndent=0, spaceAfter=2.8 * scale,
                            bulletFontName=REG, bulletFontSize=base * 0.85, bulletColor=MUTED),
        "kvk": ParagraphStyle("kvk", fontName=BOLD, fontSize=base * 0.95, leading=lead * 0.97,
                              textColor=MUTED),
        "kvv": ParagraphStyle("kvv", fontName=REG, fontSize=base * 0.95, leading=lead * 0.97,
                              textColor=INK),
    }
    M = lambda t: md(t, unicode_ok)

    doc = SimpleDocTemplate(out_pdf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=15 * mm, bottomMargin=14 * mm,
                            title=f"{content['name']} — CV", author=content["name"],
                            subject=content.get("headline", "CV"))
    avail = doc.width          # the frame's real width, padding already subtracted
    story = []

    def bullet(b):
        txt = (f"<b>{M(b['lead'])}</b> " if b.get("lead") else "") + M(b["text"])
        return Paragraph(txt, styles["b"], bulletText="\u2013")

    # ---- header
    story.append(Paragraph(M(content["name"]), styles["name"]))
    if content.get("headline"):
        story.append(Paragraph(M(content["headline"]), styles["headline"]))
    c = content.get("contact", {})
    sep = f' <font color="#B9BEC5">|</font> '
    bits = [x for x in [c.get("email"), c.get("phone")] if x]
    bits += [f"[{l['text']}]({l['url']})" for l in c.get("links", [])]
    story.append(Paragraph(sep.join(M(b) for b in bits), styles["contact"]))
    loc_bits = [x for x in [c.get("location"), c.get("status")] if x]
    if loc_bits:
        story.append(Paragraph(sep.join(M(b) for b in loc_bits), styles["status"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE,
                            spaceBefore=6 * scale, spaceAfter=1))

    # ---- sections
    for sec in content.get("sections", []):
        if sec.get("heading"):
            story.append(Paragraph(M(sec["heading"]).upper(), styles["h"]))
            story.append(HRFlowable(width="100%", thickness=0.5, color=RULE,
                                    spaceBefore=2 * scale, spaceAfter=4.5 * scale))
        blocks = sec.get("blocks", [])
        i = 0
        while i < len(blocks):
            b = blocks[i]
            t = b.get("type", "paragraph")
            if t == "paragraph":
                story.append(Paragraph(M(b["text"]), styles["p"]))
            elif t == "subheading":
                story.append(Paragraph(M(b["text"]), styles["sub"]))
            elif t == "bullet":
                story.append(bullet(b))
            elif t == "kv":
                # Grouped skills: a labelled two-column table, never one long
                # middot-separated wall. items: [["Label", "a, b, c"], ...]
                items = b.get("items", [])
                pairs = [(x[0], x[1]) if isinstance(x, (list, tuple))
                         else (x.get("label", ""), x.get("value", "")) for x in items]
                rows = [[Paragraph(M(k), styles["kvk"]), Paragraph(M(v), styles["kvv"])]
                        for k, v in pairs]
                if rows:
                    lab = max(28, min(140, int(avail * 0.22)))
                    tbl = Table(rows, colWidths=[lab, avail - lab], hAlign="LEFT")
                    tbl.setStyle(TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (0, -1), 8),
                        ("RIGHTPADDING", (1, 0), (1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * scale),
                    ]))
                    story.append(tbl)
            elif t == "entries":
                # Tight two-column list with the date right-aligned: education, awards,
                # certifications. A run-on paragraph of four degrees separated by middots
                # is unreadable, and it is the one place a CV can look careless.
                items = b.get("items", [])
                rows = []
                for it in items:
                    l, r = (it[0], it[1]) if isinstance(it, (list, tuple)) \
                        else (it.get("left", ""), it.get("right", ""))
                    rows.append([Paragraph(M(l), styles["p"]),
                                 Paragraph(M(r), styles["dates"])])
                if rows:
                    tbl = Table(rows, colWidths=[avail - 100, 100], hAlign="LEFT")
                    tbl.setStyle(TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * scale),
                    ]))
                    story.append(tbl)
            elif t == "role":
                # Line 1 carries title + employer and the dates, and nothing else, so a
                # long employer name can never push text under the date column.
                left = f"<b>{M(b['title'])}</b>"
                if b.get("org"):
                    left += f'  <font color="#5C636D">|</font>  {M(b["org"])}'
                row = Table([[Paragraph(left, styles["role"]),
                              Paragraph(M(b.get("dates", "")), styles["dates"])]],
                            colWidths=[avail - 100, 100], hAlign="LEFT")
                row.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 5 * scale),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                # Line 2 — location, one-line company descriptor, site. Small and grey.
                meta = []
                if b.get("where"):
                    meta.append(M(b["where"]))
                if b.get("url"):
                    disp = re.sub(r"^https?://(www\.)?", "", b["url"]).rstrip("/")
                    meta.append(f'<link href="{b["url"]}" color="#1F4E8C">{disp}</link>')
                keep = [row]
                if meta:
                    keep.append(Paragraph(" · ".join(meta), styles["meta"]))
                # keep the role header with the block that follows it
                if i + 1 < len(blocks) and blocks[i + 1].get("type") in ("bullet", "paragraph"):
                    nb = blocks[i + 1]
                    keep.append(bullet(nb) if nb["type"] == "bullet"
                                else Paragraph(M(nb["text"]), styles["p"]))
                    i += 1
                story.append(KeepTogether(keep))
            elif t == "spacer":
                story.append(Spacer(1, b.get("height", 4) * scale))
            i += 1

    doc.build(story)
    return doc.page

def build_docx(content, out_docx):
    try:
        import docx  # python-docx
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        print("python-docx not installed — skipping DOCX (pip install python-docx)")
        return None
    d = docx.Document()
    for s in d.sections:
        s.left_margin = s.right_margin = docx.shared.Mm(17)
        s.top_margin = docx.shared.Mm(13); s.bottom_margin = docx.shared.Mm(12)
    st = d.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(9.5)

    def runs(par, text, bold=False):
        # strip markup for docx: keep text, drop links to plain text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        for i, seg in enumerate(re.split(r"(\*\*.+?\*\*)", text)):
            if not seg: continue
            b = seg.startswith("**")
            r = par.add_run(seg.strip("*")); r.bold = bold or b

    p = d.add_paragraph(); r = p.add_run(content["name"]); r.bold = True; r.font.size = Pt(22)
    if content.get("headline"):
        p = d.add_paragraph(); r = p.add_run(content["headline"]); r.font.size = Pt(11); r.font.color.rgb = RGBColor(0x5C, 0x63, 0x6D)
    c = content.get("contact", {})
    line = " | ".join([x for x in [c.get("email"), c.get("phone")] if x] + [l["text"] for l in c.get("links", [])])
    d.add_paragraph(line)
    d.add_paragraph(" | ".join([x for x in [c.get("location"), c.get("status")] if x]))
    for sec in content.get("sections", []):
        if sec.get("heading"):
            h = d.add_paragraph(); r = h.add_run(sec["heading"].upper()); r.bold = True; r.font.color.rgb = RGBColor(0x14, 0x17, 0x1C)
        for b in sec.get("blocks", []):
            t = b.get("type", "paragraph")
            if t == "paragraph":
                runs(d.add_paragraph(), b["text"])
            elif t == "subheading":
                runs(d.add_paragraph(), b["text"], bold=True)
            elif t == "bullet":
                p = d.add_paragraph(style="List Bullet")
                if b.get("lead"): runs(p, b["lead"] + " ", bold=True)
                runs(p, b["text"])
            elif t == "role":
                p = d.add_paragraph()
                r = p.add_run(b["title"]); r.bold = True
                if b.get("org"): p.add_run(f" · {b['org']}")
                if b.get("url"):
                    disp = re.sub(r"^https?://(www\.)?", "", b["url"]).rstrip("/")
                    p.add_run(f"  {disp}")
                if b.get("where"): p.add_run(f" · {b['where']}")
                if b.get("dates"): p.add_run(f"    {b['dates']}")
    d.save(out_docx)
    return out_docx

def load_content(path):
    """Read a CV from Markdown (the authoring format) or JSON (still accepted).

    The .md is what a person and a Second Brain vault can read; the .json path stays
    so older content files, and anything generated programmatically, keep building.
    """
    text = open(path, encoding="utf-8").read()
    if path.lower().endswith((".md", ".markdown")) or text.lstrip().startswith("---"):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from cv_md import md_to_content
        return md_to_content(text)
    return json.loads(text)


# ---------------------------------------------------------------- output naming
# Upload widgets reject long filenames, and nothing used to cap this: the basename came
# straight out of the Markdown frontmatter, which the model wrote from a template that
# never defined how long "ShortRole" was allowed to be. The result was a 58-character name
# that a real application form refused. The role is dropped rather than abbreviated — the
# application folder is already named per-role, and so is the copy in the vault.
NAME_MAX = 40


def short_basename(raw, name="", company=""):
    """`<First>_<Last>_CV_<Company>`, ASCII, underscores, at most NAME_MAX chars."""
    def clean(x):
        x = unicodedata.normalize("NFKD", str(x or ""))
        x = x.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", x)).strip("_")

    cand = clean(raw)
    if not company:
        # The convention is <First>_<Last>_CV_<Company>[_<anything>], so when the caller
        # did not pass a company the authored name still carries it after "_CV_".
        m = re.search(r"_CV_([A-Za-z0-9]+)", cand)
        if m:
            company = m.group(1)
    built = ""
    if name and company:
        built = f"{clean(name)}_CV_{clean(company)}"
    # Prefer the canonical form when we can build it and the authored one is over budget.
    if built and (len(cand) > NAME_MAX or not cand):
        cand = built
    if len(cand) <= NAME_MAX:
        return cand or "CV"
    # Still too long: drop trailing words until it fits, never cutting mid-word unless a
    # single word is itself over budget.
    parts = cand.split("_")
    while len(parts) > 1 and len("_".join(parts)) > NAME_MAX:
        parts.pop()
    out = "_".join(parts)
    return (out if len(out) <= NAME_MAX else out[:NAME_MAX]).strip("_") or "CV"


def rename_source(path, base):
    """Rename the CV Markdown so its stem matches the PDF's. Returns the path in use."""
    src = os.path.abspath(path)
    if not src.lower().endswith(".md"):
        return path
    dst = os.path.join(os.path.dirname(src), base + ".md")
    if os.path.abspath(dst) == src:
        return path
    if os.path.exists(dst):
        # The PDF is about to be written as <base>.pdf while the Markdown stays <long>.md,
        # which is exactly the mismatch this rename exists to prevent: render_brain.py finds
        # a CV's PDF as md.with_suffix(".pdf"), so the pair would stop being mirrored.
        print(f"WARNING: {dst} already exists — the .md keeps its longer name, so the "
              f"Markdown and the PDF will NOT be a matching pair. Remove or rename the "
              f"existing file and rebuild.", file=sys.stderr)
        return path
    try:
        os.rename(src, dst)
    except OSError as e:
        print(f"WARNING: could not rename {src} -> {dst}: {e}", file=sys.stderr)
        return path
    print(f"MD renamed to match the PDF: {dst}")
    return dst


def mirror_into_brain(out_dir):
    """Refresh the brain's job layer when this CV was written into a brain's hidden ledger.

    The ledger (`<brain>/.plugins/job-search/applications/...`) is never shown in the vault;
    render_brain.py mirrors it into `45-jobs/` as `CV <Company>.md`. Until that runs, a CV
    that was just built is invisible in Studio ("isn't rendered into this brain's notes
    yet"). Best effort: a failed render never fails the build."""
    full = os.path.abspath(out_dir).replace(os.sep, "/")
    marker = "/.plugins/job-search/"
    if marker not in full:
        return
    brain = full.split(marker, 1)[0]
    here = os.path.dirname(os.path.abspath(__file__))
    # Claude plugin: skills/cv-tailor/scripts/ → skills/job-scout/scripts/render_brain.py;
    # the flattened Codex skill keeps every script side by side in one scripts/ folder.
    renderer = next((c for c in (
        os.path.join(os.path.dirname(os.path.dirname(here)), "job-scout", "scripts", "render_brain.py"),
        os.path.join(here, "render_brain.py"),
    ) if os.path.isfile(c)), None)
    if not renderer:
        return
    try:
        import subprocess
        r = subprocess.run([sys.executable, renderer, "--quiet"], cwd=brain,
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            print("brain: job layer re-rendered — the CV opens in Studio")
        else:
            print(f"note: could not re-render the job layer ({(r.stderr or '').strip()[-200:]}); "
                  "run render_brain.py --quiet", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 - never fail a finished CV over the mirror
        print(f"note: could not re-render the job layer ({e}); run render_brain.py --quiet", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("content", help="the CV content file — .md (preferred) or .json")
    ap.add_argument("--out", default=".")
    ap.add_argument("--max-pages", type=int, default=2)
    ap.add_argument("--docx", action="store_true")
    a = ap.parse_args()

    content = load_content(a.content)
    os.makedirs(a.out, exist_ok=True)
    base = short_basename(content.get("output_basename")
                          or os.path.splitext(os.path.basename(a.content))[0],
                          content.get("name", ""),
                          content.get("company")
                          or (content.get("target") or {}).get("company", ""))
    # Keep the pair. render_brain.py finds the PDF as `md.with_suffix(".pdf")`, so a
    # shortened PDF beside a long .md would silently stop being mirrored into the vault.
    a.content = rename_source(a.content, base)
    out_pdf = os.path.join(a.out, base + ".pdf")

    if not HAVE_REPORTLAB:
        # Exit 3, not 0. The Markdown is real and worth keeping, but a caller that reads
        # exit 0 as "the PDF exists" will attach a file that was never written.
        print("NO PDF PRODUCED — reportlab is not available.", file=sys.stderr)
        print(f"  interpreter: {sys.executable}", file=sys.stderr)
        print(f"  the CV IS complete as Markdown: {a.content}", file=sys.stderr)
        print(f"  fix: {sys.executable} -m pip install reportlab", file=sys.stderr)
        mirror_into_brain(a.out)
        return 3

    reg, bold, fname = register_fonts()
    unicode_ok = reg == "CV"
    if not unicode_ok:
        print("WARNING: no Unicode TTF found; falling back to Helvetica and stripping diacritics.")

    pages = None
    for scale in (1.0, 0.97, 0.94, 0.91, 0.88, 0.85, 0.82):
        pages = build(content, out_pdf, scale=scale, font=(reg, bold), unicode_ok=unicode_ok)
        if pages <= a.max_pages:
            break
    print(f"PDF: {out_pdf}  pages={pages}  scale={scale}  font={fname}")
    if pages > a.max_pages:
        print(f"WARNING: still {pages} pages at minimum scale — cut content.")
    if a.docx:
        out_docx = os.path.join(a.out, base + ".docx")
        if build_docx(content, out_docx):
            print(f"DOCX: {out_docx}")
    mirror_into_brain(a.out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
