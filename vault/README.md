# `vault/` — your generated second brain lands here

This is the suggested output location for the vault(s) the builder creates. Like
`data/`, **everything here is git-ignored** (except this README), so your
personal second brain is never committed.

## How it gets created

The builder refuses to write into a non-empty folder (so it never clobbers
existing notes) — generate into a **fresh** location.

```bash
# Multiple entities under data/ → one brain per entity (+ correlations)
python3 engine/scripts/build_vault.py data -o vault

# A single source folder → one brain in a fresh subfolder
python3 engine/scripts/build_vault.py data/personal/<you>/linkedin -o vault/my-brain
```

(Run from the repo root. Or just ask your agent — with the skill installed —
"build my second brain from the data/ folder.")

Pointing at the `data/` root produces one brain per discovered entity, plus a
cross-entity correlations brain when ≥2 entities are present:

```
vault/
├── personal/<you>-brain/        ← rooted on 00-me/ (a digital twin)
│   ├── Home.md                  ←   START HERE
│   ├── CLAUDE.md / AGENTS.md    ←   in-vault guide (navigation + privacy)
│   ├── 00-me/ 10-people/ 15-organizations/ … 85-places/ 90-synthesis/
│   ├── _COVERAGE.md             ←   what was imported (+ "Needs a mapping")
│   └── _BUILD_REPORT.md
├── company/<your-company>-brain/  ← rooted on 00-org/ (a Company Brain)
└── _correlations/               ← same person across brains, shared orgs, works_at edges
```

A single-source build writes one self-contained vault into the subfolder you name
(e.g. `vault/my-brain/`).

## How to use it

1. **Obsidian:** *File → Open folder as vault →* pick a brain folder (e.g.
   `vault/personal/<you>-brain/`). Open **`Home.md`** first, then **Graph view**
   to see your network.
2. **Your coding agent / Obsidian MCP:** point it at the brain folder. The bundled
   `CLAUDE.md` (Claude) or `AGENTS.md` (OpenAI) makes it navigate efficiently out
   of the box.

_This README is a placeholder so the folder exists in the repo; the generated
vault you create here is ignored by git._
