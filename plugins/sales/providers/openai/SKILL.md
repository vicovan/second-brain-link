---
name: sales
description: Run outbound from your own profile and Second Brain — generate leads (warm ties and lost deals in the brain first, then companies on the public web with a reason to buy now, per market, with a coverage gate), research the buying team, run multi-step sequences, send email from your own mailbox within your caps through a deterministic send guard, read and answer replies, and track it all as an indexed layer of your vault. Use for "find me leads", "run my sales day", "work my replies", "who would take my call", or "set up my sales profile". Nothing personal is built in; no bought data.
---

# sales — outbound from your own brain (OpenAI)

> This is the **OpenAI/Codex packaging** of the Second Brain Link `sales` plugin. The scripts are
> byte-identical to the Claude packaging; only this manifest and the layout differ. Workflows are
> in `references/`, code in `scripts/`.

**Nothing about any seller is in this skill.** The offer, the ideal customer, the voice and the
sending settings live in `<surface>/48-sales/profile/`, which `references/sales-onboarding.md`
writes with you.


Every run starts with `python3 scripts/daily.py start --agent sales` (the dated daily note first) and ends with `scripts/daily.py close --report report.json` (the report, twice); Mondays run `scripts/kpi.py` → `scripts/optimize.py`.
## What differs from the Claude packaging — read this first

Codex has no browser-automation tools, so **this packaging does not perform social steps or fill
contact forms.** Those steps are prepared (the message, the profile or form URL) and you send
them, then record it (`scripts/send_guard.py sent …` after a `check` that said ASSIST or ALLOW).
Email is sent through your own mailbox by `scripts/mail.py`, behind `scripts/send_guard.py`,
exactly as on Claude. Directory and LinkedIn signed-in reads fall back to web search.

## The workflows

| Workflow | Read | When |
|---|---|---|
| Onboarding | `references/sales-onboarding.md` | first run, or no profile |
| Lead generation | `references/sales-scout.md` | "find me leads", the morning sweep |
| Research | `references/sales-research.md` | an account to work |
| Sequences | `references/sales-sequence.md` | cadences per account |
| Sending | `references/sales-send.md` | the due steps |
| Replies | `references/sales-reply.md` | replies, meetings |
| Brief | `references/sales-brief.md` | before a call |
| Weekly review | `references/sales-optimize.md` | what works |
| End to end | `references/sales-pipeline.md` | "run my sales day" |

Supporting references: `search-method.md`, `sources.md`, `regional-sources.md`,
`scoring-rubric.md`, `email-playbook.md`, `social-playbook.md`, `form-playbook.md`, the profile
templates (`*-template.md`) and the sequence templates (`sequence-*.md`).
