# CLAUDE.md — project context for Second Brain Link

> Context for any coding agent (Claude Code, OpenAI Codex) or human contributor.
> It captures the *why* behind this repo, the architecture, the conventions that
> must not drift, the bugs we already hit and fixed, and what's next. Read it
> before editing. This is the **repo-root** CLAUDE.md; a *different*, smaller guide
> (`CLAUDE.md` for Claude / `AGENTS.md` for OpenAI) is generated *inside each vault*
> to steer the agent over a user's data — don't confuse the two.

---

## 1. What this is, in one paragraph

**Second Brain Link** turns a person's *or* a company's own platform data exports —
25 sources: LinkedIn, Facebook, Instagram, Google Takeout, Amazon, X/Twitter, WhatsApp, GitHub,
YouTube, Strava, Reddit, Spotify, TikTok (personal); LinkedIn Company, Google Workspace,
Slack, Notion, Confluence, Jira, Salesforce, HubSpot, Zendesk, Email/mbox, Microsoft 365,
Teams (company; see §9 for depth/privacy per source) — into a single, private, local,
AI-queryable knowledge
vault: a **digital twin** or **Company Brain** an agent can reason over. It runs
**100% locally**, makes **zero network calls** in the core transform, and emits
plain Markdown the user owns. It is a **cross-model Agent Skill** (one engine, thin
Claude + OpenAI Codex packagings, Agent Skills open standard); default output is an
Obsidian vault, with a GBrain repo as an opt-in emitter. Name: Second Brain Link.
Domain: `secondbrainlink.com`. Created & maintained by **Adrian Vicovan**
(`adrian@vicovan.com`). License: **MIT** — a public open-source repo that ships the
standard community files (`LICENSE`, `README.md`, `CONTRIBUTING.md`,
`CODE_OF_CONDUCT.md`) and never commits any real user data (see §6).

The product wedge: most "import your data" tools dump a pile of orphan notes. This
builds a **connected graph** (real Obsidian links + a unified network across
sources, with a person seen in several sources merged into one note) and ships
**synthesis** notes that answer goal-driven questions ("who can get me hired /
funded / a client", "how do the algorithms see me vs how I describe myself"). The
job-seeker use case is the viral on-ramp; the durable value is relationship
intelligence for founders raising and for sales/BD.

---

## 2. Non-negotiable principles (do not let these drift)

1. **Local-first, zero-server, no telemetry.** The transform never calls the
   network. Stdlib only (Python 3.8+); if you add a dependency it must work
   offline. The single opt-in networked step is `build_vault.py --gbrain-import`
   (PATH-gated).
2. **Privacy enforced in CODE, not promises.** See §6. Enforced at the `Collector`
   boundary so no adapter or mapping can violate it by accident: third-party /
   employee emails & phones are never written, message *bodies* are never read
   (only a per-person frequency/recency signal), sensitive files are quarantined.
   There is one explicit exception — **owner mode (`--full`)** captures everything
   into the user's OWN local brain; the default stays privacy-safe.
3. **Deterministic core; AI only on the residual.** All detection, parsing, vault
   building, the mindmap, places, and entity resolution run with **zero API cost**.
   Intelligence is spent only on (a) proposing a mapping/overrides file for
   genuinely unknown files (reading the small schema map, never raw data), (b)
   optionally enriching the two synthesis drafts, (c) self-heal (acting on a
   structured `_ERROR.md`). Never move bulk parsing into an AI step.
4. **Generic by architecture.** A source = a **JSON mapping** (preferred) *or* a
   Python adapter; an output = an **emitter**. The engine has **no
   source-specific code**. Adding either must not require touching the builder,
   privacy rules, or merge logic.
5. **Engine canonical & in sync.** The one source of truth is `engine/`. After
   editing it, repackage + install (§11). Never fork the engine per provider —
   providers are just `providers/<p>/SKILL.md`.
6. **Obsidian-native output, plug-and-play.** See §7. Filenames == note titles,
   quoted wikilinks in properties, ISO dates, Properties/tags, a Home MOC, a real
   graph. No plugins required.
7. **Nothing is silently dropped.** Files no adapter/mapping recognizes are rescued
   by the universal harvester, summarized into `99-uncategorized/`, and reported in
   `_COVERAGE.md` (under **"Needs a mapping"**).

---

## 3. Architecture

### The pipeline
```
DETECT + PROFILE  →  MINDMAP + BRAIN-STRUCTURE  →  ADAPT (if needed)  →  BUILD (emit)  →  VERIFY  →  (multi-entity) CORRELATE  →  ANALYZE (goal-driven)
```
- **Detect + profile** (`scripts/profile_export.py`): identify which source(s) the
  archive contains (even a combined one), catalog every file/column into a PII-safe
  `schema_map.md/.json`, flag anything unrecognized.
- **Mindmap + brain-structure** (`scripts/diagrams.py`): PII-safe Mermaid + Obsidian
  `.canvas` — `<source>_mindmap.*` (every file & column + correlations) and
  `brain_structure.md/.canvas/.json` (the designed vault tree + a build-spec).
- **Adapt** (optional): if the map flags unknowns, the agent reads only the small
  map (never raw data) and writes a mapping rule or `mapping_overrides.json`.
- **Build** (`scripts/build_vault.py`): detect sources, run each matching
  adapter/mapping, render the unified vault through an emitter, write `_COVERAGE.md`
  + `_BUILD_REPORT.md` + `_SUMMARY.md` (seed counts: per-layer note counts + the
  coverage line; multi-entity runs also write a top-level `vault/_SUMMARY.md` index)
  + **`_STRUCTURE.md`** (ALWAYS — the vault map: every folder/file + its role, from a
  role registry) (+ the in-vault guide). Every entity note is tagged `source/<name>` +
  its type (+ any rule-declared semantic tags) for the cross-source graph.
- **Verify**: read `_COVERAGE.md` / `_SUMMARY.md`; refine and rebuild into a fresh dir if needed
  (cap ~2–3 passes). On a non-zero exit, self-heal off `_ERROR.md` (§3, self-heal).
- **Analyze** (`scripts/analyze.py`): goal-driven value layer + the data-mining map, run
  AFTER build over the built brain (reads frontmatter, re-runnable, zero API cost).
  `--goals fundraising,bd,jobsearch,datamining,personalization[,…]` writes `95-goals/<goal>.md`
  (ranked tables + a ready AI prompt; `datamining` = network patterns, `personalization` =
  recommend-me-X grounded in places/interests/mirror — the cold-start solver), `Dashboard.md`
  (tag-based Dataview incl. a by-source table), **`_DATA_POINTS.md`** (the catalog of every
  node type + relation + which **source** enriched each field — always written), **`_GRAPH.md`**
  + `--graph-config` (colors the global graph by source + type, merging into
  `.obsidian/graph.json` non-destructively), and `copilot-prompts/` (incl. `/mine`, `/for-me`).
  A `GOALS` registry maps each goal key to its builder — the skill asks the user their goals
  and runs this. Deterministic ranking; judgment parts are emitted as prompts, not fabricated.
- **Self-improve on each new source** (skill loop, see `providers/*/SKILL.md`): a new source
  ratchets coverage → structure (`_STRUCTURE.md`/`layout.json`) → data points
  (`_DATA_POINTS.md` field-enrichment-by-source) → tags/graph → analyses → docs/tests.
- **Correlate** (`scripts/correlate.py`): when ≥2 entities build, write a
  `_correlations/` brain.

### The source layer (the core idea)
Everything source-specific is data or a single adapter file; the builder renders
from one canonical `Collector` and has no source-specific code.

- **Declarative JSON mappings (preferred)** — `engine/mappings/sources/<name>.json`,
  interpreted by `scripts/mapping.py` into the SAME adapter contract (`NAME`,
  `SUBJECT`, `detect`, `extract`). A mapping declares `detect` + `records[]`, each:
  `match` (path/name/suffix) → `locate` (`auto_array` / `walk` / `dict` /
  `geojson_features`) → `fields` (selector mini-language) → `emit` (a canonical
  `col.add_*` verb: person/org/post/comment/interest/reaction/search/event/
  message_signal/place/identity/**mirror**/**ad_segment** — the last two feed the
  `50-mirror/` layer). A rule may also declare **`tags`** (semantic tags like
  `person/friend`) put on every entity note it emits, joining the renderer's automatic
  `source/<name>` + type tags (the basis for the cross-source graph). **Selector
  mini-language (no eval — mappings are DATA):** dotted keys,
  `a[]` iterate, `a[N]` index, `*` any key, `a[].b` pluck, `a[k=v].b`
  label-predicate (pick a value by its sibling label — unlocks Facebook/Instagram's
  `label_values:[{label,value}]` shape, e.g. `label_values[label=Message].value`),
  `["x","y"]` first-non-empty, `{"const": v}`. Handles e.g. Instagram
  `string_list_data[].value` / `string_map_data.*.value` and Google Maps GeoJSON
  `features[].properties.location.name` + `geometry.coordinates[0]`.
  - **Mapping wins over a same-named Python adapter.** Today
    `instagram`/`facebook`/`reddit`/`spotify`/`tiktok` are JSON mappings; `linkedin`/`google` + the other personal/company
    adapters stay Python.
  - **Consumed keys must be `norm_file(p.name)`** (NOT `nk`) to match the engine's
    `file_index` keys — else coverage shows files as unclaimed though extraction
    ran (real bug, §10).
- **Python adapters (bespoke logic only)** — `scripts/sources/personal/<name>.py`
  (`SUBJECT="person"` default) and `…/company/<name>.py` (`SUBJECT="company"`). Each
  knows ONE export's format and pushes records into the `Collector` via `col.add_*`.
  - `detect(file_index) -> bool`; `extract(root, file_index, all_paths, col) -> set`
    of consumed keys. **LinkedIn is the documented exception** — `extract(root,
    file_index, col)` with normalized-filename prefix matching; new sources match
    the 4-arg form.
  - `sources/__init__.py` **auto-discovers** both subpackages (pkgutil walk) and
    `register_mappings(extra_dirs)` merges Python adapters + shipped mappings + any
    `--mappings <dir>` override (later wins on NAME). It exposes `ALL`, `BY_NAME`,
    and **`ALL_QUARANTINE`** (union of every adapter's quarantine set) — read *live*
    via `sources.<X>` (not by-value) so a `--mappings` rebuild takes effect.
- **The universal harvester** — `scripts/harvester.py` runs on any file no
  source/mapping claimed. Deterministic shape recognition (people/handles,
  message-signal, GeoJSON/lat-lng places, posts, IG wrappers, interests) → `col.add_*`,
  so **nothing is lost** even from unknown formats. Rescued files are listed in
  `_COVERAGE.md` under **"Needs a mapping"** — the cue to write a mapping JSON.
- **`scripts/sources/common.py`** — the canonical model. `Collector`: typed buckets
  (identity, people, orgs, posts, comments, reactions, interests, reputation,
  applications, mirror inferences, ad segments, searches, events, services,
  **places** (`add_place`), `msg_signal`, uncategorized). Privacy is enforced here
  (`add_person` drops anything matching `EMAIL_RE`; there is no "add body" method —
  only `add_message_signal`). Helpers: `nk`, `norm_file`, `obsidian_name`, `link`,
  `iso_date` (ISO / unix int / 10- & 13-digit epoch strings / "15 Mar 2023" / "Jan
  2022" / MM/DD/YYYY), `strip_pii`, `fix_mojibake`, `read_csv` (encoding fallback +
  `Notes:` preamble skip), `read_json`, `walk_json_arrays`, `canonical_url`,
  `EMAIL_RE`, `PHONE_RE`, `SENSITIVE_COL_HINTS`. The Collector also carries the
  run's context: `subject`/`subject_entity`, `entity_name`/`entity_kind`/
  `entity_vault`, `provider`, `structure_spec`, `full`.

### Output emitters
Output targets are drop-in emitters in `scripts/emitters/` — `base.py`,
`obsidian.py` (default; wraps `VaultWriter` via lazy import, byte-identical to the
pre-refactor output), `gbrain.py`, `__init__.py` registry with `select()`. CLI:
`--emit obsidian|gbrain|both`. GBrain emits `people/ companies/ writing/ notes/` +
`[[people/slug]]` wikilinks + typed-edge lines (`works_at`…) + `gbrain.manifest.json`
(documented-safe flat shape; revisit if a GBrain version pins a different on-disk
layout). `--gbrain-import` is PATH-gated + opt-in (the only networked step).

### Subjects, entities, per-entity brains + correlation
- **Subject axis** — `--subject person|company` (default auto: company iff a company
  adapter fired). person→`00-me/`, company→`00-org/` + a `data-handling.md`
  data-controller note. A *mixed* single export (both subject groups fire) builds
  **two sibling vaults** (`personal-brain/` + `company-brain/`); a pre-pass computes
  each group's consumed keys so a sibling treats the other group's files as
  owned-elsewhere, not uncategorized.
- **Named entities** — an entity is a named folder: `data/personal/<id>/<source>/…`
  and `data/company/<co>/<source>/…`. **The folder name IS the entity**
  (authoritative); name/URL only *correlate* across entities.
  `discover_entities(root)` enumerates named children under `personal/`+`company/`
  that hold real data (skips `_`/`.` dirs); `run_multi()` builds ONE brain per
  entity (`_build_one`, one `Collector` each) into `vault/personal/<id>-brain/` or
  `vault/company/<co>-brain/`. A plain single export still works via `run()`
  (back-compat); `--subject` forces a single brain.
- **Correlation** (`scripts/correlate.py`) — with ≥2 entities, `run_multi` calls
  `build_correlations(collectors, out/_correlations, provider)`:
  - `people/<name>.md` — a person in ≥2 brains → one cross-note deep-linking into
    each, role/company per entity. Matched by `nk(name)`; a **conflicting
    `canonical_url` blocks the merge** (precision-biased — a wrong cross-merge is
    worse than a miss).
  - `orgs/<org>.md` — organizations referenced by ≥2 entities.
  - `edges.md` — identity↔company `works_at` edges, derived ONLY from a person
    entity's own Positions naming a company entity (never inferred from a company's
    people list, which mixes employees/followers/contacts).
  - `--no-correlate` skips it.

### Brain layout
`engine/mappings/brain/layout.json` externalizes the folder/route table;
`diagrams.apply_layout()` loads it (falls back to constants, so default output is
unchanged). It adds the **`85-places/`** layer fed by the `places` bucket /
`add_place()` (Google Maps Saved Places/Reviews, IG locations), rendered by
`VaultWriter.places()`.

### Self-healing
`scripts/selfheal.py`: `--doctor` preflight → `_DOCTOR.md` (PASS/WARN/FAIL:
Python version, files readable, encodings, sources detected). `guarded_extract`
runs each adapter defensively so one bad adapter can't kill the build. On an
unrecoverable error it writes `_ERROR.md` (traceback + classified cause + offending
file/line + a concrete "To fix" hint) and exits non-zero; the agent then self-heals
in-loop (read → smallest fix to the named file → repackage/mirror → re-run, cap ~3).

### Providers + packaging
`packaging/build_skill.py [claude|openai|all] [--install]` assembles `engine/`
(`scripts/` + `references/` + `mappings/`) + a provider manifest
(`providers/<p>/SKILL.md`, plus provider-extra files such as the Codex
`agents/openai.yaml`) into `dist/<provider>/second-brain-link/` (folder) +
`.skill` (zip), using a **python `zipfile`** (a `cd && zip` subshell silently
no-ops in some sandboxes and ships a stale archive — §10). `--install` copies each
build to its agent's discovery dir (`claude→~/.claude/skills/`,
`openai→~/.agents/skills/`). `build_vault.py --provider claude|openai` (default
claude) picks the in-vault guide written by `vault_guide()` — **`CLAUDE.md`**
(claude) or **`AGENTS.md`** (openai). Provider is carried on the **Collector
instance** (`col.provider`), not a module global (§10).

---

## 4. Repo layout
```
second-brain-link/
├── CLAUDE.md                     # THIS FILE — context for any coding agent
├── AGENTS.md                     # OpenAI-facing twin of the governance rules
├── README.md                     # public pitch + quickstart
├── LICENSE                       # MIT (© Adrian Vicovan and contributors)
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md            # Contributor Covenant 2.1 (contact: adrian@vicovan.com)
├── data/                         # intake (git-ignored contents; placeholder READMEs kept)
│   ├── personal/<entity>/<source>/   # one folder per identity → a digital twin
│   └── company/<entity>/<source>/    # one folder per company → a Company Brain
├── vault/                        # output (git-ignored): personal/<id>-brain/,
│   └── README.md                 #   company/<co>-brain/, _correlations/
├── engine/                       # ← THE SINGLE SOURCE OF TRUTH (provider-neutral)
│   ├── scripts/
│   │   ├── profile_export.py     #   detect + schema map + mindmap + brain-structure
│   │   ├── build_vault.py        #   source/provider-agnostic orchestrator + VaultWriter
│   │   ├── mapping.py            #   JSON-mapping interpreter (selector mini-language)
│   │   ├── harvester.py          #   universal shape recognizer (nothing lost)
│   │   ├── correlate.py          #   cross-entity correlation vault
│   │   ├── diagrams.py selfheal.py new_source.py
│   │   ├── emitters/             #   obsidian (default), gbrain (opt-in), base, __init__
│   │   └── sources/
│   │       ├── __init__.py common.py _template.py
│   │       ├── personal/         #   linkedin, facebook, instagram, google
│   │       └── company/          #   linkedin_company, google_workspace, slack
│   ├── mappings/
│   │   ├── sources/<name>.json   #   declarative source mappings (instagram/facebook/reddit/spotify/tiktok)
│   │   └── brain/layout.json     #   the folder/route table (adds 85-places)
│   └── references/blueprint.md   #   full data model (every file → vault layer)
├── providers/                    # thin per-provider manifests (Agent Skills standard)
│   ├── claude/SKILL.md
│   └── openai/SKILL.md + agents/openai.yaml   # Codex metadata
├── packaging/build_skill.py      # assembles engine + a manifest → dist/<provider>/…
├── dist/
│   ├── claude/second-brain-link.skill     # committed installable (unpacked folder git-ignored)
│   └── openai/second-brain-link.skill
├── tests/
│   ├── run.py                    # stdlib test harness (currently 609 checks)
│   └── fixtures/{personal,company}/<entity>/<source>/   # synthetic exports
└── .github/                      # CI + issue/PR templates
```
Scripts insert their own dir on `sys.path`, so they run from anywhere. Engine
appears **once** — no per-provider duplication.

---

## 5. The vault it produces (layers)
`Home.md` (MOC, start here) · in-vault guide (`CLAUDE.md` / `AGENTS.md`) ·
`00-me/` identity (or `00-org/` for a company; +positions, education/skills/certs/
languages) · `10-people/` (one merged note per person) · `15-organizations/` ·
`20-reputation/` · `30-voice/` (posts, comments, reactions, interests, saved) ·
`35-shopping/` (purchases — one note per order: item, merchant, amount, date) ·
`40-career/` (applications, preferences, saved-jobs, reusable-answers) · `50-mirror/`
(inferences, ad-profile) · `60-learning/` · `70-services/` · `80-search/` ·
**`85-places/`** (saved/reviewed/checked-in locations) · `90-synthesis/` (network-map,
target-companies, positions-i-hold [draft], positioning-gaps [draft]) ·
`_notes/` (YOURS — never regenerated) · `99-uncategorized/` · `_quarantine/`. **Company brains use company-named folders** for the middle layers (20-brand, 30-content, 35-procurement, 40-pipeline w/ one note per deal, 50-market-view, 60-knowledge w/ meetings.md, 70-support, 80-signals, 85-locations) — driven by `mappings/brain/layout.json` `variants` via `VaultWriter.L(key)` (never hardcode a layer folder). Full field reference: `docs/ENTITY-MAP.md`.

**`graph.json` (schema `sbl-graph/1`)** is ALWAYS written at each brain root (+
`_correlations/graph.json`): the machine-readable typed graph — `nodes` (id = note path
sans `.md`, layer/type/sources/strength/geo/avatar), weighted `edges`
(`works_at`/`member_of`/`attended`/`purchased_from`/`correlated`/`linked`, `w` ∈ (0,1]),
ordered `layers`. Built by `scripts/graphdata.py` (pure scan of the rendered vault; called
from `_build_one` before `manifest_end`, so `--refresh` manages it; retrofit any old vault
via `analyze.py <brain> --graph-data`). This is what the Studio Neural view + retrieval and
any agent traverse (workflow documented in `_GRAPH.md`). Do NOT confuse with
`.obsidian/graph.json` (Obsidian's graph-styling config). **Avatars:** images bundled in an
export (e.g. Google Contacts vCard `PHOTO`) are copied to `_assets/avatars/` and stamped as
`avatar:` frontmatter (1MB cap, manifest-tracked); remote profile-image URLs the export
carries (e.g. Slack `image_512`) are stamped verbatim as `avatar_url:` and **never fetched**
— Studios use them only behind an explicit opt-in network toggle.

Generated reports/artifacts at the brain root, each documented in `_STRUCTURE.md`:
`_STRUCTURE.md` (ALWAYS — the vault map: every folder/file + its role) · `_SUMMARY.md`
(seed counts) · `_COVERAGE.md` · `_BUILD_REPORT.md` · then from `analyze.py`:
`95-goals/` (goal workspaces incl. `data-mining.md` / `personalization.md`) ·
`Dashboard.md` (Dataview) · **`_DATA_POINTS.md`** (catalog of every node type + relation +
which source enriched each field) · **`_GRAPH.md`** (the cross-source graph guide +
legend) · `copilot-prompts/` (Obsidian-Copilot `/commands`).

The `90-synthesis/` notes are the summarized "brains" — the in-vault guide tells the
agent to read `_STRUCTURE.md`/`_SUMMARY.md`/`_DATA_POINTS.md` + synthesis + frontmatter
first, never all raw notes. Every note carries `source/<name>` + type tags so the global
**Graph** shows all data points from all sources, colored/filterable by source and type.
Multiple entities → one brain each under `vault/personal/` + `vault/company/`, plus
`vault/_correlations/`.

---

## 6. Privacy model (what's enforced, where)
- **Emails/phones of third parties / employees → never written** (default).
  `Collector.add_person` rejects names matching `EMAIL_RE`; adapters never pass
  email/phone fields (they're read past, not in).
- **Message bodies → never read.** Only `add_message_signal(source, name, date)`
  exists — per-person count + last-contact date, which sets relationship
  `strength`/`status`. Applies to LinkedIn, Facebook, Instagram, Slack alike
  (iterate messages for sender + timestamp, ignore content).
- **Sensitive files → quarantined, never imported.** `ALL_QUARANTINE` (union of every
  adapter's set: Email Addresses, PhoneNumbers, Logins, Receipts, Security
  Challenges, Registration, ImportedContacts, Private_identity_asset, plus company
  HR/payroll/security/admin logs). Reused by builder + profiler for ALL sources.
- **Schema map + visualizations are PII-safe by construction** — column names &
  counts only, sensitive columns redacted, emails/phones in samples masked. Keep
  `diagrams.py` on the catalog, never cell values.
- **`.gitignore` is hardened for public release.** It ignores `data/**` and `vault/**`
  but re-includes only the **exact** placeholder READMEs by path (never a blanket
  `!data/**/README.md`, so a `README.md` shipping *inside* a real export can't slip in,
  and a user's own `data/personal/<id>/` is never tracked). It tracks the built
  `dist/**/*.skill` zips but ignores the unpacked build trees, ignores local agent state
  (`.claude/`, `.claudian/`), and carries a **secrets/credentials net** (`.env*`,
  `*.pem/key/p12/pfx/keystore`, `id_rsa*`, `.netrc`, `credentials*.json`,
  `*secret*.json`, `*token*.json`, `*.log`). Net effect: a `git add -A` can't stage a raw
  export, a generated vault, or a secret. Test fixtures are **synthetic only** (placeholder
  emails on `example.com`, reserved phone/IP ranges, public landmarks, historical-figure
  names) — never a real person's data.
- **Owner mode — the one exception.** `build_vault.py --full` (`Collector(full=True)`)
  captures emails, phones, every extra column (a `## Details` block + frontmatter),
  and folds the owner's OWN quarantined files into `00-me/` as `my-*.md` tables — no
  field dropped. There is no `raw-data/` tree (removed as redundant). Adapters always
  pass extra fields through (`email=`, `extra={...}`) and let the Collector decide —
  never special-case PII in an adapter. Default stays privacy-safe; use `--full` only
  on data the user owns/is authorized to retain, never for shared/multi-tenant data.

---

## 7. Obsidian-native rules (keep these exact — each was a real bug)
- **Filename == note title.** `obsidian_name()` keeps spaces, strips only
  filename/link-illegal chars, so `[[Acme Cloud]]` resolves to `Acme Cloud.md`. Do
  NOT slugify entity note filenames.
- **Wikilinks in YAML properties MUST be quoted, quotes OUTSIDE the brackets:**
  `company: "[[Acme Cloud]]"`. Unquoted fails silently. `_yaml_scalar()` handles it;
  route all frontmatter through `fm()`.
- **Every referenced company gets a note** (positions, connections, applications,
  saved jobs) so links resolve — orgs render AFTER career/people so referenced
  companies are registered first.
- **ISO dates** everywhere (`iso_date`) so Properties are real sortable dates.
- **Properties + tags** on every note (`type`, `tags`, `sources`, `status`,
  `strength`, `last_contact`…) for the tag pane / Bases / Dataview (all optional).
- **Callouts** (`> [!warning]`, `> [!info]`) mark draft synthesis notes.
- **Home.md** is a Map of Content with example prompts — the human entry point.
- Validation asserts: 0 invalid YAML, 0 unresolved real links, all dates ISO.

---

## 8. Conventions for editing
- **Prefer a mapping JSON over Python.** Reach for a Python adapter only for
  cross-file joins / bespoke logic. Mappings are data (no eval).
- **Mappings return `norm_file(p.name)` consumed keys** (not `nk`) — §3, §10.
- Keep the builder source-agnostic; source quirks belong in adapters/mappings.
- All frontmatter via `fm()`; all entity links via `link()`; all dates via
  `iso_date()`; all people/orgs/places via `col.add_*` (never write notes directly —
  that bypasses privacy + merge).
- New layers/notes carry `type` + `tags` + (where relevant) `sources`. Every entity
  note's tags include `source/<name>` (one per contributing source) + its type; route
  them through `note_tags(base, sources, extra)` so the cross-source graph stays
  colorable/filterable. Mapping rules add semantic tags via a rule-level `tags` list.
- Adapters parse defensively and degrade gracefully; partial coverage is fine,
  crashes are not. Unknowns go to the harvester → `99-uncategorized/`.
- Run-context (provider / structure_spec / subject) is carried on the **Collector
  instance**, never a module global — emitters import `build_vault` as a *separate*
  module object, so module globals are stale to them (§10).
- After editing the engine: **repackage + install** (§11) so the `.skill` zips +
  installed copies match. Add a `"_comment"` header key to each mapping JSON.
- Each SKILL.md `description` must stay **< 1024 chars** with **no bare colon** in
  the YAML value (use an em-dash) or the packager rejects it.

---

## 9. Status — built & tested
| Source | Kind | Format | Status |
|---|---|---|---|
| LinkedIn | personal | CSV | Full (Python adapter; real 67-CSV export built `--full`) |
| Facebook | personal | JSON | **Full** JSON mapping (46 rules): friends/followers/requests→people, posts/comments/reactions→voice, liked pages→interests, ad-interests/advertisers/off-Meta/predictions→**50-mirror** (mirror/ad_segment emit), check-ins/cities/locations→85-places, event invitations→events, pages/groups/apps→orgs, search history, profile→identity; tagged `source/facebook` + semantic; quarantine fixed (exact norm_file keys) |
| Instagram | personal | JSON | JSON mapping (profile, follows, posts, topics, places, msg signal) |
| Google Takeout | personal | mixed | JSON mapping (contacts→people, calendar→events, YouTube→interests, **Maps→85-places**) |
| X / Twitter | personal | .js (YTD JSON) | Python adapter (`x_twitter.py`, NAME `x`): tweets→voice (RTs excluded), likes→reaction count, following/followers→people (handles), account/profile→identity; DMs quarantined, contact.js skipped explicitly |
| WhatsApp | personal | .txt chats | Python adapter, **signal-only**: senders+dates→people+msg signal; bodies never read; per-chat day-first/month-first detection |
| GitHub | personal | JSON (account export) | Python adapter: user→identity (+location), repos→voice `kind: repo` + language interests, followers/following→people, stars→interests |
| YouTube | personal | JSON/CSV (Takeout slice) | Python adapter (standalone slice only — stands down when full-Takeout markers present so `google` owns it): watch→interests, search→80-search, subscriptions/playlists→interests, comments→voice |
| Strava | personal | CSV + GPX | Python adapter: activities→events + sport interests, profile→identity (city geocodes), clubs→orgs, GPX **first trackpoint only**→85-places |
| Reddit | personal | CSV | JSON mapping: posts/comments→voice, subreddits→interests, search→80-search; gender/ads/IP/chat files quarantined |
| Spotify | personal | JSON | JSON mapping: listening history→artist interests, Inferences→**50-mirror**, Marquee→ad segments, searches→80-search; Userdata/payments quarantined |
| TikTok | personal | JSON (single file) | JSON mapping: following→people, searches→80-search, hashtags→interests, profile→identity; DM text in-file but never selected |
| Amazon | personal | CSV/JSON (Request My Data) | JSON mapping: orders/subscriptions→**35-shopping** (new purchase layer/bucket), reviews+seller feedback→30-voice, search→80-search, Prime Video/Kindle→interests, Amazon Audiences+advertiser clicks→**50-mirror**; payment/IP/address/serials/message-bodies quarantined |
| LinkedIn Company | company | CSV | Python adapter (org+HQ location, employees + **Department→dept orgs/tags**, followers, posts, **analytics→50-mirror**) |
| Google Workspace | company | mixed | Python adapter (users→employees + **Org Unit→dept orgs/tags**, calendars→events **with attendees/location**, drives→projects) |
| Slack | company | JSON | Python adapter (members→people, channels→orgs **with topic/membership tags `channel/<slug>`**, messages→signal only; day-files consumed — coverage bug fixed; JSON-type detection so it coexists with Workspace in one export) |
| Notion | company | Markdown+CSV | Python adapter: pages (`<Title> <32-hex>.md`)→voice excerpts, database rows→interests |
| Confluence | company | XML (space export) | Python adapter: entities.xml page titles→voice, space→org; HTML pages when present |
| Jira | company | CSV | Python adapter: projects→orgs, assignees/reporters→people + `project/<slug>` tags; ticket prose never imported |
| Salesforce | company | CSV ZIP | Python adapter (cross-file joins): Accounts→customer orgs (+geo), Contacts/Leads→people@account, Opportunities→deal events, Tasks→**signal only**, Users→employees |
| HubSpot | company | per-object CSV | Python adapter: companies→orgs (+geo), contacts→people, deals→events, tickets→count only |
| Zendesk | company | JSON/CSV | Python adapter: orgs→customers, users→people@org, tickets→requester **signal** + volume; subjects/bodies never read |
| Email (mbox) | company | .mbox | Python adapter (`email_archive.py`, NAME `email`), **headers-only**: From/To/Cc display names→people+signal; subjects/bodies never accessed; PST → honest convert-first hint |
| Microsoft 365 | company | .eml / Purview CSV | Python adapter, **headers-only**, same rule as mbox |
| Microsoft Teams | company | CSV/JSON (Purview report) | Python adapter, **signal-only**: senders→people, teams/channels→orgs + `channel/<slug>` tags; content columns never read |

**Offline geocoder** (`scripts/geocode.py` + `mappings/geo/cities.json`, GeoNames-derived,
CC-BY — attribution in `references/geonames-attribution.md`): build-time city→lat/lng for
identity/people/org notes carrying a public location string. Precision-biased ladder
(city+country → city+admin → unambiguous city; ambiguous → no pin). Zero network — a
dictionary lookup. Feeds the Studio Map view; regenerate via `packaging/build_gazetteer.py`.
`index_files` now also indexes `.js .txt .md .xml .mbox .eml .gpx` (norm_file strips those
extensions too); README files are never indexed as data. `analyze.py` gained the company
goals **onboarding** + **whoknows** (grouping people by the `dept/<slug>` + `channel/<slug>`
structure tags adapters emit).

Real-world validation build (IG + Google Maps + LinkedIn + **Facebook**, `--full`): cross-source
merge verified, `source/*` tags on every note, `_STRUCTURE.md`/`_DATA_POINTS.md`/`_GRAPH.md`
present, default-mode PII sweep clean. Both providers package + install + run end-to-end.
`tests/run.py` → **609 checks, 0 failed** (selector mini-language, mapping-wins,
IG/Google fixture build, places + review note, harvester rescue, multi-entity 3-brain
build, cross-person note, `works_at` edge, negative no-merge, multi-vault PII sweep, Codex
`agents/openai.yaml` + `--install`, two-sibling-vault split, **Facebook full mapping +
mirror emit + source/semantic tags + quarantine**, **`_DATA_POINTS.md` catalog +
`--graph-config` merge/.bak + `_STRUCTURE.md`**, all prior regression).

All testing is on **synthetic** fixtures except the local real-export sanity builds.
**Not yet done:** the entity-resolution upgrade (§12); live `gbrain import`
validation (no `bun` here); real FB/IG/Google/company exports beyond the local one.

---

## 10. Known gotchas & lessons learned (real bugs we hit)
- **Mapping consumed-key mismatch** — mappings must return `norm_file(p.name)`, not
  `nk(p.name)`, to match the engine's `file_index` keys; otherwise coverage shows
  files as unclaimed though extraction ran (this raised coverage 48→64/103).
- **`_STRUCTURE.md` / provider / structure_spec stale-global** — emitters do
  `from build_vault import VaultWriter`, a *separate* module object, so module
  globals were stale; carry run-context on the Collector instance instead.
- **`cd skills && zip` subshell silently no-ops** in some sandboxes and ships a
  stale dist — packaging builds the zip in-process with `zipfile`.
- **`Connections.csv` "Notes:" preamble** was parsed as the header → `read_csv`
  finds the real header (`_header_index`: first row with ≥2 short non-empty fields).
- **Obsidian quoted wikilinks** in properties need quotes outside the brackets
  (confirmed via Obsidian docs); unquoted fails silently.
- **Filename slugging broke the graph** — entity filenames use `obsidian_name()`
  (title==filename) so links resolve.
- **`walk_json_arrays` double-counted** nested arrays (IG followers 6-for-3) → dedupe
  by `id()`; parse the top-level IG relationship list directly.
- **Numeric-string epochs** — `iso_date` now detects `^\d{10}$` / `^\d{13}$` strings
  (IG/FB post timestamps), not just int timestamps.
- **Google detection precedence** — an `and/or` precedence bug left Takeout
  undetected; rewritten to check `Takeout/` root + product-dir/`.ics`/subscription
  signals.
- **Dangling company links** — application/saved-job/position companies are now all
  registered as orgs; orgs render after career/people.
- **FB/IG mojibake** — JSON double-encodes UTF-8 as latin-1 ("Gonçalves");
  `fix_mojibake` repairs it.
- **Education/certs/languages** were read but not marked consumed → showed as
  uncategorized; now folded into identity and marked consumed.
- **Non-empty output dir** is refused by design (never clobbers); build into a fresh
  dir. **URL enrichment**: member-follows carry no URL in source — enriched from
  Invitations + Endorsements.

---

## 11. Dev workflow
```bash
# from repo root — engine is the source of truth
S=engine/scripts

# build: every entity under data/ → one brain each + _correlations/
python3 $S/build_vault.py data -o vault
python3 $S/build_vault.py data -o vault --refresh   # UPDATE in place (v1.5): keeps your notes/edits
python3 $S/build_vault.py data/personal/<id>/linkedin -o vault/my-brain   # one source
python3 $S/build_vault.py data --dry-run                                  # detect only
python3 $S/build_vault.py data -o vault --provider openai --emit both --full
python3 $S/build_vault.py data -o vault --mappings work/overrides --doctor

# profile (schema map + mindmap + brain-structure)
python3 $S/profile_export.py data --out vault/_profile

# package BOTH providers and install to each agent's dir
python3 packaging/build_skill.py all --install
#   claude → ~/.claude/skills/   openai → ~/.agents/skills/

# test (stdlib only; must stay green)
python3 tests/run.py            # → 609 passed, 0 failed
```
**Testing approach:** synthetic exports under
`tests/fixtures/{personal,company}/<entity>/<source>/`; assert valid YAML on every
note, every real `[[link]]` resolves, ISO dates, a grep PII sweep finds zero
email/phone/body fixtures, cross-source + cross-entity merge, mapping-wins, harvester
rescue. Never commit a real export or vault.

---

## 12. Roadmap / open questions
**Roadmap:**
- ✓ v1 sources shipped: X, WhatsApp, GitHub, YouTube, Strava, Reddit, Spotify, TikTok + Notion, Confluence, Jira, Salesforce, HubSpot, Zendesk, Email(mbox), Microsoft 365, Teams. Next: Pinterest/Goodreads/Letterboxd/Netflix + Contacts(.vcf)/Calendar(.ics) light seeds (see docs-sources catalog).
- Sharper entity resolution + stable IDs (below).
- ✓ v1.5 SHIPPED: `--refresh` idempotent re-import (manifest + stable note IDs + collector dedupe); Studio reseed offers Update vs Rebuild.
- v2: agentic twin (meeting prep, drafting in voice, relationship-revival nudges).
- Live `gbrain import` validation once a `gbrain` runtime is available.

**Open questions / deferred:**
- **People merge is name-only** (`nk(name)`; correlation additionally blocks on a
  conflicting `canonical_url`). Risk: two different "John Smith" merge, or one person
  in different name forms don't. Future: optional fuzzy/secondary-signal matching —
  keep it conservative (a wrong merge is worse than a miss); never merge on email
  (we don't store it). This is the pending **entity-resolution upgrade**.
- **FB/IG/Google/company formats drift** across versions/regions; prefer widening
  detection + a mapping/harvester catch-all over brittle exact-path assumptions.
- ✓ SOLVED (v1.5): `--refresh` updates an existing vault in place — manifest (`_GENERATED.json`) three-way sync; user notes/edits preserved (conflicts → `*.new.md` + `_UPDATE_REPORT.md`), stale unedited notes pruned, `_notes/` never touched.
- Distribution: GitHub Releases for the `.skill` files? A marketplace listing?
