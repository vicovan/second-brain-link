# Contributing to Second Brain Link

Thanks for helping build this! Second Brain Link turns a person's own platform
data exports into a private, local, Obsidian-native "second brain." Everything
runs **100% locally** with **zero network calls** in the core transform. The two
highest-impact contributions are:

1. **Run it on your real export and report mapping gaps** (PII-safe — see below).
2. **Add a new data source** (one adapter file — see the contract below).

---

## The pipeline (what runs, in order)

```
DETECT + PROFILE  →  MINDMAP + BRAIN-STRUCTURE  →  (ADAPT if needed)  →  BUILD
```

```bash
S=engine/scripts        # the single shared engine (provider-neutral)

# 1. Profile — schema map + mindmap + brain-structure design (all PII-safe)
python3 $S/profile_export.py "<your-export.zip or folder>" --out vault/_profile
#   -> vault/_profile/schema_map.md            (catalog; safe to share)
#      vault/_profile/<source>_mindmap.md/.canvas   (every file & column + correlations)
#      vault/_profile/brain_structure.md/.canvas/.json (designed vault tree + build-spec)

# 2. Build the brain from the designed spec
python3 $S/build_vault.py "<your-export>" -o vault/my-brain \
  --structure vault/_profile/brain_structure.json
```

---

## High-impact contribution #1 — report a mapping gap

Run the profiler (above) and open `vault/_profile/schema_map.md`. If anything
shows under **"⚠️ Adaptation needed"** (unknown files, or known files with
unresolved columns), open an issue and paste that section plus the relevant part
of the mindmap. **It's already PII-safe** — values are redacted/masked and the
mindmap shows only column *names*, never cell values — so it's safe to share.
This tells us exactly what header drift or new files exist in the wild.

Use the **🐛 Mapping gap** issue template.

---

## High-impact contribution #2 — add a new source

**Preferred: write a JSON mapping (no Python).** Most sources are now declarative
JSON under `engine/mappings/sources/<name>.json` — the engine interprets them.
You almost never need to write Python:

1. Run a build; open `_COVERAGE.md`. Files the **universal harvester** rescued are
   listed under **"Needs a mapping"** with their detected shape — nothing is lost
   meanwhile.
2. Add a mapping rule. A mapping declares `detect` + a list of `records`
   (`match` files → `locate` arrays → `fields` via a tiny selector language →
   `emit` via the canonical verbs person/org/post/comment/interest/reaction/search/
   event/message_signal/place/identity/**mirror**/**ad_segment** — the last two feed
   the `50-mirror/` layer). A rule may also declare **`tags`** (e.g. `["person/friend"]`)
   that go on every note it emits, joining the automatic `source/<name>` + type tags
   (so the cross-source graph stays filterable). Selectors handle nested shapes:
   `string_list_data[].value` (Instagram), `string_map_data.*.value`,
   `features[].properties.location.name` + `geometry.coordinates[0]` (GeoJSON),
   `label_values[label=Message].value` (label-predicate — pick a value by its sibling
   label, for the Facebook/Instagram `{label,value}` shape),
   `["title","caption"]` (first non-empty), `{"const": "..."}`. **Scope each rule** to
   the source (e.g. `path_contains: ["facebook"]`) — `extract` sees the whole entity
   tree, so a name-only match can hit a sibling source's file.
3. A mapping **overrides** a same-named Python adapter, and can live in a
   `--mappings <dir>` override dir (no engine edit). See the shipped
   `instagram.json` / `spotify.json` / `facebook.json` for worked examples (Facebook is
   the most complete — 46 rules across people/voice/interests/mirror/places/events/orgs).
4. **Self-improve** (don't stop at coverage): after the new source builds, read
   `_DATA_POINTS.md` — the *field-enrichment-by-source* matrix should show the new
   source's contributions and the *improvement opportunities* list flags what's still
   unmapped; re-review `_STRUCTURE.md` and add a layer to `engine/mappings/brain/layout.json`
   only if a data class has no home; then re-run `analyze.py` and add a fixture/test.

**Adding a goal (the value layer).** `engine/scripts/analyze.py` turns a built brain
into goal workspaces (`95-goals/`), an Obsidian `Dashboard.md`, the `_DATA_POINTS.md`
catalog, `_GRAPH.md`, and Obsidian-Copilot `/commands`. Built-in goals: fundraising, bd,
jobsearch, **datamining** (network patterns), **personalization** (recommend-me-X from your
own places/interests/mirror — the cold-start solver). To support a new goal, add a builder
to its `GOALS` registry (`def build_<goal>(brain, people, ctx) -> (filename, markdown)`) —
it reads the rendered notes' frontmatter (strength/status/company/role/last_contact/sources),
ranks deterministically, and emits a ready AI prompt for the judgment part (don't fabricate).
Wire the goal key into the skill's goal menu in `providers/*/SKILL.md`.

**When Python is still warranted** (cross-file joins, bespoke logic): a source can
be **ONE file** in `engine/scripts/sources/personal/<name>.py` (person) or
`…/company/<name>.py` (company). The registry **auto-discovers** both subfolders —
no registry edit. Builder, privacy, Obsidian/GBrain output, and cross-source merge
all keep working unchanged.

### Quick start (scaffold it)

```bash
python3 engine/scripts/new_source.py twitter            # personal source
python3 engine/scripts/new_source.py greenhouse --company  # company source
```

This stamps out:
- `engine/scripts/sources/personal/twitter.py` (or `company/…` with `--company`),
  copied from `_template.py` as a working no-op adapter (auto-discovered),
- `data/twitter/README.md` (intake folder),
- `tests/fixtures/twitter/` for a tiny synthetic-export stub.

Then fill in `detect()` and `extract()`. Personal modules default
`SUBJECT="person"`; company modules get `SUBJECT="company"` (it controls
personal-vs-company brain rooting + the sibling-vault split).

### The adapter contract

```python
NAME = "twitter"

def detect(file_index) -> bool:
    # file_index: {normalized_filename: [Path, ...]}
    # Return True if signature files for this source are present.
    ...

def extract(root, file_index, all_paths, col) -> set:
    # Parse this source's files and push records into the collector `col`
    # via col.add_*(...). Return the set of normalized keys you consumed.
    ...
```

- **Signature**: JSON/mixed adapters take `extract(root, file_index, all_paths, col)`
  (4 args). LinkedIn is the documented exception — it takes
  `extract(root, file_index, col)` and uses prefix matching. **Match the 4-arg
  form for new sources.**
- **Push everything through `col.add_*`** (`add_person`, `add_org`, `add_post`,
  `add_comment`, `add_reaction`, `add_interest`, `add_message_signal`,
  `set_identity`, `add_uncategorized`). This is how privacy enforcement and
  cross-source person-merge come for free. **Never write notes directly.**
- **No registration step** — `sources/__init__.py` auto-discovers every module in
  `sources/personal/` and `sources/company/`. Just drop the file in the right
  subfolder (or use `new_source.py`).
- **Add a synthetic fixture** under `tests/fixtures/<personal|company>/<entity>/<name>/`
  (the fixture tree mirrors `data/` — one entity folder per identity/company) and make
  `python3 tests/run.py` pass.

---

## Principles (non-negotiable)

- **Local-first, always.** No network calls in the transform. No telemetry.
- **Privacy in code, not in promises.**
  - Never write third-party emails/phones (`col.add_person` drops names matching
    `EMAIL_RE`; never pass email/phone fields).
  - **Never read message bodies** — only `col.add_message_signal(source, name,
    date)` (per-person count + last-contact date). There is no "add body" method.
  - Add sensitive filenames to your source's quarantine set so they're catalogued
    but never imported. When in doubt, redact.
  - **These are the DEFAULT guarantees.** There is an opt-in owner mode
    (`build_vault.py --full`, `Collector(full=True)`) that captures everything
    (emails, phones, every extra column, a `raw-data/` dump of all files incl.
    quarantined) for a user's own local brain. When adding an adapter, pass the
    extra fields through (`email=`, `extra={...}`) and let the Collector decide —
    never special-case PII in the adapter. Default must stay privacy-safe.
- **Deterministic core, intelligence only on the residual.** Keep the heavy
  lifting in tokenless Python; reserve the LLM for genuine unknowns + the two
  synthesis drafts. Never move bulk parsing into an AI step.
- **Never silently drop data.** Unknown files get summarized into
  `99-uncategorized/`, not deleted.
- **Visualizations are PII-safe by construction** — `diagrams.py` uses only the
  catalog (file names, column names, counts), never cell values. Keep it that way.

---

## Dev notes

- **Python 3.8+, standard library only** — no third-party dependencies (must work
  offline).
- **Test against synthetic exports**, never real ones. **Never commit anyone's
  real export or vault** — `.gitignore` already ignores `data/**` and `vault/**`
  (except the placeholder READMEs).
- **Keep the engine canonical & in sync.** The single source of truth is
  `engine/`. After editing it, rebuild **and** install the per-provider skills in
  one step with `python3 packaging/build_skill.py all --install` — this writes the
  `dist/<provider>/second-brain-link.skill` zips and copies the Claude build into
  `~/.claude/skills/second-brain-link/` and the OpenAI build into
  `~/.agents/skills/second-brain-link/`. Don't fork the engine per provider —
  providers are just `providers/<p>/SKILL.md` (+ optional provider-extra files like
  the Codex `agents/openai.yaml`).
- **One source per PR.** Use the Pull Request template checklist.
- Full data model + per-source mapping: see `engine/references/blueprint.md`.

## Code of Conduct

By participating you agree to uphold our [Code of Conduct](CODE_OF_CONDUCT.md).
Report unacceptable behavior to **adrian@vicovan.com**.

## Submitting

- Sign off your commits (DCO): `git commit -s` (adds `Signed-off-by:`).
- MIT licensed — by contributing you agree your contribution is under MIT.
- Fill in the PR checklist (privacy respected, offline-only, fixture added,
  `tests/run.py` green, skill copies in sync, README/CLAUDE updated).
