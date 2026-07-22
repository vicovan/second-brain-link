---
name: second-brain-link
description: Turn a personal OR company data export into a private, local, AI-queryable "digital twin" or Company Brain — an Obsidian vault (optionally a GBrain repo). 25 sources auto-detected — LinkedIn, Facebook, Instagram, Google Takeout, Amazon, X, WhatsApp, GitHub, YouTube, Strava, Reddit, Spotify, TikTok; company-side LinkedIn Page, Google Workspace, Slack, Notion, Confluence, Jira, Salesforce, HubSpot, Zendesk, mail archives, Microsoft 365, Teams — plus a self-adapting mapper for unknown exports. 100% local, zero network, message text never read. Use whenever the user points at a data export (.zip or folder) or asks to build/map/import their data into a second brain, digital twin, knowledge vault, or company brain — even without those exact words.
---

# Second Brain Link — multi-source digital-twin second brain

Build ONE unified, private, Obsidian-native vault from any supported data export so the user (and their Claude) can reason over their professional and social history. **25 sources ship** — personal: LinkedIn, Facebook, Instagram, Google Takeout, Amazon, X/Twitter, WhatsApp, GitHub, YouTube, Strava, Reddit, Spotify, TikTok; company: LinkedIn Company, Google Workspace, Slack, Notion, Confluence, Jira, Salesforce, HubSpot, Zendesk, Email (mbox), Microsoft 365, Teams (full export + import steps per source: `references/SOURCES.md`) — and unknown files are caught, never dropped. Everything runs locally; nothing is uploaded.

## Architecture (read before running)

Each source is a **drop-in adapter** in `scripts/sources/{personal,company}/` or a **declarative JSON mapping** in `mappings/sources/` (mappings win on a name clash). An adapter knows its export's format (CSV/JSON/ICS) and pushes records into one canonical `Collector` (`scripts/sources/common.py`). The builder (`scripts/build_vault.py`) then renders a single vault from the collector — so multiple sources merge into one graph, and **a person who is both a LinkedIn connection and a Facebook friend becomes one note tagged with both sources.** Adding a future network = one new adapter file.

Two cost tiers, same as before: a **deterministic core** (detection, parsing, the whole vault) runs with zero API tokens; **intelligence is spent only on the residual** — unknown files and the two judgment-heavy synthesis notes. The efficiency rule still holds: **read `schema_map.md` and `_COVERAGE.md`, never the raw files or thousands of person notes.**

The scripts:
- `scripts/profile_export.py` — detects source(s) and writes `schema_map.json` + `schema_map.md` (the catalog + unknown-file flags). It also writes two PII-safe visualizations: a **mindmap** (`<source>_mindmap.md` + `.canvas` — every file & column + cross-file correlations) and a **brain-structure design** (`brain_structure.md` + `.canvas` + `.json`). Disable with `--no-mindmap` / `--no-structure`.
- `scripts/diagrams.py` — renders those visualizations from the catalog (column names only, never cell values). Source-agnostic.
- `scripts/build_vault.py` — detects source(s), runs adapters, renders the unified vault; `--dry-run` plans without writing; `--structure brain_structure.json` lays the vault out per the designed (pruned-canonical) spec; `--overrides mapping_overrides.json` maps unknown files; writes `_COVERAGE.md`, `_BUILD_REPORT.md`, and **`_SUMMARY.md`** (a seed-counts snapshot: per-layer note counts + the coverage line; a top-level `vault/_SUMMARY.md` indexes all entity brains).
- `scripts/sources/` — the adapters + shared canonical model. This is what you extend.

## Workflow

### 1. Locate the export
Ask for the path if you don't have it. Accepts a `.zip` or an unzipped folder. It can even be a **combined** archive containing more than one source's folders — the tool detects and merges them all.

**Multiple identities / companies (named entities):** organize as `data/personal/<identity>/<source>/…` and `data/company/<company>/<source>/…` — **the folder name is the entity**. Point the builder at the `data/` root (or any dir with `personal/`+`company/` children) and it builds ONE brain per entity into `vault/personal/<id>-brain/` + `vault/company/<co>-brain/`, then (when ≥2 entities) a **`vault/_correlations/`** brain linking the same person across brains, shared orgs, and identity↔company `works_at` edges (`--no-correlate` to skip). A single un-foldered export still builds one brain.

If the user hasn't downloaded it yet, read them the steps from `references/SOURCES.md` (all 25 sources, verified vendor flows). In short: LinkedIn → Settings & Privacy → Data Privacy → Get a copy of your data (larger archive). Facebook → Settings → Your information → Download your information (**format: JSON**). Instagram → Accounts Center → Your information and permissions → Download your information (**JSON**). Google → takeout.google.com (select Contacts, Calendar, YouTube, Profile at minimum).

**Company exports** (for a Company Brain — use `--subject company`, auto-detected): LinkedIn **Company Page** export (org profile, employees, followers, posts), **Google Workspace** admin export (directory/users → employees, shared calendars → events), **Slack** workspace export (users + channels; messages → signal only, never bodies). These root the brain on the organization and carry the same privacy guarantees (employee emails/phones stripped by default; HR/payroll/security/admin-log files quarantined).

### 2. (Optional but recommended) Dry-run to confirm detection
```bash
python3 scripts/build_vault.py "<export>" --dry-run
```
Reports which source(s) were detected and how many files. If it detects nothing, the folder/file names may differ from expectations — proceed to profiling.

### 3. Profile — build the schema map + mindmap + brain-structure design
```bash
python3 scripts/profile_export.py "<export>" --out "<vault>/_profile"
```
Write the profiler outputs into the **vault** (a `_profile/` subfolder), so the map and the built brain live together. This writes:
- `schema_map.md` / `.json` — compact, PII-safe catalog: detected sources, every file with columns/keys + a safe sample, and an "⚠️ Adaptation needed" section flagging unrecognized files.
- `<source>_mindmap.md` + `.canvas` — an **exhaustive mindmap**: every file → every column, grouped by target layer, plus a correlations diagram (which files feed Person / Organization / Skill / Job / Activity / Profile-URL, and on what join field). 🔒 marks sensitive files (catalogued, never imported); ❓ marks unmapped files.
- `brain_structure.md` + `.canvas` + `.json` — the **designed brain folder/note tree** (fixed canonical layers, pruned to what this export actually has). The `.json` is the build-spec consumed in step 5.

Show the user the mindmap and brain-structure (both render in Obsidian and GitHub) before building, so they can see the data points and the planned layout.

### 4. Adapt — only if the map flags unknowns
If nothing is flagged, skip to step 5. Otherwise write `<work-dir>/mapping_overrides.json` to route unknown files into the right layer (reasoning over the small map, not the data):
```json
{
  "file_routes": {
    "newsletters": {"layer": "30-voice", "title": "Newsletters"},
    "watchhistory": {"layer": "30-voice", "title": "YouTube watch history"}
  }
}
```
Match keys are normalized filenames (lowercase, no spaces/punctuation/shard-suffix), exactly as printed in the map. Tell the user in a line what you adapted.

### 5. Build the brain
```bash
python3 scripts/build_vault.py "<export>" -o "<vault>/<name>-brain" \
  --structure "<vault>/_profile/brain_structure.json" \
  --overrides "<vault>/_profile/mapping_overrides.json"
```
`--structure` makes the builder lay the vault out per the designed spec from step 3; omit `--overrides` if step 4 wasn't needed. Output must be empty/new (keep `_profile/` separate from the built brain so they don't collide).

**Self-adapting sources (mappings + harvester).** Most sources are declarative JSON
(`engine/mappings/sources/<name>.json`) interpreted by the engine — no Python. Any
file no source claims is rescued by a deterministic **universal harvester** (people,
places, posts, interests, message-signal) so nothing is lost, and listed in
`_COVERAGE.md` under **"Needs a mapping"** with its detected shape. Read that section
and add a mapping rule (or a `--mappings <dir>` override) to claim those files precisely
— selectors handle nested shapes (`string_list_data[].value`,
`features[].properties.location.name`, `geometry.coordinates[0]`); a rule's `emit` picks
a canonical verb (person/org/post/interest/place/event/search/message_signal/identity/
**mirror**/**ad_segment**), and a rule may declare semantic `tags` (e.g. `person/friend`)
that join the automatic `source/<name>` + type tags on every note. A mapping overrides a
same-named Python adapter. The full self-improvement loop is below.

**Subject + output target (`--subject`, `--emit`):**
- `--subject person|company` (default **auto** — picks `company` if a company-subject adapter fired, e.g. LinkedIn Company / Google Workspace / Slack). Person roots on `00-me/`; company roots on `00-org/` (people→employees/contacts; `15-organizations/`→customers/vendors/partners) and writes a `data-handling.md` note ("you are the data controller; processed locally; here's what was quarantined"). **Company brains use company-named layers** — `20-brand/`, `30-content/`, `40-pipeline/` (one note per deal/campaign), `50-market-view/`, `60-knowledge/` (meetings.md + events.md), `70-support/`, `80-signals/`, `85-locations/` — same layer keys, subject-appropriate folder names (`_STRUCTURE.md` in the vault maps them).
- `--emit obsidian|gbrain|both` (default **obsidian** — today's vault, unchanged). `gbrain` emits a GBrain-compatible markdown repo (`people/`, `companies/`, `writing/`, `notes/` + typed-edge wikilinks + `gbrain.manifest.json`); `both` writes Obsidian to `<out>/obsidian/` and the GBrain repo to `<out>/gbrain/`. Optional `--gbrain-import` then shells out to `gbrain import <dir>` **only if** the `gbrain` CLI is on PATH (opt-in; the sole non-core/networked step; clean no-op otherwise). The GBrain repo respects the same privacy mode as Obsidian.

**Full-fidelity / owner mode (`--full`):** by default the build is privacy-safe (third-party emails/phones stripped, message bodies never read, sensitive files quarantined). For the user's OWN brain on their OWN machine, add `--full` to capture **everything** — emails, phones, every extra column on every entity (rendered in a `## Details` section + frontmatter), and the otherwise-quarantined personal files folded into `00-me/` as `my-*.md` tables, so **no field is ever dropped**. Still 100% local; `vault/` stays git-ignored. Use it when the user says they want all their data; keep the default for anything shared, distributed, or company/multi-tenant.

### 6. Verify coverage
Read `<vault-dir>/_COVERAGE.md` — it reports detected sources and how many files were leveraged. Anything unrecognized is summarized into `99-uncategorized/` (never dropped). Refine overrides and rebuild into a fresh dir if needed; cap at ~2–3 passes. Read `<vault-dir>/_SUMMARY.md` for the seed counts at a glance (per-layer note counts + the coverage line + key buckets).

### 6b. Activate for the user's GOALS (do this — it's where the value is)
A brain is only useful once pointed at a goal. **Ask the user what they want to use it
for** (offer the menu: **fundraising · sales/BD · job-search · datamining · personalization
· hiring · reconnect-dormant · positioning · travel** — and for a COMPANY brain also **onboarding · who-knows-what**), then generate goal workspaces:
```bash
python3 scripts/analyze.py "<vault-dir>" --goals fundraising,bd,jobsearch,datamining,personalization \   # company: add onboarding,whoknows
  [--icp "<who they sell to>"] [--thesis "<what they raise for>"] \
  [--copilot-dir "<their Obsidian Copilot custom-prompts folder>"] \
  [--graph-config "<vault>/.obsidian/graph.json"]
```
This is deterministic + re-runnable in seconds over the built brain (reads frontmatter,
no rebuild). It writes:
- `95-goals/<goal>.md` — ranked tables + a ready AI prompt per goal. `datamining` = network
  patterns (clusters, multi-source-confirmed people, mirror-vs-stated gaps); `personalization`
  = recommend-me-X grounded in your places/interests/mirror (solves cold-start).
- **`Dashboard.md`** — tag-based Dataview tables (incl. a **by-source** table).
- **`_DATA_POINTS.md`** — the catalog of every node type + relation + which **source**
  enriched each field (the data-mining map; always written).
- **`_GRAPH.md`** + `--graph-config` — colors the global **graph** by source + type so all
  data points from all networks are visible at once (merges into `.obsidian/graph.json`,
  preserving the user's settings, writing a `.bak`).
- **`copilot-prompts/`** — `/warm-intro`, `/investor-paths`, `/reconnect`, `/job-fit`,
  `/ask-my-network`, **`/mine`** (data-mining), **`/for-me`** (personalized recs).

Then ACT on the prompts: read the goal note + `00-me/identity.md` and draft the
intros/asks/recommendations in the user's voice.

### Operating the brain — leverage layers (tell the user)
1. **Dataview/Bases dashboards** (`Dashboard.md`) — structured, exact, always-current;
   `_DATA_POINTS.md` is the map of every data point + relation.
2. **The typed graph (`graph.json`, schema sbl-graph/1)** — every brain root carries a
   machine-readable graph: nodes (id = note path sans `.md`), TYPED weighted edges
   (`works_at`/`member_of`/`attended`/`purchased_from`/`correlated`/`linked`, `w` ∈ (0,1])
   and ordered layers. **Answer questions by traversing it, never by reading all notes:**
   resolve the question's entities to node ids by title → follow `correlated`/`works_at`
   first, then high-`w` edges 1–2 hops → read ONLY those notes (frontmatter first) → cite
   what you used as `[[wikilinks]]`. This is spreading activation over the real graph —
   the same traversal the Studio's Neural view animates. `_HEALTH.md` reports orphans /
   duplicate suspicions / conflicts an agent may fix WITH the user (never auto-merge).
3. **The cross-source graph** — every note is tagged `source/<name>` + its type (+ semantic
   tags like `person/friend`, `mirror/ad-segment`), so the global **Graph view** shows all
   data points from all networks, colored/filterable by source and type (see `_GRAPH.md`).
4. **Obsidian Copilot** — **Vault QA** answers natural questions across all notes
   semantically; the generated **custom prompts** are one-click `/commands`. Point Copilot's
   custom-prompts folder at `copilot-prompts/` (or pass `--copilot-dir`).
5. **An AI agent (Claude Code / Codex)** — deep multi-step reasoning + writing notes back
   (read `_STRUCTURE.md`+`_SUMMARY.md`+`_DATA_POINTS.md`+synthesis+frontmatter, never all notes).
6. **Plugins** — **Map View** for `85-places/` (notes carry lat/lng — great with Facebook
   check-ins + Google Maps); **Graph/Local Graph** for the people↔company network.

### Self-healing (the skill debugs + fixes itself)
- **Preflight:** `python3 scripts/build_vault.py "<export>" -o "<vault>" --doctor` (or the same flag on `profile_export.py`) writes `_DOCTOR.md` (PASS/WARN/FAIL: Python version, files readable, encodings, sources detected). WARN is non-blocking; FAIL must be fixed first.
- **Auto-recover at runtime:** a single broken file or adapter no longer kills the run — `read_csv` falls back across encodings + skips a `Notes:` preamble, and each adapter is run guarded so the build continues with the other sources (logged in `_BUILD_REPORT.md`).
- **On an unrecoverable error:** the run writes `_ERROR.md` (traceback + classified likely cause + the offending script/line + a concrete "To fix" hint) and exits non-zero. **When that happens, YOU (Claude Code) self-heal:** read `_ERROR.md`, apply the smallest fix to the named `scripts/...` file, **mirror it to the installed copy** (`~/.claude/skills/second-brain-link/`, see Persist step), then re-run the same command. Cap ~3 passes. Keep every privacy + deterministic-core invariant.

### 7. Self-improve on every new source (the loop — from all points of view)
Whenever a NEW source (or a new export version) is integrated, ratchet the whole system
up, not just coverage. Run this loop:
1. **Profile** the source (step 3) → the schema map flags new files & fields.
2. **Close coverage** — read `_COVERAGE.md` "Needs a mapping"; write/extend the source's
   mapping JSON. If the source carries a data class no `emit`/bucket holds, add the emit
   (this is exactly how the **`mirror`/`ad_segment`** emits were added for Facebook/IG
   ad-data → `50-mirror/`).
3. **Re-review the brain STRUCTURE** — does the source add a data class no layer holds? If
   so add a layer/bucket in `engine/mappings/brain/layout.json`; else route into an existing
   layer. Regenerate and read **`_STRUCTURE.md`** (the always-on vault map: every folder/file
   + its role).
4. **Re-review the DATA POINTS** — read **`_DATA_POINTS.md`**: the *field-enrichment-by-source*
   matrix should light up new cells for the new source, and the *improvement opportunities*
   list shows what's still unmapped. Iterate the mapping until the valuable fields are captured.
5. **Ensure tagging** — the source's notes must carry `source/<name>` + semantic tags so they
   join the cross-source graph (mapping rules declare `tags`; the renderer adds `source/*`).
6. **Re-run `analyze.py`** so goals / Dashboard / `_DATA_POINTS.md` / the graph reflect the
   richer graph.
7. **Persist + ratchet** — fold a clearly-general improvement into the mapping (or a Python
   adapter for cross-file logic), update the status table, and add a fixture/test so coverage
   can't regress. The installed skill dir may be read-only — copy it somewhere writeable,
   edit, repackage/mirror, and tell the user. This is how the tool gets better with each source.

### 8. Enrich the synthesis drafts (optional, cheap)
`90-synthesis/positions-i-hold.md` and `positioning-gaps.md` ship as deterministic drafts. To deepen them, read ONLY those two plus `00-me/identity.md`, `50-mirror/inferences.md`, `30-voice/comments.md`, and a sample of `30-voice/posts/`. Rewrite into articulated positions / concrete gaps in the user's voice; if activity is thin, say so. Keep links tight.

### 9. Summarize and hand off
Tell the user which sources were detected and what they produced (from `_BUILD_REPORT.md` and the seed counts in `_SUMMARY.md`), highlighting cross-source merges ("X people appear in more than one network"). Then: open the folder in **Obsidian** and start at **`Home.md`**; it's Obsidian-native (filenames == titles so `[[links]]` resolve and the **Graph view** shows the merged network; frontmatter uses Properties incl. a `sources` field; no plugins required). A `CLAUDE.md` at the root guides Claude Code and enforces privacy.

## Operating the vault (example prompts for the user)
- "Who shows up across multiple networks — those are my strongest multi-context relationships."
- "Using my network map, who are my strongest dormant connections, and draft a reconnect message to each in my voice."
- "What companies/roles have I actually targeted, and where does that drift from my stated preferences?"
- "How do the algorithms categorize me vs how I describe myself, and what should I change?"

## Privacy (enforced in code at the collector boundary)
**Default mode = privacy-safe** (use for anything shareable / company / GBrain). **`--full` = owner mode** flips these to capture everything into the user's OWN local brain (see the build step). The guarantees below describe the DEFAULT:
- Third-party emails/phones are never stored as notes (LinkedIn connections, Google contacts, etc.). *(In `--full` they are stored — the owner's choice for their own local data.)*
- Message **bodies are never read** — only a derived per-person count + last-contact date (sets relationship strength). Applies to LinkedIn, Facebook, Instagram messages alike.
- LinkedIn quarantine-class files (Email Addresses, PhoneNumbers, Logins, Receipts, Security Challenges, Registration, ImportedContacts, Private_identity_asset…) are never imported. *(In `--full` they ARE imported, into the `raw-data/` layer.)*
- The schema map redacts sensitive columns and masks emails/phones in samples.

## Notes
- Re-running into a non-empty directory is refused — use a fresh dir, OR pass `--refresh` to UPDATE the existing vault in place (keeps the user's notes/edits; conflicts land beside as `*.new.md`; read `_UPDATE_REPORT.md` after and summarize its counts). `_notes/` is the user's own space — never write generated content there, but DO save user-requested notes there.
- Facebook/Instagram exports must be requested in **JSON** format (HTML is not parsed).
- Source formats drift; adapters parse defensively and unknowns are summarized, so partial coverage degrades gracefully rather than failing.
- Full data model + per-source mapping: see `references/blueprint.md`.
