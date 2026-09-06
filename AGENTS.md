# AGENTS.md — Second Brain Link (OpenAI / cross-agent guide)

This is the OpenAI-facing twin of `CLAUDE.md`. Second Brain Link is a **cross-model
Agent Skill**: one shared, provider-neutral Python **engine** plus thin
per-provider manifests. Read this before editing if you're an OpenAI agent (Codex);
read `CLAUDE.md` for the full project context (architecture, privacy, gotchas) —
it applies to every provider.

## Layout (engine once; providers thin)
- `engine/scripts/` — the single source of truth (build_vault, profile_export,
  mapping, harvester, correlate, analyze, diagrams, selfheal, new_source,
  `sources/personal/*`, `sources/company/*`, `emitters/*`).
- `engine/mappings/` — declarative `sources/<name>.json` (interpreted by
  `mapping.py`) + `brain/layout.json` (folder/route table; adds an `85-places/`
  layer). `engine/references/blueprint.md` = full data model.
- `providers/claude/SKILL.md`, `providers/openai/SKILL.md` (+ `agents/openai.yaml`)
  — manifests (Agent Skills open standard; same format, only wording + the in-vault
  guide differ).
- `packaging/build_skill.py [claude|openai|all] [--install]` — assembles `engine/`
  + a provider manifest into `dist/<provider>/second-brain-link(.skill)`; `--install`
  copies into the agent discovery dirs.

## Non-negotiables (same as CLAUDE.md §2)
- Local-first, zero network in the core (only opt-in `--gbrain-import` may reach out).
- Privacy enforced in CODE at the `Collector` boundary; `--full` is owner-only.
- Deterministic core; AI only on the residual (unknown-file mapping, synthesis
  enrichment, self-heal on `_ERROR.md`).
- A source = a **JSON mapping** (preferred, `mappings/sources/<name>.json`,
  mapping-wins over a same-named adapter) or a Python adapter
  (`sources/personal|company/`, auto-discovered); an output = one emitter file
  (`emitters/`). Files nothing claims are rescued by the **universal harvester**
  (`harvester.py`) and flagged in `_COVERAGE.md` — nothing silently dropped.

## Provider + the in-vault guide
- `build_vault.py --provider openai` writes an **`AGENTS.md`** guide into the built
  vault; `--provider claude` writes `CLAUDE.md`. Same guidance, different addressee.
- `--subject person|company` (auto by default); a mixed single export builds **two
  sibling vaults** (`personal-brain/` + `company-brain/`).

## Multiple identities + companies (named entities)
Organize exports as `data/personal/<identity>/<source>/…` and
`data/company/<company>/<source>/…` — **the folder name is the entity**. The builder
makes one brain per entity (`vault/personal/<id>-brain/`, `vault/company/<co>-brain/`)
and, when ≥2 entities are present, a `vault/_correlations/` brain linking the same
person across brains, shared orgs, and `works_at` edges (people matched by name +
profile URL; precision-biased). `personal`/`company` separation is consistent across
`sources/`, `data/`, `tests/fixtures/`, and the vault output. This OpenAI skill is
discovered from `.agents/skills/` (repo) or `~/.agents/skills/` (user) and ships an
`agents/openai.yaml`.

## Activate for goals + operate the brain
After building, **ask the user their goals** and run
`python3 engine/scripts/analyze.py <brain> --goals fundraising,bd,jobsearch,datamining,personalization
[--icp …] [--thesis …] [--copilot-dir …] [--graph-config <vault>/.obsidian/graph.json]` —
deterministic, re-runnable over the built brain. It writes `95-goals/<goal>.md` (ranked
tables + a ready AI prompt; `datamining` = network patterns, `personalization` =
recommend-me-X grounded in places/interests/mirror, the cold-start solver), `Dashboard.md`
(tag-based Dataview incl. a by-source table), **`_DATA_POINTS.md`** (catalog of every node
type + relation + which source enriched each field), **`_GRAPH.md`** + `--graph-config`
(colors the global graph by source + type, merging non-destructively into
`.obsidian/graph.json`), and `copilot-prompts/` (incl. `/mine`, `/for-me`). A `GOALS`
registry in `analyze.py` maps goal keys to builders — add one to support a new goal.
Leverage layers to surface: Dataview/Bases dashboards + `_DATA_POINTS.md` · the cross-source
**Graph** (every note tagged `source/<name>` + type; see `_GRAPH.md`) · Obsidian Copilot
(Vault-QA + the generated `/commands`) · an AI agent (reads `_STRUCTURE.md`+`_SUMMARY.md`+
`_DATA_POINTS.md`+synthesis, not all notes) · Map View/Graph plugins (`85-places/` carry lat/lng).

## Self-improve on every new source
Integrating a new source (or export version) should ratchet the whole system: close
`_COVERAGE.md` "Needs a mapping" with a mapping (add an `emit` like `mirror`/`ad_segment` if
a new data class appears) → re-review the brain **structure** (`_STRUCTURE.md` /
`engine/mappings/brain/layout.json`) → re-review the **data points** (`_DATA_POINTS.md`
field-enrichment-by-source matrix lights up new cells) → ensure the new notes are
`source/<name>` + semantically tagged so they join the graph → re-run `analyze.py` → update
the status table + add a fixture/test. See `providers/*/SKILL.md` for the full loop.

## Keep the engine canonical & in sync
The engine is the source of truth. After editing `engine/`, rebuild the installable(s)
with `python3 packaging/build_skill.py all` (or `… all --install` to copy into the
provider discovery dirs), and keep `tests/run.py` green (`python3 tests/run.py`).
Never fork the engine per provider.

## Plugins

`plugins/` is a separate surface from `engine/`. The engine BUILDS a brain (deterministic,
stdlib-only, zero network); a plugin USES one to do work and may reach the network if its
`.claude-plugin/plugin.json` declares it. `packaging/build_skill.py` never bundles
`plugins/` — that is what keeps the engine's zero-network claim true of everything the
skill ships. Build plugins with `packaging/build_plugin.py` (`--provider claude|openai|all`);
the Codex packaging is a FLATTENED single skill installed to `~/.agents/skills/`.

A plugin must never write user data inside the plugin folder or this repository, never
hardcode a vault layer folder, and never ship anything personal. See `plugins/README.md`.
