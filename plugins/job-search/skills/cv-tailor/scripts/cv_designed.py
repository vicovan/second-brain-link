#!/usr/bin/env python3
"""
cv_designed.py — the `designed` CV template, imported by build_cv.py.

    A dark header band on page 1 (name in a display serif, the headline in italic accent,
    two contact lines, the status line, an optional square photo), a white body with
    serif section headings and a hairline, and Education / Work Experience on a thin
    timeline: dates in a gutter on the left, a ring marker per entry (filled only for a
    current role), a "Name, Headline · n / total" footer on every page.

The rules that keep it ATS-safe and small (references/designed-template.md):
- One reading order. Everything is drawn in the order a parser should read it: name,
  headline, contact, status, then the photo (no text in it); in an entry the date before
  the entry; the footer after the page content.
- Decoration is vector shapes only — band, dots, rings, rules — never glyphs or images of text.
- Fonts are the bundled open-licensed TTFs (assets/fonts), subset and embedded, so the PDF
  opens and parses anywhere with nothing installed. No Type3, no outlines.
- The photo is resampled to 480 px (300 dpi at 40 mm), EXIF/ICC stripped, JPEG q82: a photo
  never makes a CV heavy.
"""
import colorsys, glob, json, os, re, sys, tempfile

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
                                Flowable, KeepTogether, PageBreak, NextPageTemplate)

HERE = os.path.dirname(os.path.abspath(__file__))
# Claude plugin: skills/cv-tailor/assets/fonts; the flattened Codex skill: references/fonts.
FONT_DIRS = [os.path.join(HERE, "..", "assets", "fonts"),
             os.path.join(HERE, "..", "references", "fonts")]

# ---------------------------------------------------------------- palettes
PRESETS = {
    # band (dark header), accent (light: on the band + markers), ink (dark accent on white),
    # status (muted tint for the authorization line on the band)
    "navy-steel":     {"band": "#17202a", "accent": "#a7c4c0", "ink": "#3e6b6a", "status": "#97ad92"},
    "pine-mint":      {"band": "#0c3b3c", "accent": "#4fd8a8", "ink": "#0e7a63", "status": "#a6cfc4"},
    "ink-amber":      {"band": "#121a24", "accent": "#e2a03f", "ink": "#a16111", "status": "#9aa6b2"},
    "plum-rose":      {"band": "#2a1b2e", "accent": "#e8a6b8", "ink": "#8a3d5a", "status": "#c7a9b8"},
    "graphite-coral": {"band": "#1d1f22", "accent": "#ff8a65", "ink": "#b84a2a", "status": "#a9a9a9"},
    "oxford-sky":     {"band": "#14274e", "accent": "#8fc1ff", "ink": "#2457a6", "status": "#a9b8d4"},
}
DEFAULT_PALETTE = "navy-steel"

# Markets where a CV photo costs the candidate (playbook §2.3). Elsewhere it is common or expected.
NO_PHOTO_MARKETS = {"US", "USA", "GB", "UK", "CA", "AU", "IE", "NZ"}

TEXT_DARK = "#0f1419"
TEXT = "#20262d"
SOFT = "#5d6670"
RULE = "#dfe3e8"
FOOT = "#8a949e"


def _rgb(h):
    return [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c * 255)))) for c in rgb)


def _lum(h):
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b="#ffffff"):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _hls(h):
    return colorsys.rgb_to_hls(*_rgb(h))


def _shade(h, l=None, s_mul=1.0):
    hh, ll, ss = _hls(h)
    return _hex(colorsys.hls_to_rgb(hh, ll if l is None else l, max(0, min(1, ss * s_mul))))


def _darken_to(h, target=4.6):
    """Darken a colour until it reaches `target`:1 on white (the ink rule)."""
    l = _hls(h)[1]
    out = h
    while contrast(out) < target and l > 0.05:
        l -= 0.03
        out = _shade(h, l, 1.1)
    return out


def palette_from_photo(path):
    """Darkest clothing tone -> band, most colourful mid/light tone -> accent, accent
    darkened to 4.5:1 -> ink. Check the preview: shadows can read as a warm brown."""
    from PIL import Image
    im = Image.open(path).convert("RGB").resize((160, 160))
    q = im.quantize(colors=10, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:30]
    cols = [_hex([v / 255 for v in pal[i * 3:i * 3 + 3]]) for _, i in sorted(q.getcolors(), reverse=True)]
    darks = [c for c in cols if _hls(c)[1] < 0.35]
    band = darks[0] if darks else PRESETS[DEFAULT_PALETTE]["band"]
    band = _shade(band, min(_hls(band)[1], 0.13), 0.9)
    mids = sorted([c for c in cols if 0.45 < _hls(c)[1] < 0.85], key=lambda c: _hls(c)[2], reverse=True)
    accent = mids[0] if mids else PRESETS[DEFAULT_PALETTE]["accent"]
    accent = _shade(accent, max(_hls(accent)[1], 0.70), 1.15)
    return {"band": band, "accent": accent, "ink": _darken_to(accent),
            "status": _shade(accent, 0.62, 0.6)}


def palette_from_accent(accent):
    """A whole palette from one colour the user picked: the band is that hue nearly black, the
    ink is it darkened to 4.5:1 on white, the light accent and the status tint are lifted."""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(accent or "")):
        return None
    accent = accent.lower()
    return {"band": _shade(accent, 0.13, 0.7), "accent": _shade(accent, max(_hls(accent)[1], 0.72), 1.0),
            "ink": _darken_to(accent), "status": _shade(accent, 0.66, 0.45)}


def resolve_palette(spec, photo_src=None, accent=None):
    """`spec`: a preset name, "from-photo", "custom" (with `accent`), "employer" (the agent picks
    per employer; with nothing picked the default stands), or a dict / "band=#..,accent=#.."."""
    pal = None
    if spec == "custom":
        pal = palette_from_accent(accent)
        if pal is None:
            print(f"note: palette custom needs an accent colour like #2457a6; using {DEFAULT_PALETTE}",
                  file=sys.stderr)
    elif spec == "employer":
        pass
    elif isinstance(spec, dict):
        pal = dict(PRESETS[DEFAULT_PALETTE], **spec)
    elif isinstance(spec, str) and "#" in spec:
        pairs = dict(re.findall(r"(band|accent|ink|status)\s*[=:]\s*(#[0-9a-fA-F]{6})", spec))
        pal = dict(PRESETS[DEFAULT_PALETTE], **pairs)
    elif spec == "from-photo":
        if photo_src:
            try:
                pal = palette_from_photo(photo_src)
            except Exception as e:  # noqa: BLE001 - a palette is never worth a failed build
                print(f"note: palette from photo failed ({e}); using {DEFAULT_PALETTE}", file=sys.stderr)
    elif spec in PRESETS:
        pal = dict(PRESETS[spec])
    elif spec:
        print(f"note: unknown palette '{spec}'; using {DEFAULT_PALETTE}. "
              f"Presets: {', '.join(PRESETS)}", file=sys.stderr)
    pal = pal or dict(PRESETS[DEFAULT_PALETTE])
    if contrast(pal["ink"]) < 4.5:
        fixed = _darken_to(pal["ink"])
        print(f"WARNING: palette ink {pal['ink']} is {contrast(pal['ink']):.1f}:1 on white "
              f"(needs 4.5) — darkened to {fixed}", file=sys.stderr)
        pal["ink"] = fixed
    return pal


# ---------------------------------------------------------------- fonts
FACES = {
    "D":   "Fraunces72pt-SemiBold.ttf",     # name, section headings
    "D-I": "Fraunces72pt-Italic.ttf",       # headline
    "B":   "IBMPlexSans-Regular.ttf",       # body
    "B-I": "IBMPlexSans-Italic.ttf",
    "B-B": "IBMPlexSans-SemiBold.ttf",
}


def _font_file(name):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def register_fonts():
    """Register the bundled faces. Returns False (and names what is missing) when any face is
    absent — the caller then falls back to the classic template rather than ship Helvetica."""
    missing = [f for f in FACES.values() if not _font_file(f)]
    if missing:
        print(f"note: designed template fonts missing ({', '.join(missing)})", file=sys.stderr)
        return False
    for key, f in FACES.items():
        pdfmetrics.registerFont(TTFont("SBL" + key, _font_file(f)))
    pdfmetrics.registerFontFamily("SBLB", normal="SBLB", bold="SBLB-B", italic="SBLB-I",
                                  boldItalic="SBLB-B")
    return True


F_D, F_DI, F_B, F_BI, F_BB = "SBLD", "SBLD-I", "SBLB", "SBLB-I", "SBLB-B"


# ---------------------------------------------------------------- the user's CV design settings
# Written by Studio -> Jobs Agent -> Settings -> CV design (or by hand), read on every build:
#   <brain>/45-jobs/profile/style/cv-style.json   {"schema": "sbl-cv-style/1", ...}
STYLE_SCHEMA = "sbl-cv-style/1"
TEMPLATES = ("band", "minimal", "executive", "classic")
STYLE_CHOICES = {
    "template": TEMPLATES,
    "palette": tuple(PRESETS) + ("from-photo", "employer", "custom"),
    "photo": ("by-market", "always", "never"),
    "photo_shape": ("square", "rounded", "circle"),
}
STYLE_DEFAULTS = {"template": "band", "palette": DEFAULT_PALETTE, "photo": "by-market",
                  "photo_shape": "rounded", "accent": ""}


def _plugin_paths():
    try:
        for c in (os.path.join(os.path.dirname(os.path.dirname(HERE)), "job-scout", "scripts"), HERE):
            if os.path.isfile(os.path.join(c, "paths.py")) and c not in sys.path:
                sys.path.insert(0, c)
        import paths  # noqa: E402 - the plugin's one resolver
        return paths
    except Exception:  # noqa: BLE001 - outside the plugin there is simply no profile
        return None


def _profile_dirs(md_path=None, out_dir=None):
    """The profile folders this CV can draw on: the brain the output sits in, then this surface's."""
    paths, dirs = _plugin_paths(), []
    for p in (out_dir, md_path):
        full = os.path.abspath(p or "").replace(os.sep, "/")
        if paths is not None and "/.plugins/job-search/" in full:
            brain = full.split("/.plugins/job-search/", 1)[0]
            dirs.append(os.path.join(brain, paths.layer(brain, "jobs"), "profile"))
    if paths is not None:
        try:
            dirs.append(str(paths.profile_dir()))
        except Exception:  # noqa: BLE001
            pass
    out = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


def load_style(md_path=None, out_dir=None, path=None):
    """The user's CV design settings, validated; {} when there are none. A value outside the
    known choices is dropped with a note rather than trusted."""
    cands = [path] if path else [os.path.join(d, "style", "cv-style.json") for d in _profile_dirs(md_path, out_dir)]
    for f in cands:
        if not f or not os.path.isfile(f):
            continue
        try:
            raw = json.load(open(f, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"note: could not read {f} ({e}) — design settings ignored", file=sys.stderr)
            return {}
        if not isinstance(raw, dict):
            return {}
        style = {}
        for k, allowed in STYLE_CHOICES.items():
            v = str(raw.get(k, "")).strip().lower()
            if v and v in allowed:
                style[k] = v
            elif v:
                print(f"note: cv-style.json {k}={v!r} is not one of {', '.join(allowed)} — ignored",
                      file=sys.stderr)
        acc = str(raw.get("accent", "")).strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", acc):
            style["accent"] = acc.lower()
        style["_file"] = f
        return style
    return {}


def effective_design(design, style, cli_template=None):
    """What this build uses. Precedence: --template, then the CV's own frontmatter (the agent
    writes a one-off request there), then the user's settings, then the defaults.

    Frontmatter `template: designed` and `photo: auto` are the generic values older CVs carry;
    they defer to the settings rather than override them."""
    d = dict(design or {})
    st = dict(STYLE_DEFAULTS, **{k: v for k, v in (style or {}).items() if not k.startswith("_")})
    t = str(cli_template or d.get("template") or "").strip().lower()
    if t in ("", "designed"):
        t = st["template"]
    if t not in TEMPLATES:
        print(f"note: unknown template '{t}' — using {st['template']}", file=sys.stderr)
        t = st["template"]
    palette = d.get("palette") or st["palette"]
    accent = d.get("accent") or st.get("accent") or ""
    shape = str(d.get("photo_shape") or st["photo_shape"]).lower()
    if shape not in ("square", "rounded", "circle"):
        shape = "rounded"
    market = str(d.get("market", "")).strip().upper()
    photo = str(d.get("photo", "") or "").strip()
    if photo.lower() in ("", "auto"):
        policy = st["photo"] if style else ("always" if photo.lower() == "auto" else st["photo"])
        if policy == "never":
            photo = "none"
        elif policy == "by-market" and market in NO_PHOTO_MARKETS:
            photo = "none"
        else:
            if policy == "by-market" and not market:
                print("note: photo by market, but the CV names no `market:` — using the photo",
                      file=sys.stderr)
            photo = "auto"
    return {"template": t, "palette": palette, "accent": accent, "photo": photo,
            "photo_shape": shape, "market": market,
            "source": "settings" if style else "defaults"}


# ---------------------------------------------------------------- photo
PHOTO_EXT = (".jpg", ".jpeg", ".png", ".webp")


def find_photo(spec, md_path=None, out_dir=None):
    """`photo:` is `auto` (the newest image in the profile's photo/ folder), `none`, or a path."""
    if not spec or str(spec).strip().lower() in ("none", "no", "false", "off"):
        return None
    spec = str(spec).strip()
    if spec.lower() != "auto":
        cands = [spec] if os.path.isabs(spec) else \
            [os.path.join(d, spec) for d in (os.path.dirname(md_path or ""), out_dir or "", os.getcwd()) if d]
        for c in cands:
            if os.path.isfile(c):
                return os.path.abspath(c)
        print(f"note: photo '{spec}' not found — header without photo", file=sys.stderr)
        return None
    dirs = [os.path.join(d, "photo") for d in _profile_dirs(md_path, out_dir)]
    hits = []
    for d in dirs:
        hits += [f for f in glob.glob(os.path.join(d, "*")) if f.lower().endswith(PHOTO_EXT)]
    if not hits:
        print("note: photo: auto — no image in the profile's photo/ folder (Studio -> Jobs Agent "
              "-> Settings -> Your CV photo); header without photo", file=sys.stderr)
        return None
    return max(hits, key=os.path.getmtime)


def prepare_photo(src, zoom=1.0, center_x=None, px=480):
    """Square crop on the full image height (no zoom unless zoom > 1), faces sit high in a
    portrait. Resampled, metadata stripped, JPEG q82 in a temp file. Returns its path."""
    from PIL import Image, ImageOps
    im = Image.open(src)
    im = ImageOps.exif_transpose(im)              # phone photos carry their rotation in EXIF
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    im = im.convert("RGB")
    w, h = im.size
    side = int(min(w, h) / max(1.0, float(zoom or 1.0)))
    cx = int(float(center_x) * w) if center_x not in (None, "") else w // 2
    left = max(0, min(w - side, cx - side // 2))
    top = 0 if h <= w else max(0, int((h - side) * 0.15))
    im = im.crop((left, top, left + side, top + side)).resize((px, px), Image.LANCZOS)
    fd, out = tempfile.mkstemp(prefix="cv_photo_", suffix=".jpg")
    os.close(fd)
    im.save(out, "JPEG", quality=82, optimize=True, progressive=False)   # no exif/icc passed on
    return out


# ---------------------------------------------------------------- markup
_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def md(text, link_color):
    out = []
    for p in re.split(r"(\[[^\]]+\]\([^)]+\))", text or ""):
        m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", p)
        if m:
            label = "".join(_ESC.get(c, c) for c in m.group(1))
            out.append(f'<link href="{m.group(2)}" color="{link_color}">{label}</link>')
        else:
            s = "".join(_ESC.get(c, c) for c in p)
            s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
            s = re.sub(r"\*([^*\n]+?)\*", r"<i>\1</i>", s)
            out.append(s)
    return "".join(out)


def plain(text):
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text or "")
    return re.sub(r"\*+", "", t).strip()


# ---------------------------------------------------------------- flowables
PHOTO_SHAPES = ("square", "rounded", "circle")


def draw_photo(c, img, x, y, s, shape, border, bw):
    """The photo clipped to its shape, then a thin border in the palette colour."""
    def path():
        p = c.beginPath()
        if shape == "circle":
            p.circle(x + s / 2, y + s / 2, s / 2)
        else:
            p.roundRect(x, y, s, s, 0 if shape == "square" else 1.2 * mm)
        return p
    c.saveState()
    c.clipPath(path(), stroke=0, fill=0)
    c.drawImage(img, x, y, s, s)
    c.restoreState()
    c.setStrokeColor(colors.HexColor(border))
    c.setLineWidth(bw)
    c.drawPath(path(), stroke=1, fill=0)


class HeaderBand(Flowable):
    """Page-1 header in one of three styles. All text is drawn with drawString in reading
    order (name, headline, contact, status); the photo last, with no text in it.

    band       a full-bleed dark band, white name, accent headline, photo on the right
    minimal    white header, dark serif name, ink headline, a short accent rule underneath
    executive  everything centred, a full-width hairline underneath, a small photo top-right
    """

    def __init__(self, content, pal, photo, page_w, margin, style="band", shape="rounded"):
        super().__init__()
        self.c, self.pal, self.photo = content, pal, photo
        self.page_w, self.margin = page_w, margin
        self.style = style if style in ("band", "minimal", "executive") else "band"
        self.shape = shape if shape in PHOTO_SHAPES else "rounded"
        ct = content.get("contact", {}) or {}
        self.line1 = [x for x in (ct.get("location"), ct.get("phone"), ct.get("email")) if x]
        self.links = [(l.get("text") or l.get("url", ""), l.get("url", "")) for l in ct.get("links", []) or []]
        self.status = plain(ct.get("status", ""))
        self.name, self.headline = plain(content.get("name", "")), plain(content.get("headline", ""))
        band = self.style == "band"
        self.PAD_T = 10 * mm if band else 13 * mm
        self.PAD_B = 8 * mm if band else 6 * mm
        self.PHOTO = 26 * mm if self.style == "executive" else (40 * mm if band else 34 * mm)
        self.GAP = 8 * mm
        self.centre = self.style == "executive"
        if band:
            self.col = {"name": "#ffffff", "head": pal["accent"], "contact": "#eef2f4",
                        "dot": pal["accent"], "status": pal["status"], "border": pal["accent"]}
        else:
            self.col = {"name": TEXT_DARK, "head": pal["ink"], "contact": TEXT,
                        "dot": pal["ink"], "status": SOFT, "border": RULE}

    def _layout(self, aw):
        side = (self.PHOTO + self.GAP) if self.photo else 0
        # centred text keeps clear of the photo on both sides so it stays truly centred
        tw = aw - (2 * side if self.centre else side)
        self.tw = tw
        self.name_fs = 28 if self.centre else 31
        while self.name_fs > 20 and pdfmetrics.stringWidth(self.name, F_D, self.name_fs) > tw:
            self.name_fs -= 1
        # a long headline steps down to 12pt before it wraps; one word alone on a line reads broken
        self.head_fs = 14.0
        while self.head_fs > 12 and pdfmetrics.stringWidth(self.headline, F_DI, self.head_fs) > tw:
            self.head_fs -= 0.5
        self.head_lines = simpleSplit(self.headline, F_DI, self.head_fs, tw) if self.headline else []
        self.contact_rows = self._rows([(x, None) for x in self.line1], tw) + \
            self._rows(self.links, tw)
        self.status_lines = simpleSplit(self.status, F_B, 8.4, tw) if self.status else []
        h = self.name_fs * 0.98
        h += (2.2 * mm + len(self.head_lines) * self.head_fs * 1.18) if self.head_lines else 0
        h += 4.5 * mm - 11 + len(self.contact_rows) * 12.6 if self.contact_rows else 0
        h += (1 * mm + len(self.status_lines) * 11) if self.status_lines else 0
        self.text_h = h
        photo_h = self.PHOTO if (self.photo and not self.centre) else 0
        self.inner_h = max(h, photo_h)
        return self.inner_h + self.PAD_T + self.PAD_B

    def _rows(self, items, width, fs=9):
        """Contact items laid out left to right; a new row starts rather than splitting one."""
        rows, cur, cw = [], [], 0
        sep = 6.4 * mm
        for text, url in items:
            w = pdfmetrics.stringWidth(text, F_B, fs)
            add = w + (sep if cur else 0)
            if cur and cw + add > width:
                rows.append(cur)
                cur, cw, add = [], 0, w
            cur.append((text, url, w))
            cw += add
        if cur:
            rows.append(cur)
        return rows

    def wrap(self, aw, ah):
        self.width = aw
        self.height = self._layout(aw)
        return aw, self.height

    def _x(self, w):
        return (self.width - w) / 2 if self.centre else 0

    def draw(self):
        c, pal, col = self.canv, self.pal, self.col
        c.saveState()
        if self.style == "band":
            # the band runs to the page edges and the page top; the canvas is not clipped to the frame
            c.setFillColor(colors.HexColor(pal["band"]))
            c.rect(-self.margin, 0, self.page_w, self.height + 2 * mm, stroke=0, fill=1)
        top = self.height - self.PAD_T
        if self.photo and not self.centre and self.text_h < self.PHOTO:   # centre the text on the photo
            top -= (self.PHOTO - self.text_h) / 2
        y = top - self.name_fs * 0.78
        c.setFillColor(colors.HexColor(col["name"]))
        c.setFont(F_D, self.name_fs)
        c.drawString(self._x(pdfmetrics.stringWidth(self.name, F_D, self.name_fs)), y, self.name)
        if self.head_lines:
            hf, hl = self.head_fs, self.head_fs * 1.18
            y -= 2.2 * mm + hf
            c.setFillColor(colors.HexColor(col["head"]))
            c.setFont(F_DI, hf)
            for i, ln in enumerate(self.head_lines):
                c.drawString(self._x(pdfmetrics.stringWidth(ln, F_DI, hf)), y - i * hl, ln)
            y -= (len(self.head_lines) - 1) * hl
        if self.contact_rows:
            y -= 4.5 * mm + 1.6
            for r, row in enumerate(self.contact_rows):
                x = self._x(sum(w for _, _, w in row) + 6.4 * mm * (len(row) - 1))
                for k, (text, url, w) in enumerate(row):
                    if k:
                        c.setFillColor(colors.HexColor(col["dot"]))
                        c.circle(x + 3.2 * mm, y + 2.6, 0.55 * mm, stroke=0, fill=1)
                        x += 6.4 * mm
                    c.setFillColor(colors.HexColor(col["contact"]))
                    c.setFont(F_B, 9)
                    c.drawString(x, y, text)
                    if url:
                        c.linkURL(url, (x, y - 2, x + w, y + 9), relative=1)
                    x += w
                if r < len(self.contact_rows) - 1:
                    y -= 12.6
        if self.status_lines:
            y -= 1 * mm + 11
            c.setFillColor(colors.HexColor(col["status"]))
            c.setFont(F_B, 8.4)
            for i, ln in enumerate(self.status_lines):
                c.drawString(self._x(pdfmetrics.stringWidth(ln, F_B, 8.4)), y - i * 11, ln)
        if self.style == "minimal":
            c.setStrokeColor(colors.HexColor(pal["ink"]))
            c.setLineWidth(2)
            c.line(0, 1.5 * mm, 30 * mm, 1.5 * mm)
        elif self.style == "executive":
            c.setStrokeColor(colors.HexColor(RULE))
            c.setLineWidth(0.6)
            c.line(0, 1.5 * mm, self.width, 1.5 * mm)
        if self.photo:
            s = self.PHOTO
            px = self.width - s
            py = (self.height - self.PAD_T - s + 2 * mm) if self.centre \
                else self.PAD_B + (self.inner_h - s) / 2
            bw = 0.7 * mm if self.style == "band" else 0.4 * mm
            draw_photo(c, self.photo, px, py, s, self.shape, col["border"], bw)
        c.restoreState()


class SectionHead(Flowable):
    """A serif section heading with a hairline running to the right edge."""

    def __init__(self, text, space_before):
        super().__init__()
        self.text, self.sb = plain(text), space_before
        self.keepWithNext = 1

    def wrap(self, aw, ah):
        self.width = aw
        self.height = self.sb + 12.5 + 2.4 * mm
        return aw, self.height

    def draw(self):
        c = self.canv
        base = 2.4 * mm + 2.5
        c.setFillColor(colors.HexColor(TEXT_DARK))
        c.setFont(F_D, 12.5)
        c.drawString(0, base, self.text)
        x = pdfmetrics.stringWidth(self.text, F_D, 12.5) + 3.5 * mm
        c.setStrokeColor(colors.HexColor(RULE))
        c.setLineWidth(0.6)
        c.line(x, base + 4, self.width, base + 4)


class Gutter(Flowable):
    """One piece of a timeline entry: the inner flowable sits right of a date column and a
    vertical rule. The first piece also draws the marker and the dates — before the inner
    text, so a parser reads "dates, then entry"."""

    COL, GAP, PAD = 27 * mm, 6 * mm, 5 * mm

    def __init__(self, inner, pal, dates=None, first=False, current=False, pad_after=0,
                 cont_label=None):
        super().__init__()
        self.inner, self.pal = inner, pal
        self.dates, self.first, self.current = dates, first, current
        self.pad_after, self.cont_label = pad_after, cont_label

    @property
    def x0(self):
        return self.COL + self.GAP

    def wrap(self, aw, ah):
        self.width = aw
        _, ih = self.inner.wrap(aw - self.x0 - self.PAD, ah)
        self.ih = ih
        self.lab_h = 11 if self.cont_label else 0
        self.height = ih + self.pad_after + self.lab_h
        return aw, self.height

    def draw(self):
        c, pal = self.canv, self.pal
        top = self.height - self.lab_h
        if self.cont_label:
            c.setFillColor(colors.HexColor(SOFT))
            c.setFont(F_BI, 8)
            c.drawString(self.x0 + self.PAD, top + 3, self.cont_label)
        c.setStrokeColor(colors.HexColor(RULE))
        c.setLineWidth(0.8)
        c.line(self.x0, 0, self.x0, top)
        if self.first:
            if self.dates:
                c.setFillColor(colors.HexColor(pal["ink"]))
                c.setFont(F_B, 7.6)
                c.drawRightString(self.COL, top - 0.9 * mm - 7.6, self.dates)
            r = 1.15 * mm
            cy = top - 1.5 * mm - r
            c.setStrokeColor(colors.HexColor(pal["accent"]))
            c.setLineWidth(0.9)
            c.setFillColor(colors.HexColor(pal["accent"]) if self.current else colors.white)
            c.circle(self.x0, cy, r, stroke=1, fill=1)
        self.inner.drawOn(c, self.x0 + self.PAD, self.pad_after)


class EntryHead(Flowable):
    """Executive template: an entry's first line with the dates right-aligned on the same
    baseline — no gutter. The text is drawn first, the dates after, so a parser reads the entry
    and then its dates."""

    DATE_W = 34 * mm

    def __init__(self, inner, dates, pal, pad_after=0):
        super().__init__()
        self.inner, self.dates, self.pal, self.pad_after = inner, dates or "", pal, pad_after

    def wrap(self, aw, ah):
        self.width = aw
        _, ih = self.inner.wrap(aw - (self.DATE_W if self.dates else 0), ah)
        self.ih = ih
        self.height = ih + self.pad_after
        return aw, self.height

    def draw(self):
        c = self.canv
        self.inner.drawOn(c, 0, self.pad_after)
        if self.dates:
            st = self.inner.style
            c.setFillColor(colors.HexColor(self.pal["ink"]))
            c.setFont(F_B, 7.8)
            c.drawRightString(self.width, self.height - st.leading + (st.leading - st.fontSize) / 2 + 1,
                              self.dates)


class NumberedCanvas(rl_canvas.Canvas):
    """Buffers the pages so the footer can say "n / total"; the footer is stamped after each
    page's content, so a parser reads it last."""

    footer = ""

    def __init__(self, *a, **kw):
        # start every page in a bundled face, so no unembedded Helvetica is even referenced
        if not kw.get("initialFontName"):
            kw["initialFontName"] = F_B
        super().__init__(*a, **kw)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._pages)
        for st in self._pages:
            self.__dict__.update(st)
            self.setFont(F_B, 7)
            self.setFillColor(colors.HexColor(FOOT))
            w, _ = self._pagesize
            self.drawString(18 * mm, 7 * mm, self.footer)
            self.drawRightString(w - 18 * mm, 7 * mm, f"{self._pageNumber} / {n}")
            super().showPage()
        super().save()


# ---------------------------------------------------------------- build
# (body pt, line height, section gap mm, entry gap mm) — loosest first; the builder takes the
# first that fits the page limit.
DENSITIES = [(9.0, 1.48, 5.6, 3.2), (8.8, 1.45, 5.2, 2.8), (8.8, 1.43, 4.8, 2.8),
             (8.6, 1.42, 4.4, 2.5), (8.4, 1.40, 4.0, 2.2), (8.2, 1.38, 3.6, 2.0)]


def _is_current(dates):
    return bool(re.search(r"(present|now|current)\s*$", (dates or "").strip(), re.I))


def _split_where(where):
    """`City, Country · what the company does` -> (location, descriptor)."""
    if not where:
        return "", ""
    loc, _, rest = where.partition(" · ")
    return loc.strip(), rest.strip()


def build(content, out_pdf, dens, pal, photo, template="band", shape="rounded"):
    fs, lh, sec_gap, gap = dens
    gutter = template != "executive"      # executive: dates sit on the entry's own line
    LM = RM = 18 * mm
    W, H = A4
    ink = pal["ink"]
    S = {
        "summary": ParagraphStyle("summary", fontName=F_B, fontSize=fs + 1, leading=(fs + 1) * 1.55,
                                  textColor=colors.HexColor(TEXT_DARK)),
        "p": ParagraphStyle("p", fontName=F_B, fontSize=fs, leading=fs * lh,
                            textColor=colors.HexColor(TEXT), spaceAfter=1.2 * mm),
        "h3": ParagraphStyle("h3", fontName=F_BB, fontSize=10.6, leading=10.6 * 1.3,
                             textColor=colors.HexColor(TEXT_DARK)),
        "role": ParagraphStyle("role", fontName=F_B, fontSize=9.2, leading=9.2 * 1.35,
                               textColor=colors.HexColor(TEXT_DARK)),
        "desc": ParagraphStyle("desc", fontName=F_B, fontSize=8.5, leading=8.5 * 1.38,
                               textColor=colors.HexColor(SOFT)),
        "ctx": ParagraphStyle("ctx", fontName=F_BI, fontSize=fs - 0.2, leading=fs * lh,
                              textColor=colors.HexColor(SOFT)),
        "li": ParagraphStyle("li", fontName=F_B, fontSize=fs, leading=fs * lh,
                             textColor=colors.HexColor(TEXT), leftIndent=3.8 * mm,
                             bulletIndent=0, bulletFontName=F_B, bulletFontSize=fs,
                             bulletColor=colors.HexColor(ink)),
        "sub": ParagraphStyle("sub", fontName=F_BB, fontSize=fs, leading=fs * lh,
                              textColor=colors.HexColor(SOFT)),
        "cont": ParagraphStyle("cont", fontName=F_BI, fontSize=8, leading=11,
                               textColor=colors.HexColor(SOFT)),
    }
    M = lambda t: md(t, ink)

    doc = BaseDocTemplate(out_pdf, pagesize=A4, leftMargin=LM, rightMargin=RM,
                          topMargin=14 * mm, bottomMargin=13 * mm,
                          title=f"{plain(content.get('name', ''))}, {plain(content.get('headline', ''))}",
                          author=plain(content.get("name", "")), subject="CV / Resume",
                          keywords=", ".join((content.get("design") or {}).get("keywords") or []),
                          creator="Second Brain Link · cv-tailor")
    first = Frame(LM, 13 * mm, W - LM - RM, H - 13 * mm, id="first",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later = Frame(LM, 13 * mm, W - LM - RM, H - 27 * mm, id="later",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate("First", frames=[first]),
                          PageTemplate("Later", frames=[later])])
    avail = W - LM - RM

    story = [NextPageTemplate("Later"), HeaderBand(content, pal, photo, W, LM, template, shape)]

    def li(b):
        txt = (f"<b>{M(b['lead'])}</b> " if b.get("lead") else "") + M(b.get("text", ""))
        return Paragraph(txt, S["li"], bulletText="–")

    first_sec = True
    for sec in content.get("sections", []):
        heading = sec.get("heading", "")
        if heading:
            story.append(SectionHead(heading, (sec_gap + 1.6 if first_sec else sec_gap) * mm))
        first_sec = False
        blocks = sec.get("blocks", [])
        is_summary = heading.lower() in ("professional summary", "summary", "profile")
        role = None              # the open timeline entry, while bullets belong to it
        pieces = []              # its flowables, before they are wrapped in Gutters
        pending_label = None

        def close_entry():
            nonlocal role, pieces
            if role is None:
                return
            # one list of flowables per piece; never a KeepTogether inside a KeepTogether (it
            # reports a huge height to force its own split, which would push every entry to a
            # new page)
            gut = []
            for k, (fl, label, after) in enumerate(pieces):
                if gutter:
                    gut.append([Gutter(fl, pal, dates=role.get("dates"), first=(k == 0),
                                       current=_is_current(role.get("dates")),
                                       pad_after=after, cont_label=label)])
                elif k == 0:
                    gut.append([EntryHead(fl, role.get("dates"), pal, after)])
                else:
                    lab = Paragraph(label, S["cont"]) if label else None
                    if lab is not None:
                        lab.cont_label = label
                    gut.append(([lab] if lab is not None else []) + [fl, Spacer(1, after)])
            # keep the header lines with the first bullet; let the rest flow
            head = 0
            while head < len(gut) and pieces[head][1] is None and \
                    pieces[head][0].style.name in ("h3", "role", "desc", "ctx"):
                head += 1
            if head < len(gut) and pieces[head][1] is None:
                head += 1
            out = [KeepTogether([f for g in gut[:head] for f in g])]
            for g in gut[head:]:
                if getattr(g[0], "cont_label", None):
                    out.append(PageBreak())
                out.extend(g)
            story.extend(out)
            story.append(Spacer(1, gap * mm))
            role, pieces = None, []

        for b in blocks:
            t = b.get("type", "paragraph")
            if t == "role":
                close_entry()
                role = b
                org = b.get("org", "")
                company, _, org_desc = org.partition(" · ")
                loc, where_desc = _split_where(b.get("where", ""))
                if company:
                    pieces.append((Paragraph(M(company), S["h3"]), None, 0.3 * mm))
                    sub = M(b.get("title", ""))
                    if loc:
                        sub += f'<font color="{ink}">  ·  </font><font color="{SOFT}">{M(loc)}</font>'
                    pieces.append((Paragraph(sub, S["role"]), None, 0.4 * mm))
                else:
                    pieces.append((Paragraph(M(b.get("title", "")), S["h3"]), None, 0.3 * mm))
                    if loc:
                        pieces.append((Paragraph(M(loc), S["role"]), None, 0.4 * mm))
                desc = " · ".join(x for x in (org_desc, where_desc) if x)
                for u in (b.get("url") or "").split():
                    disp = re.sub(r"^https?://(www\.)?", "", u).rstrip("/")
                    desc += (" · " if desc else "") + f"[{disp}]({u})"
                if desc:
                    pieces.append((Paragraph(M(desc), S["desc"]), None, 1 * mm))
            elif t == "break":
                if role is not None:
                    company = (role.get("org") or role.get("title") or "").partition(" · ")[0]
                    pending_label = f"{plain(company)}, continued"
            elif t == "bullet" and role is not None:
                pieces.append((li(b), pending_label, 0.6 * mm))
                pending_label = None
            elif t == "paragraph" and role is not None:
                ctx = re.fullmatch(r"\*[^*].*\*", b.get("text", "").strip()) is not None
                pieces.append((Paragraph(M(b["text"]), S["ctx" if ctx else "p"]), pending_label, 1 * mm))
                pending_label = None
            elif t == "entries":
                close_entry()
                for it in b.get("items", []):
                    left, right = (it[0], it[1]) if isinstance(it, (list, tuple)) \
                        else (it.get("left", ""), it.get("right", ""))
                    if gutter:
                        story.append(Gutter(Paragraph(M(left), S["role"]), pal, dates=right, first=True,
                                            current=_is_current(right), pad_after=gap * mm))
                    else:
                        story.append(EntryHead(Paragraph(M(left), S["role"]), right, pal, gap * mm))
            elif t == "subheading":
                close_entry()
                story.append(Paragraph(M(b["text"]), S["sub"]))
            elif t == "kv":
                close_entry()
                for it in b.get("items", []):
                    k, v = (it[0], it[1]) if isinstance(it, (list, tuple)) else (it.get("label"), it.get("value"))
                    story.append(Paragraph(f"<b>{M(k)}:</b> {M(v)}", S["p"]))
            elif t == "spacer":
                story.append(Spacer(1, b.get("height", 4)))
            elif t == "bullet":
                story.append(li(b))
            else:  # paragraph outside an entry
                story.append(Paragraph(M(b.get("text", "")), S["summary" if is_summary else "p"]))
        close_entry()

    NumberedCanvas.footer = f"{plain(content.get('name', ''))}, {plain(content.get('headline', ''))}"
    doc.build(story, canvasmaker=NumberedCanvas)
    return doc.page


def build_designed(content, out_pdf, max_pages=2, md_path=None, out_dir=None, eff=None):
    """Render; return (pages, density, palette, photo_used, eff). `eff` is effective_design();
    computed here when the caller did not. Raises nothing on a missing photo."""
    d = content.get("design") or {}
    if eff is None:
        eff = effective_design(d, load_style(md_path, out_dir))
    template = eff["template"] if eff["template"] in ("band", "minimal", "executive") else "band"
    src = find_photo(eff["photo"], md_path, out_dir)
    if src and eff["market"] in NO_PHOTO_MARKETS:
        print(f"WARNING: a photo on a CV for market {eff['market']} usually costs the screen — "
              f"set `photo: none` unless the user asked for it", file=sys.stderr)
    pal = resolve_palette(eff["palette"], src, eff.get("accent"))
    photo = None
    try:
        if src:
            photo = prepare_photo(src, d.get("photo_zoom") or 1.0, d.get("photo_center_x"))
        pages = None
        for dens in DENSITIES:
            pages = build(content, out_pdf, dens, pal, photo, template, eff["photo_shape"])
            if pages <= max_pages:
                break
        return pages, dens, pal, src, eff
    finally:
        if photo and os.path.exists(photo):
            os.remove(photo)        # our own temp file
