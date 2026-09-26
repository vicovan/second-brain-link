---
name: raise-research
description: Build and refresh the fundraising target universe — import lists the founder pastes or drops as CSV, screen every lead against the founder's own ordered filter chain with no network, verify the survivors on each fund's or program's own site with a capped fan-out, and stamp every claim with its evidence. Use for "screen this list", "find programs open now", "verify these funds", the research half of "build my funding plan", or when dated claims have gone stale.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, Agent, TodoWrite
---

# Raise Research

Turns names into **target records with evidence**. It owns the ledger's claims and verdicts; it
never drafts anything and never contacts anyone.

The record, the stamps and the state machine are defined in `scripts/ledger.py`'s docstring and in
`references/verification.md`. Read that reference before the first verification of a run.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/founder_profile.py    # the filter chain in force
```

## The loop — cheapest first, always

```
ingest (📋)  →  rescreen (no network)  →  state the fan-out  →  verify survivors (✅/3P/⚠)
            →  rescreen with real claims  →  tier + fit  →  render
```

### 1. Ingest — a list is a lead, never a source

- **CSV** (an Airtable or spreadsheet export):
  `python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py import-csv <file> --origin <label>`
  Header aliases cover Name/Fund, About/Description, Website/URL, Location/Region, Partner, Check…
- **Pasted text** (a LinkedIn listicle, a newsletter): save it to a scratch file, then
  `python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py import-text <file> --origin <label>`
  Lines shaped "Person - Fund" import the person as a partner of that fund.
- **A shared Airtable/Notion VIEW link** cannot be fetched — it is a JavaScript app. Say so in one
  line and ask the founder for a CSV export (Airtable: the view's ⋯ menu → Download CSV). Do not
  try the browser to scrape it.
- Programs from a post: import with `--kind program`, and record the post's deadline as a claim
  with stamp ⚠ — **posts carry no year** until a page confirms it.

Everything imported starts 📋. The list's own assertions ("geo-agnostic", "$1M") stay in
`origin_text`; they are never claims.

### 2. Rescreen — no network

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py rescreen
```

Applies the founder's `filter_order` to what is known. `unknown` passes and is marked; only a
positive signal fails a record. Report the result as **how many survived and which filter removed
the rest** — that is the founder's first read of their own filter.

### 3. State the fan-out, then verify

Say it before spending it: *"N survivors; verifying with 3 parallel agents (your
max_research_agents), ~N/3 sites each."* Then verify in priority order — programs with a deadline in
the next 60 days, then untiered survivors with the strongest desk signal.

Each subagent gets a batch of records (key, name, url, the claims already held) and **returns claims,
not prose** — the shape in `references/verification.md`:
`{"key": …, "claims": {"cheque": {"v": …, "stamp": "✅", "src": URL, "at": DATE}, …},
"people": […], "notes": "…"}`. Rules it must follow: read the target's **own** site; a claim it
could not confirm is ⚠ or omitted, never guessed; a deadline needs its year on the page
(`year_confirmed: true`); cash for a program is split into gross, fee and contingent.

**Only the main session writes the ledger.** For each returned record:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py upsert --json '<the returned record>'
```

then `rescreen` again — real claims change verdicts.

### 4. Tier and fit

Your judgement, recorded with its reason. Tiers (the plan groups by them):

| Tier | Means |
|---|---|
| 1 | a dated cohort door that clears every filter |
| 2 | a fund with a cold path and an exact-thesis signal on its own site |
| 3 | home-turf / regional first cheques |
| 4 | warm-intro builds (no cold path; worth engineering an intro) |

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py set-tier <key> --tier 2 --fit 8 --why "<one line, from a ✅ claim>"
```

Manual verdict overrides (with a reason) when the desk screen is wrong:
`ledger.py set-verdict <key> thesis pass --why "…"`.

### 5. Sweep for programs (only when asked, or when Tier 1 is empty)

WebSearch for accelerators and fellowships **open now** that clear the floor, for the founder's
geography and stage. Every find is a new `--kind program` record with the deadline ⚠ until the
program's own page confirms the year. Never add a program whose cash is below the floor after fees.

### 6. Write the research note and render

`46-fundraising/research/<YYYY-MM-DD> Research.md`: what was ingested (per origin), screened,
verified, dropped by which filter, and the fan-out spent. Then:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/render_brain.py --quiet
```

## Re-verification

Dated claims (deadline, open status, cohort) go stale after 7 days, static ones after 30.
`ledger.py stale` lists them; `ledger.py due` includes them. A weekly run re-verifies stale dated
claims on Tier 1–2 records before the plan is rebuilt.

## What this skill never does

Draft an email or an answer · contact anyone · pay for or log into a database · treat a list's claim
as verified · resolve a ledger conflict by inference (surface it as a question in the plan).
