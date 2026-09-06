# ATS / AI-readability QA checklist — run before delivering

Run `python3 scripts/check_pdf.py <file.pdf> --keywords "kw1;kw2;..."` and read
its report. Then confirm each item by eye on the rendered page images.

## Structure
- [ ] Single column, no tables for body content (the builder only uses a
      borderless 2-cell row for role-title/date lines, which extracts in order).
- [ ] Standard section names in this order: Professional Summary · Core
      Competencies · Work Experience · (Founder/Why section if programme)
      · Education · Technical Skills (optional) · Languages (optional).
- [ ] Contact block on page 1 top: name, headline, email, phone, city+country,
      LinkedIn, website — all as real text (no icons-only, no header/footer
      objects; parsers skip headers/footers).
- [ ] Every role line reads: Title · Company · Location · dates as MM/YYYY – MM/YYYY
      or YYYY – YYYY or "Present". Same format throughout.
- [ ] Reverse-chronological, no unexplained gaps > 1 month.
- [ ] ≤ 2 pages. Page 1 stands alone.

## Text & fonts
- [ ] Real embedded TrueType text (pdffonts shows emb=yes); no text-as-image.
- [ ] No text in white/tiny/hidden; no keyword blocks disguised as design.
- [ ] Bullets are real characters ("•") rendered by the builder, not glyph
      fonts (Wingdings) that parse as garbage.
- [ ] Diacritics render (e.g. Zürich, Kraków, Iaşi) — the builder embeds a Unicode font; if the
      keyword check shows "Ia?i", the font fallback failed — fix, don't ship.
- [ ] Hyphens/dashes: en dash between dates is fine; avoid exotic symbols.

## Keywords
- [ ] Every must-have keyword from the JD appears ≥ 2× (competencies + a
      bullet), both acronym and long form on first use.
- [ ] Target job title appears verbatim in headline AND summary.
- [ ] Years of experience stated, using the profile's own figure.
- [ ] check_pdf.py reports 0 missing must-have keywords.

## Extraction test (what the ATS actually sees)
- [ ] `pdftotext -layout` output reads top-to-bottom, sections in order,
      role line and dates on the same line, no interleaving from columns.
- [ ] First 300 characters contain: name, headline, email, phone.

## Human gate
- [ ] Headline mirrors the target title.
- [ ] First bullet of the first role answers the JD's #1 requirement.
- [ ] Bold lead-ins on bullets map to JD requirements.
- [ ] No claim outside profile/profile.md.
- [ ] Contact set matches the location decision; DOB absent unless required.
