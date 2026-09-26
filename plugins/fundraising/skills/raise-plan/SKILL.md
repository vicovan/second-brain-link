---
name: raise-plan
description: Write the founder's Funding Plan from the target records and the profile — the application ledger, a dated timeline with days remaining and branches on pending decisions, the tiers, the founder decisions with a recommendation each, the screening tables, the partner track and what to do this week — archiving the previous plan. Use for "build my funding plan", "update the plan", "what should I do this week", after a research run, or after an outcome changes the ledger.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Raise Plan

Projects the records into **`46-fundraising/Funding Plan.md`** — the note Studio opens beside the
chat. It invents nothing: every row comes from a record (with its stamp) or from the profile.

## Before writing

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/founder_profile.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py stats
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py list --json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py due --days 60
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py stale
```

If Tier 1–2 records carry stale dated claims, say so and offer a re-verification pass
(`raise-research`) **before** writing — a plan built on last month's deadlines is the failure this
skill exists to prevent.

## Archive, then write

If `Funding Plan.md` exists, move its content to `46-fundraising/plans/Funding Plan <date of that
plan>.md` (the date from its frontmatter `updated:`) — never delete it. The new plan is regenerated,
not appended; "what changed since last time" is answered by comparing the two.

Frontmatter:

```yaml
---
type: fundraising-plan
title: Funding Plan
updated: <today>
targets: <count>
level: <supervised|autonomous>
tags: [fundraising, plan]
---
```

## The fixed sections — in this order, every time

1. **Stamps legend** — ✅ own site (dated) · 3P · 📋 desk-screened · ⚠ unverified · ⏳ stale.
   Plus one honest line: this plan reads public pages and the founder's lists; where those are
   silent, it says ⚠ rather than guessing.
2. **The filter** — the founder's chain, verbatim from `round.md`, and what it removed this run
   (counts per filter from `ledger.py rescreen`).
3. **§0 Ledger** — every record with an application or a contact: filed/sent date, outcome, next
   window. **Conflicts are questions, not guesses**: when two sources disagree (a program shows a
   window open for a batch the founder believes rejected them), list the evidence and the question.
4. **§1 Timeline** — dated rows from today: date · days left · action · net cash · stamp. Rolling
   doors in their own block. **Branches** where a pending decision changes the plan ("If <program>
   accepts → …; if not by <date> → …"). A deadline with `year_confirmed: false` is shown ⚠.
5. **§2 Tiers** — Tier 1 dated cohort doors · Tier 2 cold path + exact thesis (a table: target —
   partner · why this one · cold path · cheque · stamp) · Tier 3 home turf · Tier 4 warm-intro builds
   · **Don't bother**, grouped by the filter that removed each.
6. **§3 Founder decisions** — each `undecided` field in `round.md`, and anything the records imply
   (e.g. most Tier 2 leads need a stated round size). **Recommend one option with a reason; the
   founder decides.** Never edit the profile to reflect a recommendation.
7. **§4 Screening tables** — one per origin (each imported list): survived / conditional / out, with
   the filter and one-line reason.
8. **§5 Partner track** — integrations and design partners before corporate development, in that
   order (an acquisition conversation before a pilot reads as "couldn't raise").
9. **§6 Corrections** — contradictions found between the founder's materials and the facts file,
   listed, not fixed.
10. **This week, in order** — at most seven numbered actions, the cheapest-highest-odds first, each
    naming the skill that does it ("Draft the Tier 2 emails — raise-outreach").

Link targets as `[[<Name> (target)]]` (their note titles) — never an aliased link inside a table
cell. Never link a note that does not exist.

## After writing

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/render_brain.py --quiet
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py mark-run
```

Report in four lines: the nearest deadline, how many doors are live after the filter, the one
decision the founder owes, and the first action this week.
