---
name: second-brain-link
description: Turn a personal OR company data export — LinkedIn, Facebook, Instagram, Google Takeout, LinkedIn Company, Google Workspace, Slack — into a private, local, queryable "digital twin" or Company Brain for your OpenAI agent (Codex). Self-adapting — detects which export(s) you have, profiles every file and column, and normalizes them into one canonical graph, merging people seen in more than one source. Default output is an Obsidian vault (with an AGENTS.md guide); it can also emit a GBrain repo (--emit gbrain|both). Use whenever the user points at a data export (.zip or folder), or says things like "build my second brain from my LinkedIn data", "bootstrap a company brain from our Workspace/Slack export", "turn my download into an Obsidian vault", "map my export", or "import my data into GBrain". Trigger even without the words "Obsidian", "GBrain", or "second brain" — any request to process, profile, or build a knowledge base from a personal or company archive. New sources/outputs are drop-in.
---

# Second Brain Link — multi-source digital-twin / Company Brain (OpenAI)

Build ONE unified, private, Obsidian-native vault (or a GBrain repo) from any
supported data export so the user (and their OpenAI agent, e.g. Codex) can reason
over their professional/social history — or a company's. Everything runs locally;
nothing is uploaded (the only opt-in networked step is `--gbrain-import`).

> This is the **OpenAI** packaging of the cross-model Agent Skill. The Python
> engine is identical to the Claude packaging — only this manifest and the
> in-vault guide differ. **Always pass `--provider openai`** so the engine writes
> an `AGENTS.md` guide into the vault (Claude builds write `CLAUDE.md`).

## Architecture (read before running)

Sources are **drop-in adapters** under `scripts/sources/personal/` (linkedin,
facebook, instagram, google) and `scripts/sources/company/` (linkedin_company,
google_workspace, slack). Each knows one export's format (CSV/JSON/ICS) and pushes
records into one canonical `Collector` (`scripts/sources/common.py`). Output
targets are **drop-in emitters** under `scripts/emitters/` (obsidian = default,
gbrain = opt-in). The builder (`scripts/build_vault.py`) renders from the
collector, so multiple sources merge into one graph and **a person seen in more
than one source becomes one note tagged with each**.

**Deterministic core, AI only on the residual:** detection, parsing, the whole
vault, the mindmap, and entity resolution run with zero API tokens. Spend
intelligence only on (a) mapping genuinely unknown files via a tiny overrides
file, (b) optionally enriching the two synthesis drafts, (c) self-heal (acting on
a structured `_ERROR.md`). **Read `schema_map.md` + `_COVERAGE.md`, never the raw
files or thousands of notes.**

The scripts (run with `python3`):
- `scripts/profile_export.py "<export>" --out "<vault>/_profile"` — detects
  source(s); writes `schema_map.json/.md`, a **mindmap** (`<source>_mindmap.md` +
  `.canvas`), and a **brain-structure design** (`brain_structure.md/.canvas/.json`).
  PII-safe (column names only). Flags: `--no-mindmap`, `--no-structure`, `--doctor`.
- `scripts/build_vault.py "<export>" -o "<vault>/<name>-brain" --provider openai`
  — runs adapters, renders the vault, writes `_COVERAGE.md` + `_BUILD_REPORT.md`
  + `_SUMMARY.md` (seed counts: per-layer note counts + coverage line; a top-level
  `vault/_SUMMARY.md` indexes all entity brains) (+ `AGENTS.md` guide). Flags:
  `--structure`, `--overrides`, `--subject
  person|company` (default auto), `--emit obsidian|gbrain|both` (default
  obsidian), `--full`, `--doctor`, `--gbrain-import`, `--mappings <dir>`.
- `scripts/diagrams.py`, `scripts/selfheal.py`, `scripts/new_source.py`,
  `scripts/mapping.py` (JSON-mapping interpreter), `scripts/harvester.py`
  (universal shape recognizer) — support.

**Self-adapting sources.** Most sources are declarative JSON under
`mappings/sources/<name>.json` (no Python). Files no source claims are rescued by
the universal harvester (people/places/posts/interests/message-signal) so nothing
is lost, and listed in `_COVERAGE.md` under **"Needs a mapping"**. To self-adapt:
add a mapping rule (or a `--mappings <dir>` override) — selectors handle nested
shapes like `string_list_data[].value` and `features[].properties.location.name`; a
rule's `emit` picks a canonical verb (person/org/post/interest/place/event/search/
message_signal/identity/**mirror**/**ad_segment**), and a rule may declare semantic
`tags` (e.g. `person/friend`) that join the automatic `source/<name>` + type tags on
every note. A mapping overrides a same-named Python adapter. Enables layers like
**`85-places/`** (Maps/check-ins) and **`50-mirror/`** (ad-interests/advertisers via
the mirror emit). The full self-improvement loop is in step 6b.

## Workflow

1. **Locate the export** (`.zip` or folder; may be combined / multi-source). For
   **multiple identities/companies**, organize as `data/personal/<identity>/<source>/`
   and `data/company/<company>/<source>/` (folder name = entity) and point the
   builder at the `data/` root: it builds one brain per entity under
   `vault/personal/<id>-brain/` + `vault/company/<co>-brain/`, plus a
   `vault/_correlations/` brain (cross-person notes, shared orgs, `works_at` edges)
   when ≥2 entities are present.
2. **Profile** → read `<vault>/_profile/schema_map.md`, show the user the mindmap +
   brain-structure design.
3. **Adapt** only if the map flags unknowns → write `mapping_overrides.json`.
4. **Build** with `--provider openai` (+ `--subject`/`--emit`/`--full` as needed).
   - **Personal + company sources in one export → two sibling vaults**:
     `personal-brain/` (rooted `00-me/`) and `company-brain/` (rooted `00-org/`).
   - `--emit both` writes Obsidian + a GBrain repo under separate subdirs.
5. **Verify** `_COVERAGE.md` (+ `_SUMMARY.md` for the seed counts at a glance);
   refine overrides + rebuild into a fresh dir (cap ~3). On a non-zero exit, read
   `_ERROR.md`, apply the smallest fix to the named script, mirror it, re-run
   (self-heal protocol).
6. **Activate for the user's GOALS** (where the value is): **ask what they want to use
   it for** (fundraising · sales/BD · job-search · **datamining** · **personalization** ·
   hiring · reconnect · positioning · travel), then `python3 scripts/analyze.py
   "<vault-dir>" --goals fundraising,bd,jobsearch,datamining,personalization [--icp …]
   [--thesis …] [--copilot-dir …] [--graph-config "<vault>/.obsidian/graph.json"]`.
   Deterministic + re-runnable over the built brain; writes `95-goals/<goal>.md` (ranked
   tables + a ready prompt; `datamining` = network patterns, `personalization` =
   recommend-me-X grounded in places/interests/mirror, solving cold-start), `Dashboard.md`
   (tag-based Dataview incl. a by-source table), **`_DATA_POINTS.md`** (catalog of every
   node type + relation + which source enriched each field — always written), **`_GRAPH.md`**
   + `--graph-config` (colors the global graph by source + type; preserves the user's
   `.obsidian/graph.json`, writes a `.bak`), and `copilot-prompts/` (`/warm-intro`,
   `/investor-paths`, `/reconnect`, `/job-fit`, `/ask-my-network`, **`/mine`**, **`/for-me`**).
   Then act on the prompts in the user's voice.
6b. **Self-improve on every new source (the loop).** When a new source/export version is
   integrated, ratchet the whole system: (1) profile → schema map flags new files/fields;
   (2) close `_COVERAGE.md` "Needs a mapping" by extending the mapping, adding an `emit` if a
   new data class appears (as `mirror`/`ad_segment` were added for FB/IG ads); (3) re-review
   the brain **structure** (`_STRUCTURE.md`; add a layer in `mappings/brain/layout.json` only
   if a data class has no home); (4) re-review **data points** (`_DATA_POINTS.md` — the
   field-enrichment-by-source matrix should light up new cells; the improvement-opportunities
   list is the backlog); (5) ensure the source's notes are `source/<name>` + semantically
   tagged so they join the graph; (6) re-run `analyze.py`; (7) update the status table + add a
   fixture/test so coverage can't regress.
7. **Hand off**: open the vault in **Obsidian** (start at `Home.md` → `_STRUCTURE.md` →
   `Dashboard.md`); `AGENTS.md` guides the agent and enforces privacy. **Leverage layers:**
   Dataview/Bases dashboards + `_DATA_POINTS.md` · the cross-source **Graph** (every note
   tagged `source/<name>` + type; see `_GRAPH.md`) · Obsidian Copilot (Vault-QA + the
   generated `/commands`) · an AI agent (deep multi-step, reads `_STRUCTURE.md`+`_SUMMARY.md`+
   `_DATA_POINTS.md`+synthesis not all notes) · Map View/Graph plugins (`85-places/` carry
   lat/lng — great with Facebook check-ins + Google Maps).

## Privacy (enforced in code at the collector boundary)
Default mode is privacy-safe: third-party/employee emails & phones are never
written; message **bodies are never read** (only per-person frequency/recency
signal); sensitive files (Email Addresses, PhoneNumbers, Logins, Receipts, plus
company HR/payroll/security/admin logs) are quarantined. **`--full`** (owner mode)
captures everything into the user's OWN local brain — use only on data they own/
are authorized to retain; keep the default for anything shared or company/
multi-tenant.

## Operating the vault (example prompts for the user)
- "Who shows up across multiple sources — my strongest multi-context relationships?"
- "Using my network map, who are my strongest dormant connections — draft a reconnect message in my voice."
- "What companies/roles have I actually targeted vs my stated preferences?"

## Notes
- Re-running into a non-empty directory is refused — use a fresh dir.
- Facebook/Instagram exports must be requested in **JSON**.
- Full data model + per-source mapping: `references/blueprint.md`.
- Adding a source = one file in `scripts/sources/personal|company/` (see
  `CONTRIBUTING.md`); adding an output = one emitter in `scripts/emitters/`.
