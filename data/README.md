# `data/` — drop your exports here

This is where your downloaded data archives go. **Everything you put in here is
git-ignored** (except these README files), so your personal data is never
committed or pushed — see the repo's `.gitignore`.

## Layout — organize by entity

An **entity** is one named identity or company. The **folder name *is* the entity
name** (it's authoritative; names/URLs inside the files are only used to correlate
across entities). Put each source export in its own subfolder under the entity:

```
data/
├── personal/                       # digital twins (one folder per identity)
│   ├── your-name/                  # ← TEMPLATE: rename to your real name
│   │   ├── linkedin/               #   your LinkedIn export
│   │   ├── facebook/               #   your Facebook export (JSON)
│   │   ├── instagram/              #   your Instagram export (JSON)
│   │   └── google/                 #   your Google Takeout export
│   └── <someone-else>/…            # another identity → its own brain
└── company/                        # Company Brains (one folder per company)
    └── your-company/               # ← TEMPLATE: rename to your real company
        ├── linkedin_company/       #   LinkedIn company export (CSV)
        ├── google_workspace/       #   Workspace export (mixed)
        └── slack/                  #   Slack export (JSON)
```

This repo ships those two folders — `personal/your-name/` and
`company/your-company/` — as **templates** (source subfolders + READMEs) so the
layout is obvious. **Rename each to your real name / company**, then drop your
exports in. While a folder holds only READMEs it's **skipped** by entity discovery,
so it's harmless to leave in place until you add data. (Folders beginning with `_`
or `.` are also always skipped — handy for notes/templates.)

You only need to fill the folders for the source(s) and entit(ies) you have — one
identity with one source is fine; several of each is fine.

## How to use it

**Multiple entities → per-entity brains + correlations.** Point the builder at the
whole `data/` root. It discovers every named entity and builds one brain each, plus
a cross-entity `_correlations/` brain when ≥2 entities are present:

```bash
python3 engine/scripts/build_vault.py data -o vault
#   → vault/personal/<you>-brain/        (rooted on 00-me/)
#     vault/company/<your-company>-brain/ (rooted on 00-org/)
#     vault/_correlations/                (same person across brains, shared orgs, works_at edges)
```

**One source at a time.** Point the builder straight at a single source folder:

```bash
python3 engine/scripts/build_vault.py data/personal/<you>/linkedin -o vault/my-brain
```

> You don't have to unzip — the tool also reads a `.zip` directly
> (`build_vault.py data/personal/<you>/linkedin/MyExport.zip -o vault/my-brain`).
> Unzipping into these folders is just the tidiest way to keep sources organized.

## Tip: preview before building

See what was detected without writing anything:

```bash
python3 engine/scripts/build_vault.py data --dry-run
```

Or, in Claude Code / OpenAI Codex / the Claude app with the skill installed, just
say:
> *"Build my second brain from the exports in the data/ folder."*

## Privacy reminder

Third-party emails/phones and message bodies are never written into the vault —
that's enforced in the code (`--full` owner mode keeps your *own* data; the default
stays privacy-safe). But the **raw exports in this folder still contain that data**,
so keep `data/` out of any public repo (the `.gitignore` already handles this) and
don't share it.
