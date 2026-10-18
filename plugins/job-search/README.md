# job-search — the first Second Brain Link plugin

Run a whole job hunt from Claude Code — or from inside Second Brain Studio, against your own
second brain. It sweeps the market against **your** criteria, tailors a CV for each role it
shortlists, fills the employer's application form, and keeps everything as an indexed layer
of your vault.

**Nothing about any particular person is in this plugin.** Your career facts, criteria and
settled application answers live in seven Markdown files that `/onboard` writes into your own
vault or working folder, and every skill reads them from there.

## Install

The plugin is maintained in ONE place — this repo — and installed from here, the same way
the engine skill is. Nothing bundles a copy of it, so what you install is what runs.

**Claude Code** — install it once:

```bash
python3 packaging/build_plugin.py job-search --provider claude --install
#   -> ~/.claude/skills/job-search
```

Claude Code loads a plugin folder placed there as a **skills-directory plugin** — it
appears in `claude plugin list` as `job-search@skills-dir` — and Second Brain Studio reads
the same location, so this one install serves the CLI and both Studios.

If you are working on the plugin itself, link the checkout instead so edits are live:

```bash
ln -s "$PWD/plugins/job-search" ~/.claude/skills/job-search
```

`--install` will not overwrite that link. For a one-off run without installing anything:

```bash
claude --plugin-dir /path/to/second-brain-link/plugins/job-search
```

A marketplace install works too — Studio reads `installed_plugins.json` as well.

**OpenAI Codex** — build and install the flattened skill:

```bash
python3 packaging/build_plugin.py job-search --provider openai --install
#   -> ~/.agents/skills/job-search
```

Nothing bundles a copy: the desktop app and a locally-run browser Studio both read the
install above and show it as the **Jobs Agent** in the Agents tab. Whichever route you
use, the plugin lives in exactly one place on disk.

Or build both distributable archives:

```bash
python3 packaging/build_plugin.py job-search
#   -> dist/plugins/claude/job-search.zip
#   -> dist/plugins/openai/job-search.skill
```

In Second Brain Studio the plugin is loaded for you — pick **Jobs Agent** in the Agents tab.

> **The Codex packaging is narrower, on purpose.** Codex has no browser tooling, so it runs
> onboard → scout → score → tailor → log and hands you the prepared application to submit
> yourself. The sweep and the CV work — the slow parts — are identical.

Then:

```
/onboard      # builds your profile from a CV, a Second Brain vault, a LinkedIn export, or a chat
/jobs         # the daily run: sweep -> score -> tailor -> apply
/kpi          # the number that matters: interviews won, and the interview rate
              #   plus the daily pace: valid applications vs `daily-target:` (default 10)
/outcome      # paste a reply or rejection — it is logged against the right application
/report       # re-render the dashboard
```

## The five skills

| Skill | Does |
|---|---|
| `job-onboarding` | Writes your profile — the operating prompt every other skill reads |
| `job-scout` | Sweeps open ATS boards and public search, scores against your criteria, delivers a ranked shortlist you can actually apply to |
| `cv-tailor` | Builds a tailored, ATS-first CV as Markdown and PDF, from your profile only |
| `job-apply` | Classifies the portal, fills the form, logs every answer given |
| `job-pipeline` | Sequences the other four and holds whatever gates your autonomy setting calls for |

## How it tries to win interviews, not just send applications

Fast, generic rejections usually come from an automatic rule, not a person: a "No" to *right to
work in <country>*, a location outside the posting's, a required language, a salary figure off
the band. After those, the causes are a job the candidate was never going to be shortlisted for,
and a CV or answer that reads as generated. Each has a gate:

| Gate | Where | Stops |
|---|---|---|
| **Knock-out screen** | `job-apply/scripts/knockout.py`, run by the scout and again on the form's own questions | jobs the truthful answer disqualifies — before a CV is written |
| **Archetypes + shortlist likelihood + apply floor** | `profile/archetypes.md`, `job-scout/references/scoring-rubric.md` | roles outside your lanes, and roles a recruiter would not shortlist you for |
| **Fit file** | `<application>/fit.md` | a CV built from anything but evidence for the JD's actual requirements |
| **CV and answers lint** | `cv-tailor/scripts/lint_cv.py` | dates out of order, a named gap, first person, banned phrases, "not just X but Y", numbers or titles not in your profile, placeholders in a form answer |
| **Independent recruiter review** | job-apply step 4b — one small model, no tools | anything a hiring manager would not shortlist; only `shortlist` is submitted autonomously |

`learn.py log-outcome --status applied` refuses to record a submission unless all three
recorded gates in `gates.json` are green. And the loop only learns if results come back —
`/outcome` records them, `learn.py calibrate` shows whether the score predicts replies.

## Where your data lives

Never inside this plugin folder, and never inside the repository it ships in. The state root is
resolved by `skills/job-scout/scripts/paths.py`, in this order:

| Order | Location | When |
|---|---|---|
| 1 | `$JOB_SEARCH_HOME` | you set it explicitly |
| 2 | `<brain>/45-jobs/_state/` | **legacy** — an install from before the move, still using it |
| 3 | `<brain>/.plugins/job-search/` | you are running inside a Second Brain vault |
| 4 | `<working folder>/45-jobs/_state/` | a ledger already exists there |
| 5 | `~/.second-brain/job-search/` | fresh install |

The in-brain location is **dot-prefixed on purpose**: Obsidian and Second Brain Studio both skip
dot-folders, so your ledger travels with the brain — move it, sync it, back it up and the
application history comes along — without sitting in the tree beside the notes you actually read.

Upgrading from an older install? One command moves everything into the current layout, printing
every move and deleting nothing:

```bash
python3 skills/job-scout/scripts/render_brain.py --migrate-layout --dry-run   # see what it would do
python3 skills/job-scout/scripts/render_brain.py --migrate-layout             # do it
```

```
<state root>/       the ledger — what you have seen, applied to, and heard back
<surface>/45-jobs/  the rendered layer: dashboard, one note per application, CVs, shortlists
  profile/          your criteria and career facts
```

Inside a Second Brain vault the `45-jobs/` layer is written into the brain, with the frontmatter
and wikilinks that make it index, search and graph like every other layer. Application notes link
`[[Company]]`, so an application lands in the graph next to the people you know there.

**Your ledger never forks.** `seen.json` and `outcomes.jsonl` live in one place regardless of
which surface you run from — that is what stops the scout showing you a job you already applied to.

Run `python3 skills/job-scout/scripts/paths.py` to see every decision it made.

## What it will not do

- **It does not submit without you — unless you tell it to.** Out of the box the level is
  `supervised`: it fills the form and clicking submit is yours, every time. Set
  `level: autonomous` in §0 of your `application-answers.md` and it will submit on your behalf,
  after reading every required field back from the DOM. That is a deliberate one-word change to
  your own profile, never a default and never inferred from how you phrased a request.
- **It never types a credential** — no passwords, passport or identity numbers, payment details.
  This holds at both levels.
- **It never invents a fact.** If something is not in your profile it asks; at `autonomous`, where
  there is nobody to ask, it skips that job and says why rather than guessing. Prose it *writes* —
  a "why this company" answer — is composed from your profile every time, and is not a fact it
  could invent.
- **It never writes a job title you did not hold.** Your profile carries a closed list of allowed
  variants per role, and the CV builder may not go outside it.
- **LinkedIn only if you turn it on.** Onboarding asks. With it on, the scout reads LinkedIn's
  public, no-login job search — no account is used, so nothing touches yours — slowly, with a
  request cap, stopping when throttled; LinkedIn's terms discourage automated reading, which is why
  it is your choice. It never applies, messages or logs in there: every posting is resolved to the
  employer's own site, which is where you should apply anyway.
- **It searches each market where that market posts** — LinkedIn, regional boards and recruiters,
  then every hiring company's own careers board — and a coverage check refuses to call a market
  empty until several sources agree.
- **It never creates an account.** Jobs on portals that need one (Workday, SuccessFactors) are kept
  on your shortlist with the CV and answers ready for you to apply there, filled in the run with
  you doing only the account, password and e-mail-code steps (`walled: assist`), or left out, if
  you prefer (`walled: drop`).
- **It identifies itself honestly** to every endpoint it calls, and only calls public ones.

## What changed

**1.6.0** — the CV's look is a setting:
- Studio → Jobs Agent → Settings now has a **CV design** tab with four templates (Band, Minimal,
  Executive, Classic) shown as live miniatures, six palettes plus "from my photo", "match each
  employer" and a custom accent, and the photo: when to use it and its shape (square, rounded,
  circle). It is saved as `45-jobs/profile/style/cv-style.json`, and every CV follows it unless you
  ask otherwise in a run.
- The builder adds the **Minimal** and **Executive** templates and the photo shapes, and reads the
  settings file on every build (`from=settings` in its summary line).
- The settings dialog itself is redesigned: tabs, template cards, swatches, a photo row with a
  live preview, file cards, inline delete confirmation, a sticky Save.

**1.5.0** — a designed CV, and a photo when the market expects one:
- `build_cv.py` now renders the **designed** template by default (`cv_designed.py`). It has a dark
  header band with an optional square photo, a serif name and headings, a dated timeline with ring
  markers, a "Name, Headline · n / total" footer, six palettes or one taken from the photo, and a
  "Company, continued" label at a forced page break. `--template classic` keeps the plain layout.
- Fonts ship in the plugin: Fraunces and IBM Plex Sans, SIL OFL, subset-embedded. The PDF opens
  and parses anywhere with nothing installed. A CV with a photo is about 90 KB, because the photo
  is resampled and stripped of its metadata.
- Studio → Jobs Agent → Settings has a new **Your CV photo** upload. Studio shrinks the photo to
  800 px JPEG and drops its location data before it is saved in `45-jobs/profile/photo/`.
- The photo and personal data follow the market (`market:` in the CV frontmatter). `lint_cv.py`
  fails a date of birth, marital status, religion or ID number, fails stat-tile lines, and warns on
  a photo for US/UK/CA/AU/IE. `check_pdf.py` fails a file over 1 MB, any font that isn't embedded,
  a Type3 font, spaced-letter headings and a broken name → headline → contact order.
- New `references/designed-template.md`: layout, palette, the photo policy, and the three reviews
  (recruiter, ATS import, designer) that every CV gets before delivery.

**1.4.0** — lessons from a month of real daily runs, generalised:
- `knockout.py` no longer stops on negated requirements ("X is not required"), benefit lines read
  as salary, localisation duties read as a nationality gate, or another listing's text on an
  aggregator page; it separates a **salary floor** (drop) from a **salary target** (rank), and finds
  the profile from any working folder.
- ATS freshness uses each provider's real publish date (Greenhouse `first_published`, Lever
  `createdAt`); the open pool adds SmartRecruiters, Recruitee and Personio, flags multi-city rows,
  and has a `--diagnose` mode for slugs.
- CV notes show plain links in Studio; `build_cv.py --no-render` for parallel builders; the CV lint
  accepts the target title in the summary's first sentence when a headline would read as copied.
- New settings, cautious by default: `fill-mode`, `filler-model`, `review-rounds`, `when-stuck`,
  `reviewer-ignore`, `walled: assist`, `name-clients`, contact sets by job location, `salary_target`,
  standing form defaults and consents (§5b/§5c).
- New *Career Evidence — confirm* note; sourcing, LinkedIn-pace, attestation, consent and form-trap
  rules throughout the skills; working files in the state root, never `/tmp`.

## Requirements

Python 3.9+ · `reportlab` for PDFs (`pip install -r requirements.txt`; Pillow comes with it and
resamples the CV photo; the fonts are bundled) · Claude Code with the
Chrome extension for the apply half. The scout and the CV builder work without Chrome; without
`reportlab` the CV is produced as Markdown and the PDF step is skipped with a notice.

MIT licensed.
