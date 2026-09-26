---
name: raise-onboarding
description: Set up a founder's fundraising profile — company facts and the do-not-claim list, founder bio, the round and its ordered filter chain (minimum cheque, geography, thesis, entity, exclusions), the autonomy level and the settled answers every application form asks — from the brain, the deck and a facts file first, asking only the decisions. Use on first run, when no 46-fundraising profile exists, or when the founder says "set me up", "update my round", "change my filter" or their situation changed.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Raise Onboarding

Everything the other five skills know about the founder and the company lives in five Markdown files
plus a materials folder. This skill writes them. **Nothing else may.**

Without a profile the plugin cannot run honestly: a plan with an invented minimum cheque screens the
wrong universe, and an application drafted from guesses states things the founder never said.
**Never proceed on assumptions — run this instead.**

## Where the profile goes

```
<brain>/46-fundraising/profile/
    company.md    product truth, traction, proof points — and the "## Do not claim" list
    founder.md    roles, dates, education, links, references
    round.md      the round, the constraints, the ordered filter chain  (frontmatter = settings)
    answers.md    §0 the autonomy level + settled form answers           (frontmatter = settings)
    stories.md    origin · why now · why you · the hardest thing · unfair advantage
    materials/    deck, facts file / one-pager, CV   (Studio's settings panel uploads here)
```

The folder is resolved, never hardcoded:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/paths.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/founder_profile.py   # what exists, what is missing
```

## Step 0 — see what already exists, create only what is missing

A file that exists is **not rewritten** unless the founder asked to update it. Show a diff of what
would change before writing an update. A run that can only fill three files writes those three and
says which are still missing — never placeholders.

## Step 1 — read before asking

In this order, and quote what you found in one line each so the founder sees the work:

1. `materials/` — the deck, the facts file, the one-pager, the CV. **A facts file is the strongest
   source there is**: when one exists, `company.md` is built from it and its do-not-claim list is
   copied verbatim.
2. The brain: `00-me/identity.md` (or `00-org/` in a company brain), `40-career/`, `90-synthesis/`,
   `95-goals/fundraising.md` (who in the network invests — note it, the outreach skill uses it).
3. Only then ask — and ask **decisions**, not facts you could have read.

## Step 2 — the files

Templates with a worked example (a fictional fintech founder, not a real one) are in
`references/`: `company-template.md`, `founder-template.md`, `round-template.md`,
`answers-template.md`, `stories-template.md`. Follow their shape exactly — `round.md` and
`answers.md` carry **machine-read frontmatter** that `founder_profile.py` parses.

### round.md — the decisions, asked with AskUserQuestion

| Key | Ask | Notes |
|---|---|---|
| `min_net_cash` | The smallest cheque worth the founder's time | **Net**: fees are subtracted, contingent "up to" money is not counted |
| `geography_ok` | Where they can raise from | region tags: global, us, europe, cee, nordics, mena, israel, anz, asia, latam |
| `relocation` | Would they move for a program | `ok` turns a US-only fund into *conditional*, not *out* |
| `entity_now` / `entities_ok` | What exists today; what they would form | e.g. `none` / `[us-delaware, eu]` |
| `cofounder` | open / closed / has one | shapes solo-founder programs |
| `exclusions` | Hard noes | e.g. `[crypto]` — matched against the program's own page, not a post |
| `thesis_keywords` / `off_thesis` | What the company *is*, in funders' words; what it is not | drives the desk screen |
| `filter_order` | default `[floor, geo, thesis, access, entity, exclusions]` | cheapest-first: money and geography kill most candidates from one line |
| `max_research_agents` | default 3 | the verification fan-out cap — cost is a setting |
| `followup_days` | default 7 | when a sent email with no reply becomes due |
| `ask` / `instrument` | the round size and instrument, or `undecided` | `undecided` becomes a founder decision in the plan |

### answers.md §0 — autonomy

`level: supervised` is the shipped default. Explain both levels in two lines and let the founder
choose; never set `autonomous` because a request sounded eager. `max_submits_per_run` defaults to 5.

### company.md — "## Do not claim"

One bullet per term, the term first (`- users — no user numbers are published`). These are matched
as whole words by `lint_claims.py`. Ask: *"What must an application never say — numbers you don't
publish, features that aren't shipped?"* A company with no such list is a company that will
eventually overclaim in a form.

## Step 3 — finish

Run `founder_profile.py` again and show what it parsed. Then offer the next step: *"Build my funding plan"*
(`raise-plan` via `raise-research`), or *"Screen this list"* if the founder has lists to hand.
