# job-search — the first Second Brain Link plugin

Run a whole job hunt from Claude Code — or from inside Second Brain Studio, against your own
second brain. It sweeps the market against **your** criteria, tailors a CV for each role it
shortlists, fills the employer's application form, and keeps everything as an indexed layer
of your vault.

**Nothing about any particular person is in this plugin.** Your career facts, criteria and
settled application answers live in five Markdown files that `/onboard` writes into your own
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
/kpi          # the only number that matters: applications actually submitted
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
- **It never touches LinkedIn.** Its User Agreement forbids automated access and enforcement lands
  on your account, so this plugin does not search it at all. Job URLs that reach you another way
  are resolved to the employer's own form first, which is where you should apply anyway.
- **It never creates an account**, so portals that require one are excluded from your shortlist
  rather than wasting a slot in it.
- **It identifies itself honestly** to every endpoint it calls, and only calls public ones.

## Requirements

Python 3.9+ · `reportlab` for PDFs (`pip install -r requirements.txt`) · Claude Code with the
Chrome extension for the apply half. The scout and the CV builder work without Chrome; without
`reportlab` the CV is produced as Markdown and the PDF step is skipped with a notice.

MIT licensed.
