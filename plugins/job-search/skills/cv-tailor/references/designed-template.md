# The designed CV template — layout, photo, palette and the three reviews

The `designed` template (`scripts/cv_designed.py`, the default) produces a two-page A4 CV that a
recruiter enjoys reading, that an ATS parses cleanly, and that is light enough for any upload
widget. This file holds the design rules. The writing rules (truth boundary, title ladder, summary,
bullets, de-tell) stay in `tailoring-playbook.md`, and `lint_cv.py` enforces them. Where the two
files overlap, the playbook and the linter win.

---

## 0. Inputs, beyond the profile

Ask only for what is missing. Never invent a fact to fill a gap.

| Input | Where it comes from |
|---|---|
| Market | The country the role sits in → frontmatter `market:` as an ISO code (`AE`, `DE`, `US`, `GB`…). It drives the photo and the personal-data rules. |
| Photo | Studio → Jobs Agent → Settings → *Your CV photo*, stored in `45-jobs/profile/photo/`. Use it as is: no retouching. Never ask the user to paste a photo into chat. |
| Photo policy | `profile.md` §10 *Photo on CV*: `by market` (the default) · `always` · `never`. |
| Palette | `profile.md` §10 *Palette*, else chosen per employer (§3). |
| Availability | A notice period or start date, if the profile has one. Many markets screen on it first. |

## 1. Photo, date of birth and other personal data

- **Photo by market.** It is common and often expected in the Gulf, much of continental Europe and
  Asia. Leave it off for the US, UK, Canada, Australia, Ireland and New Zealand unless the user
  insists. `lint_cv.py` warns when it is on for those markets.
- Never include a date of birth, marital status, religion, ID number or full home address unless
  the user explicitly asks for a market that requires it. `lint_cv.py` fails these unless `market:`
  is one where a date of birth is still sometimes expected (DE, AT, CH).
- In the frontmatter, `photo: auto` uses the newest image in the profile's `photo/` folder,
  `photo: none` leaves it off, and a path names one file. With no image uploaded, the header is
  text-only. That is not an error, but say it in the delivery note.

## 2. Layout (what the builder draws)

- **Page 1 header band**, full width and dark. Inside it:
  - the name in the display serif
  - the headline in italic, in the accent colour
  - contact line 1: location · phone · email
  - contact line 2: the LinkedIn link
  - the status line (citizenship / work authorization) in a muted tint
  - optionally, a 40 mm square photo on the right
- **White body.** Section headings are in the serif with a hairline to the right edge.
- **Timeline** for Work Experience and Education. Each entry has:
  - dates in a gutter on the left
  - a small ring marker, filled only when the entry runs to *Present*
  - then, in order: company (bold), title · location, a grey line saying what the company does,
    and the bullets with a dash
- **Footer on every page**: "Name, Headline" on the left, "n / total" on the right. Separated
  pages stay identifiable.
- **"Company, continued".** When a role splits across pages, put `<!-- break -->` on its own line
  before the first bullet that lands on the next page (check the PNG previews). The builder then
  breaks the page there and prints the italic label.

How the Markdown maps onto an entry:

```
### Director of Engineering | Meridian Analytics · Enterprise Analytics Platform
*03/2021 – Present*
Remote from Portugal · US company (Boston) · Series C, 300 staff
```

| On the page | Comes from |
|---|---|
| Company (bold) | the text after `|`, up to the first ` · ` |
| Title · location | the text before `|`, then the meta line up to its first ` · ` |
| Grey descriptor | the rest of both, plus the company site |

So the meta line always opens with the location.

## 3. Palette

There are three roles on the page, with one palette per CV:

| Role | Colour | Used for |
|---|---|---|
| `band` | dark | the header background |
| `accent` | light | the title on the band, the contact dots, the photo border, the timeline rings |
| `ink` | a darker accent | the dates and bullet dashes on white. It must reach 4.5:1 on white; the builder darkens it if not. |
| `status` | a muted tint | the authorization line |

Frontmatter `palette:` takes one of these:
- a preset: `navy-steel` (default) · `oxford-sky` · `pine-mint` · `ink-amber` · `plum-rose` · `graphite-coral`
- `from-photo`: derived from the photo. Check the preview, because shadows can turn a navy band brown.
- explicit values: `band=#17202a, accent=#a7c4c0, ink=#3e6b6a, status=#97ad92`

Match the palette to the employer:
- Conservative industries (finance, government, consulting, legal) suit `navy-steel` or `oxford-sky`.
- Product, design and consumer companies can carry `pine-mint`, `plum-rose` or `graphite-coral`.

Colour appears only on the band, markers, dates and dashes.

## 3b. The four templates, and the settings file

| Template | Looks like | Suits |
|---|---|---|
| `band` (default) | Dark full-width header band, white serif name, photo on the right, dated timeline | Most roles; markets where a photo is expected |
| `minimal` | White header, dark serif name, a short accent rule, the same timeline | Product, design, consumer, start-ups |
| `executive` | Everything in the header centred, a full-width hairline, no gutter — each entry's dates sit right-aligned on its own line | Finance, consulting, legal, board and C-level roles |
| `classic` | Plain single column, one deep blue, no photo | Portals that choke on designed PDFs; a user who asks for plain |

Photo shapes: `square`, `rounded` (default), `circle`.

**The settings file** — what Studio's *CV design* tab writes, and what a CLI user can write by hand:

```json
{"schema": "sbl-cv-style/1", "template": "band", "palette": "navy-steel",
 "accent": "#2457a6", "photo": "by-market", "photo_shape": "rounded"}
```
at `<brain>/45-jobs/profile/style/cv-style.json` (or `<working folder>/45-jobs/profile/style/`).
`palette` is a preset, `from-photo`, `employer` (the agent picks per company) or `custom` (built
from `accent`: the band is that hue nearly black, the ink is it darkened to 4.5:1). `photo` is
`by-market` · `always` · `never`. Unknown values are ignored with a note. Precedence on every
build: `--template`, then the CV's frontmatter (a one-off request), then this file, then the
defaults. The builder prints `from=settings` when the file was used.

## 4. Typography and file

- **Fonts.** The display serif is Fraunces (SemiBold for the name and headings, Italic for the
  headline). The body is IBM Plex Sans (Regular, Italic, SemiBold). Both are SIL OFL, bundled in
  `assets/fonts/`, and subset-embedded in the PDF. The CV opens and parses on any machine with
  nothing installed. Never substitute a system font or a downloaded one.
- **No letter-spacing and no all-caps headings.** Text extraction splits spaced capitals
  ("EX PER IENCE").
- **Small file.** The photo is resampled to 480 px, stripped of EXIF and ICC data, and saved as
  JPEG q82. A designed CV with a photo is about 90 KB. `check_pdf.py` fails anything over 1 MB and
  warns over 400 KB.
- **Metadata.** Title "Name, Headline", Author "Name", and Keywords from the frontmatter
  `keywords:` list. Put the posting's exact title and its top must-have terms there.

## 5. ATS rules (enforced by the template; verify with `check_pdf.py`)

- The extracted text begins: name, headline, location, phone, email, LinkedIn, status. Then
  "Professional Summary".
- Nothing text-like comes before the name: no monograms, initials badges or logos.
- One reading order. The date gutter extracts as "dates, then entry". The photo carries no text.
- Use standard section headings, and write "Present" for current roles.
- Use real embedded fonts. No Type3 fonts, no text in images, no tables for layout.

## 6. The three reviews, after building and before delivery

Run all three in this order, as if you were each person. Fix every finding, rebuild, and look
again. Record anything durable with `learn.py add-lesson … --tag cv`.

**Recruiter (a 10-second scan, then a 60-second read)**
- [ ] The headline matches the posted title.
- [ ] Location, phone, email and authorization are visible in the band. The status line answers
  the sponsorship question without volunteering a need.
- [ ] Every must-have is visibly covered by a real role, not only by a keyword.
- [ ] The summary has a bridge to the employer's industry.
- [ ] The most recent role answers the posting's "what success looks like".
- [ ] At least one number appears in the top two roles (if the profile has one).
- [ ] Job-hopping or concurrent roles are explained by the grey company line (acquired,
  contract, founder) rather than left as a question.
- [ ] Each role has one concrete detail only this person would know: a constraint, a trade-off,
  a lesson.
- [ ] Nothing appears that the user cannot defend in an interview.

**ATS import (`check_pdf.py --name … --headline … --title … --keywords …`)**
- [ ] The reading order is name → headline → contact → status → Summary.
- [ ] Headings extract as whole words.
- [ ] Each job extracts as dates, company, title · location, description, bullets.
- [ ] Every must-have appears at least once, and the exact title at least twice.
- [ ] There are no replacement characters, so diacritics render.
- [ ] Pages are within the limit, fonts are embedded, and the size gate is green.

**Designer (look at every `--png` page)**
- [ ] The hierarchy has three clear levels: company, then title, then details.
- [ ] One palette, used with restraint.
- [ ] Filled markers mean "current" and nothing else.
- [ ] Contact lines don't wrap awkwardly or leave a stray dot.
- [ ] Page 2 has no orphaned bullets without a "continued" label, and page 1 has no large empty
  gap at the bottom.
- [ ] The rhythm is even: the same spacing and the same structure for every job.
- [ ] The photo is square, sharp, not over-zoomed, and the face is centred. If it isn't, adjust
  `photo_center_x` (0 to 1) or `photo_zoom` (1.0 means no zoom).
- [ ] It is readable at 100 % on a laptop and in greyscale print.

## 7. Delivery note (at most 6 lines)

- What was built: the file name, page count, template, palette, photo used or not (and why), the
  location choice.
- What was tailored: the title match, the industry bridge, which requirements the top roles answer.
- What was left out because the profile did not support it.
- What the user could add to make it stronger: availability, a number, a certification, a photo
  for a market that expects one.
