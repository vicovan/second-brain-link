# fundraising — run a raise from your Second Brain

A Second Brain Link plugin. It screens funds and programs against **your own filter chain**,
verifies the survivors on their own sites, writes a dated **Funding Plan**, drafts applications and
investor emails, and tracks every conversation — as the `46-fundraising/` layer of your brain, and as
the **Fundraising Agent** in Second Brain Studio.

> **It never sends anything.** Emails are written as vault notes and, where a Gmail *draft* tool is
> available, as Gmail drafts. You press send.

## What it does

| You say | It does | Skill |
|---|---|---|
| "Set me up" | builds your profile from the brain, your deck and your facts file; asks only the decisions | `raise-onboarding` |
| "Screen this list" (paste, or a CSV) | imports leads as unverified, runs your filter chain with no network, reports what survived | `raise-research` |
| "Build my funding plan" | verifies survivors on their own sites (capped fan-out), tiers them, writes the plan | `raise-research` → `raise-plan` |
| "Apply to <program>" | drafts answers within tested limits, lints them against your facts, fills the form, verifies it in the DOM, submits or asks — per your autonomy level | `raise-apply` |
| "Draft this week's emails" | one email per target with a verified hook, linted, saved as a note + Gmail draft | `raise-outreach` |
| "What's due?" / "Record a reply" | follow-ups, deadlines, re-verification; outcome logging and meeting prep | `raise-pipeline` |

Commands: `/raise` · `/fund-onboard` · `/fund-plan` · `/fund-apply` · `/fund-email` · `/fund-due` ·
`/fund-outcome` · `/fund-kpi`.

## The rules it keeps

- **Every claim about a third party carries its evidence** — ✅ own site (URL + date) · 3P ·
  📋 desk-screened · ⚠ unverified. A list you paste is a lead, never a source. A deadline without a
  confirmed year is ⚠.
- **Every claim about you traces to your profile.** `lint_claims.py` refuses a number that is not in
  your profile, anything on your do-not-claim list, a leftover `[CONFIRM]`, or an answer over its
  limit. Red stops that item at every autonomy level.
- **Your filter, your order.** Minimum *net* cheque → geography → thesis → access → entity →
  exclusions, set in `round.md`. Change it and `ledger.py rescreen` re-tiers everything without
  fetching a page.
- **Autonomy is a setting.** `level: supervised` (the default) gates pick, answers and submit.
  `level: autonomous` submits after lint and DOM verification, up to `max_submits_per_run`. Logins,
  fees, required videos and missing facts stop that one application at both levels.
- **Cost is a setting.** Verification fans out to at most `max_research_agents` (default 3), and the
  agent states the fan-out before spending it.

## Where your data lives

Nothing personal ships in this plugin. Everything is written into **your** brain:

```
<brain>/46-fundraising/          notes you read: Funding Plan, dashboard, KPI, targets/,
                                 applications/<YYYY-MM-DD>/<key>/, outreach/<YYYY-MM-DD>/, research/,
                                 plans/ (archived plans), profile/ (written only by onboarding)
<brain>/.plugins/fundraising/    machinery, hidden from the tree: targets.jsonl, events.jsonl,
                                 lessons.md, _FUNDRAISE_GENERATED.json
```

Outside a brain the state root is `$FUNDRAISE_HOME`, else `~/.second-brain/fundraising`.
`python3 skills/raise-research/scripts/paths.py` prints every decision.

The layer has its own manifest, so the engine's `build_vault.py --refresh` treats it as your files
and leaves it alone.

## Install

```bash
python3 packaging/build_plugin.py fundraising                         # both providers
python3 packaging/build_plugin.py fundraising --provider claude --install
#   → ~/.claude/skills/fundraising — loaded by Claude Code as fundraising@skills-dir,
#     and discovered by both Second Brain Studios (desktop and browser)
claude --plugin-dir plugins/fundraising                               # or load from source
```

Codex (`--provider openai --install` → `~/.agents/skills/fundraising`) prepares plans, answers and
drafts, but has no browser tooling, so it does not fill forms.

Optional daily reminder (silent unless something is due): see `docs/scheduling.md`.

## Network

Declared in `.claude-plugin/plugin.json`: public fund and program pages (WebSearch/WebFetch), program
forms through the Chrome integration, and the Gmail connector for **draft creation only**. The
Second Brain Link engine stays zero-network; this plugin is a separate distribution surface.

## Honest limits

It reads public pages and the lists you hand it, and it will be wrong where they are silent — it
says ⚠ rather than guessing. Forms change without notice; a failed fill falls back to paste-ready
answers. Warm paths inherit the engine's name-only identity matching. It only knows an email was
sent when you tell it.
