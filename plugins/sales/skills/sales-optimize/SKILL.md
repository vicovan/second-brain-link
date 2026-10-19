---
name: sales-optimize
description: The weekly review — reply and meeting rates by origin, segment, channel and sequence step from the ledger (rates only once a group has 20 sends, counts below that), what to change (the steps that never get replies, the segments and signals that do, the sources that produce reachable leads), lookalikes of the accounts that replied, and the proposed edits to sequences and signal weights, applied only at autonomous. Use for "how is it going", "what's working", "weekly sales review", or the weekly routine.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion
---

# Sales Optimize — the weekly review

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py kpi
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py kpi --json
```

Write `<sales layer>/reviews/Week <YYYY-Www>.md`:

1. **The numbers** — sent, replies, meetings, opportunities this week and in total. A rate only
   where n ≥ 20; below that, counts and the words "too few to tell".
2. **What works** — the origin, segment, signal kind and step with the best reply and meeting
   rates (n ≥ 20 only), and the denied batches' reasons from memory.
3. **What to change** — at most three proposals, each with its evidence:
   - a sequence step to rewrite or drop (its reply rate vs. the sequence's);
   - a signal weight to raise or lower in `icp.md` (what replied vs. what was sent);
   - a source to add or drop for a market (reachable leads per source).
4. **Lookalikes** — for each account that replied or booked, two or three companies like it (same
   segment, size, market, signal) as `kind: lookalike` rows for the next sweep.

At `autonomous`, apply the weight and sequence edits (show the diff in the report). At
`supervised` or `draft`, propose them in one card and apply what the seller approves. Never edit
`offer.md` facts — those are the seller's.

Save each change and its reason to memory (`observe --source outcome --tags optimize`).
