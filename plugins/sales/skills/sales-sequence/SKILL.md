---
name: sales-sequence
description: Pick or build the cadence for each target account — the steps, channels and waits that fit its origin (revival, warm, intro, cold, not-now), which contacts it runs to, and the brief for each step — and start it, so the due steps come up on schedule and stop the moment someone replies, bounces, unsubscribes or books. Use for "start sequences", "put <account> on a sequence", "make me a sequence for <segment>", "change the cadence", or "stop <account>".
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion
---

# Sales Sequence

A sequence is a readable note in `<sales layer>/sequences/` — a steps table (`n · channel ·
wait_days · kind · requires · brief`). The shipped five are seeded by `sequence.py seed`:
**Revival** (reopen a lost deal), **Warm** (new offer to someone you know), **Intro** (ask the
connector — never cold to the target), **Cold** (signal-led), **Not now** (wake on their date).
Their templates are `references/sequence-*.md`.

The plan lives in the sequence; **the words are written per contact at send time** from the voice
layer and the account's evidence. There is no mail-merge and no `{{first_name}}`.

## Start

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/sequence.py list
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py list --stage target
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/sequence.py start <KEY> --sequence "<Name>" --contacts "<A,B>"
```

- Match the sequence to the account's `origin` (`applies_to`). A cold account where the brain
  also holds a tie gets the warm one.
- Run to the people research chose — usually one buyer and, later, one champion; never the
  whole team at once.
- A `requires: social` step on a seller with `social_auto: off` becomes an **assisted** step (the
  seller presses Send); a `requires: connected` step waits until `ledger.py log connected` is recorded.
- At `supervised`, show the plan (accounts × sequence × contacts) in one card and start what the
  seller approves. At `autonomous`, start them and list what started.

## Change

- A new sequence: write the note in the same table shape (copy a template), then `sequence.py list`
  to check it parsed. Keep it short: 3–5 steps over 2–3 weeks; the last step closes the loop.
- `sequence.py stop <KEY> [--contact NAME] --reason "<why>"` — the seller said stop, or the
  account changed.
- `sequence.py timeline <KEY>` shows each contact's steps: sent / due / waiting / upcoming /
  skipped (no reachable channel) / stopped.

Then `render_sales.py`, and offer `sales-send` for what is due today.
