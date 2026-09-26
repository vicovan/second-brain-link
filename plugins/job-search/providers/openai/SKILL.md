---
name: job-search
description: Run a job hunt from your own career profile — sweep open ATS boards for roles that match your criteria, score and shortlist them, build a tailored ATS-first CV as Markdown and PDF for each, and keep the whole pipeline as an indexed layer of your Second Brain vault. Use for the daily job scan, "any good jobs today", "tailor my CV for this role", "set up my job search", or a fresh sweep of the market. Nothing personal is built in — every fact comes from a profile this skill writes with you on first run.
---

# job-search — the whole hunt, from your own profile (OpenAI)

> This is the **OpenAI/Codex packaging** of the Second Brain Link `job-search` plugin.
> The scripts are byte-identical to the Claude packaging; only this manifest and the
> layout differ. Codex installs one self-contained skill, so everything lives here:
> workflows in `references/`, code in `scripts/`.

**Nothing about any particular person is in this skill.** Your career facts, criteria
and settled application answers live in seven Markdown files under
`<surface>/45-jobs/profile/`, which `references/job-onboarding.md` writes with you.
Read them; never assume them, never invent them.

## What differs from the Claude packaging — read this first

Codex has no browser-automation tools, so **this packaging does not fill web forms.**
It runs: **onboard → scout → score → shortlist → tailor a CV → log**, and then hands
you the application with the CV and every answer prepared. You submit. That is the
honest boundary, and it is most of the value: the sweep and the tailoring are the slow
parts.

**`level: autonomous` therefore means something narrower here.** The setting in §0 of
`profile/application-answers.md` still removes the pick and CV gates, and free text is still
composed rather than asked about — but there is no submit gate to remove, because there is no
submit. On this packaging `autonomous` covers discovery, tailoring and the record; the last
step is yours whatever the setting says.

Everything else — the ledger, the scoring, the vault layer, the CV builder — is the same.

## The five workflows

Read the one you need, in full, before acting. They are the real instructions; this
file only routes.

| Workflow | Read | When |
|---|---|---|
| Onboarding | `references/job-onboarding.md` | First run, or no `45-jobs/profile/` exists, or criteria changed |
| Daily sweep | `references/job-scout.md` | "any good jobs today", the daily scan, a fresh market search |
| CV tailoring | `references/cv-tailor.md` | A job description is shared, or "tailor my CV for this" |
| Applying | `references/job-apply.md` | The user picks a role — follow it up to the form, then hand off |
| End to end | `references/job-pipeline.md` | "run my job pipeline" — sequences the other four |

Supporting references: `references/sources.md` (where to look, and what not to retry),
`references/scoring-rubric.md` (the 100-point method), `references/search-method.md`,
`references/tailoring-playbook.md` (the CV rewriting moves), `references/ats-checklist.md`,
`references/field-policy.md` (what may never be typed into a form),
`references/profile-template.md` / `criteria-template.md` / `answers-template.md` /
`archetypes-template.md` / `stories-template.md`.

**The recruiter review (job-apply step 4b) has no subagent here.** Do it as a separate pass:
read only `posting.md`, the CV Markdown and `answers.json` — not `fit.md` or your own notes —
answer as the hiring manager in the step's JSON shape, and record the verdict with
`lint_cv.py review`. Because this packaging never submits, the user logs the submission; if they
send one whose gates are not green, `learn.py log-outcome --status applied --force-gates "<reason>"`
records that honestly.

## Scripts

All paths are relative to this skill folder. Run them with `python3`.

```bash
python3 scripts/paths.py                    # where everything resolves — run this first when unsure
python3 scripts/scout_state.py stats        # daily gate, dedupe, report path
python3 scripts/learn.py kpi                # the north star — interviews, and the interview rate
python3 scripts/learn.py calibrate          # does the score predict replies?
python3 scripts/learn.py set-result --job-key K --result rejected   # feed outcomes back
python3 scripts/knockout.py --jd posting.txt       # auto-reject questions, before any CV
python3 scripts/lint_cv.py cv <cv.md> --profile <profile.md> --fit <fit.md>   # the CV gate
python3 scripts/lint_cv.py answers <answers.json>  # the answers gate
python3 scripts/lint_cv.py review <app dir> --verdict shortlist|maybe|reject
python3 scripts/learn.py show               # lessons earned from real outcomes
python3 scripts/ats_pool.py --titles "…" --domain "…" --regions "…"   # Tier 0 bulk board probe
python3 scripts/ats_fetch.py auto <slug>    # one company's board
python3 scripts/detect_portal.py <url> --fetch   # fillable / walled / aggregator
python3 scripts/build_cv.py <cv.md> --out <dir>  # Markdown + PDF (needs reportlab)
python3 scripts/check_pdf.py <cv.pdf> --keywords "a;b"
python3 scripts/find_brain.py --verbose     # locate the user's vault
python3 scripts/render_brain.py --quiet     # render the 45-jobs layer into the vault
```

**Pass the user's own criteria into `ats_pool.py`.** Its defaults filter on nothing but
job-type noise, deliberately — so that it never applies one person's lanes to somebody
else. Build `--titles` / `--domain` / `--regions` / `--exclude-titles` from
`profile/search-criteria.md`, and use word boundaries (`\bai\b`, not `ai`, which also
matches "Retail").

## Where your data lives

**Never inside this skill folder.** `scripts/paths.py` resolves a state root:
`$JOB_SEARCH_HOME` → `<brain>/45-jobs/_state/` (legacy only, if it already exists) →
`<brain>/.plugins/job-search/` → `<working folder>/45-jobs/_state/` →
`~/.second-brain/job-search/`. Dot-prefixed inside a brain so it travels with the vault
without showing up in the tree. The rendered layer (`45-jobs/`) goes into the user's
Second Brain vault when running inside one, otherwise the working folder.

Upgrading an older install: `python3 scripts/render_brain.py --migrate-layout` moves the
ledger to the new location and files applications by day. It prints every move and deletes
nothing; add `--dry-run` to see it first.

## Non-negotiables

- **Never submit anything.** This packaging cannot, and must not pretend to.
- **Never type a credential** — no passwords, passport or national identity numbers,
  payment details. See `references/field-policy.md`.
- **Never invent a fact.** Not in the profile → ask.
- **Never write a job title the user did not hold.** The profile carries a closed list
  of allowed variants per role; the CV may not go outside it.
- **Never touch LinkedIn.** Its User Agreement forbids automated access and enforcement
  lands on the user's account. Discovery is the public Greenhouse/Lever/Ashby APIs and
  web search.
- **Never write outside `45-jobs/`** in the vault, except the report mirror that
  `scripts/publish_report.py` places in `_notes/job-pipeline/`.
