# What does this PR do?

<!-- One or two sentences. If it adds a source, name it. -->

## Type

- [ ] New data source (one adapter file)
- [ ] Mapping-gap / drift fix on an existing source
- [ ] Builder / profiler / visualization improvement
- [ ] Docs

## Checklist (all must hold)

- [ ] **Local-first**: no network calls, no telemetry, **stdlib-only** (Python 3.8+).
- [ ] **Privacy in code**: no third-party emails/phones written; message **bodies
      never read** (only `col.add_message_signal`); sensitive files added to the
      source's quarantine set. Visualizations use column names only, never cells.
- [ ] **Nothing silently dropped**: unrecognized files still route to
      `99-uncategorized/`.
- [ ] **Mapping-first** (preferred for a new source): a JSON mapping under
      `engine/mappings/sources/<name>.json` (no Python) — `detect` + `records[]`.
- [ ] **Adapter contract** (only when Python is warranted): `NAME`, `detect()`,
      `extract(root, file_index, all_paths, col)`; pushes via `col.add_*`; dropped
      into `engine/scripts/sources/personal/` or `…/company/` (auto-discovered, no
      registry edit).
- [ ] **Synthetic fixture added** under
      `tests/fixtures/<personal|company>/<entity>/<source>/` (never a real export)
      and `python3 tests/run.py` is green.
- [ ] **Obsidian invariants** hold: valid YAML, links resolve, ISO dates
      (the harness checks these).
- [ ] **Engine kept canonical**: edited `engine/` (the single source of truth),
      then re-packaged + installed with
      `python3 packaging/build_skill.py all --install`. Docs (`providers/*/SKILL.md`,
      `CLAUDE.md`, `README.md`) updated as needed.
- [ ] **One source per PR.**
- [ ] Commits signed off (`git commit -s`); contribution is MIT-licensed.

## PII-safe notes (optional)

<!-- Paste any schema_map.md excerpt that motivated the change. Never raw data. -->
