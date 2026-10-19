---
name: sales-scout
description: Generate the day's leads the way job-scout finds jobs — the brain first (warm and dormant decision-makers, lost deals worth reopening, intro paths), then discovery per market (companies hiring for the buyer and need roles via LinkedIn's public search and careers boards, funding and news, directories, events, public registries, public threads asking for what the seller sells), then each company's own site — merged into one account per company, gated on coverage, cleared of knock-outs, scored on fit, signal, warmth and reachability, and delivered as a shortlist above the seller's floor. No bought data, ever. Use for "find me leads", "who should I sell to", "who's hiring for what I sell", the morning lead sweep, or "who would take my call".
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, Agent, mcp__claude-in-chrome__*
---

# Sales Scout — lead generation

## Memory — every run (recall → act → reflect)
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/memory.py recall --scope sales --tags leads,sources,markets`
first; an outcome (a source that throttled, a market that came back thin across 3+ sources, a
segment that replied) → `observe --source outcome`; at most 3 inferred lessons at the end.

**What to find is not here.** Segments, roles, markets, signals, exclusions, the target and the
floor live only in `profile/icp.md`. No profile → stop and run `sales-onboarding`. This file is the
procedure, the same for every seller (details: `references/search-method.md`).

Work in a scratch folder: `SCRATCH=$(mktemp -d)`. Every source writes ONE file there.

## 1. Frame the run

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/sales_profile.py show icp
SINCE=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/scout.py since-seconds)
```
Build the query grid: buyer roles + need roles (and their synonyms) × every `market.<Name>`.

## 2. Tier 0 — the brain (no network, no cost)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/warm_rank.py --out $SCRATCH/scout-brain.json
```
"Who would take my call?" ends here.

## 3. Tier 1 — discovery, per market (`references/sources.md`, `references/regional-sources.md`)

Run every source the market's pack lists and `icp.md` §3b turns on. **A source that ran and found
nothing still writes its file** with `"markets": [...]` and `"rows": []` — that is how the coverage
gate tells "thin" from "never looked".

- **Hiring signals** (`source.linkedin-public: on`):
  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/linkedin_jobs.py --since-seconds "$SINCE" \
          --keywords "<need role>" --keywords "<buyer role>" ... --location "<market>" ... \
          --out $SCRATCH/scout-linkedin.json
  ```
  Throttled → stop that source today; never retry. Then confirm at the company's own board
  (`ats_fetch.py auto <slug> --filter "<role regex>"`) — the employer's own date and link win.
- **Funding, exec hires, expansions, migrations, launches** — `WebSearch` with time-bounded
  queries per market (patterns in `sources.md`). Each hit → a signal row.
- **Directories, accelerator portfolios, event exhibitor and speaker lists, free-zone and
  chamber directories** — `WebFetch` the public page; Chrome only if `source.chrome-directories: on`,
  read-only, lists only (name, URL, date), never signed in.
- **Registries** (`source.registries: on`) — open company registries where they exist.
- **Intent threads** (`source.threads: on`) — `WebSearch` the `intent_phrases` on public forums
  and posts. A person publicly asking for what the seller sells is the strongest signal there is.
- **LinkedIn signed-in search** — only with `source.linkedin-signed-in: on`; lists only, the pace
  and stop rules in `sources.md` → *On LinkedIn*, without exception.

Signal row shape (one JSON list per source file, or `{source, markets, rows}`):
```json
{"company": "Globex", "domain": "globex.example", "market": "DACH", "kind": "funding",
 "what": "Series B to expand in the Gulf", "url": "https://…", "seen": "2026-01-15",
 "source": "news-search", "own_site": false}
```
`kind` ∈ hiring · funding · exec_hire · migration · expansion · event · intent · news ·
directory · registry · lookalike. `domain` only when you saw the company's own site.

## 4. Tier 2 — the companies' own sites

Merge first, then resolve and confirm:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/scout.py merge $SCRATCH/scout-*.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/scout.py unresolved --limit 15
```
For each unresolved lead (most signals first, at least the top 15): find the official site,
read about / team / press / careers / contact, and write `$SCRATCH/scout-site-<n>.json` rows with
`own_site: true`, the `domain`, `industry`/`size`/`about` when stated, any **published** business
address of a buyer (with the page as `role_source`), and `form_url` when a contact or demo form
exists. Then `scout.py merge` again with every file.

## 5. Coverage is a gate

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/scout.py coverage
```
Exit 1 = a market came back with no qualified accounts from fewer than 3 sources — a
**coverage FAILURE, not a thin market**. Widen: the next source in that market's pack, a
role-synonym pass, lookalikes of accounts that replied (`ledger.py kpi` → the segments that
reply). Merge and check again. Only a market empty across 3+ sources may be reported as thin.

## 6. Score, shortlist, record

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/lead_score.py shortlist
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/scout.py mark-run
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/render_sales.py
```
Knock-outs come off before scoring, each with its rule. The shortlist is what clears the floor,
up to the target. **Short of the target → widen the SOURCES, never the ICP or the floor**, and
say plainly how thin the day was. Leads with no way in are listed, never hidden — "find me a way
in" (form, social, intro) is a follow-up, not a reason to drop them.

## 7. Deliver

Lead with the one line `scout.py coverage` prints (*"Swept N companies from M sources across K
markets — P new since the last run"*), then the shortlist (score · account · why now · way in),
then knock-outs and unreachable counts. Offer: *"Add the top N to the pipeline and research them?"*
At `autonomous`, rows above the floor go to `sales-research` without asking; at `supervised`, ask.

## Never

- Buy, rent or call a data broker, an enrichment API or an email verifier.
- Guess an address and treat it as real (`pattern-unverified` is recorded, never sent).
- Scrape a profile beyond what a list page shows, or read anything behind a login the seller did not open.
