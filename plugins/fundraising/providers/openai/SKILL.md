---
name: fundraising
description: Run a raise from your own profile — screen funds and programs against your filter chain, verify the survivors on their own sites, write a dated Funding Plan, draft application answers and investor emails (never sent), and track replies and follow-ups as an indexed layer of your Second Brain vault. Use for "build my funding plan", "screen this list of investors", "draft investor emails", "what's due in my raise", or "set up my fundraising profile". Nothing personal is built in.
---

# fundraising — the whole raise, from your own profile (OpenAI)

> This is the **OpenAI/Codex packaging** of the Second Brain Link `fundraising` plugin. The scripts
> are byte-identical to the Claude packaging; only this manifest and the layout differ. Workflows
> are in `references/`, code in `scripts/`.

**Nothing about any founder or company is in this skill.** Facts, the round and the filter chain
live in `<surface>/46-fundraising/profile/`, which `references/raise-onboarding.md` writes with you.

## What differs from the Claude packaging — read this first

Codex has no browser-automation tools, so **this packaging does not fill application forms.** It
drafts every answer into the application folder, lints it, and hands you the form URL; you paste and
submit, then record it (`ledger.py set-status <key> filed --by founder`). `level: autonomous`
therefore covers research, the plan and drafting — there is no submit to automate. Emails are
drafts in the vault, never sent, exactly as on Claude.

## The workflows

| Workflow | Read | When |
|---|---|---|
| Onboarding | `references/raise-onboarding.md` | first run, or no profile |
| Research | `references/raise-research.md` | "screen this list", verification, stale claims |
| The plan | `references/raise-plan.md` | "build my funding plan" |
| Applying | `references/raise-apply.md` | a program is picked — up to the form, then hand off |
| Outreach | `references/raise-outreach.md` | emails, intros, follow-ups |
| End to end | `references/raise-pipeline.md` | "run my raise", "what's due", "record a reply" |

Supporting references: `verification.md`, `filter-chain.md`, `sources.md`, `email-playbook.md`,
`field-policy.md`, `form-patterns.md`, and the profile templates (`*-template.md`).
