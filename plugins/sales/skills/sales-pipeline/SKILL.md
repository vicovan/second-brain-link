---
name: sales-pipeline
description: Run the seller's outbound end to end from their Second Brain — onboard if needed, generate today's leads (brain first, then the public web per market, with a coverage gate), research the approved accounts, start sequences, send the due steps from the seller's own mailbox and browser within the caps, work the replies, book meetings and report — holding whatever gates the seller's autonomy setting calls for. Use for "run my sales day", "find me leads", "work my pipeline", "what's due", "work my replies", the daily sales routine, or any sales request where the right skill is not obvious.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, Skill, Agent, TodoWrite, AskUserQuestion, mcp__claude-in-chrome__*
---

# Sales Pipeline

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/sales-send/references/`). Tool:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/memory.py`, scope `sales`, tags `leads,research,sequence,send,reply`.
1. **First:** `memory.py recall --scope sales --tags leads,research,sequence,send,reply` — apply it, say in one line which items changed what you do, never re-ask what it answers.
2. **The seller says a preference, rule or correction** → `observe --source user` at once (`--scope shared` if it holds for every agent).
3. **An outcome lands** (a reply, a meeting, a bounce, a "not now", a denied batch and its reason) → `observe --source outcome` with the evidence, `--match` the item it strengthens.
4. **Last:** at most 3 inferred lessons → `observe --source agent`; end with *"Learned: …"*.

The orchestrator. It **owns no logic of its own** — it sequences the other skills and holds the gates.

```
leads ─► research ─► sequence ─► send (guarded) ─► replies ─► meeting ─► brief
  ▲                                                   │
  └──────────── optimize (weekly, from the ledger) ◄───┘
```

| Stage | Skill |
|---|---|
| Profile: offer, ICP, voice, sending | `sales-onboarding` |
| Lead generation: the daily sweep, coverage, score, shortlist | `sales-scout` |
| One account in depth: buying team, a way in, why now | `sales-research` |
| Cadence per account | `sales-sequence` |
| The due steps: email, social, forms — every one through `send_guard.py` | `sales-send` |
| Replies: read, classify, answer, book, suppress | `sales-reply` |
| Before a call | `sales-brief` |
| Weekly: what works, what to change | `sales-optimize` |

Invoke them with the Skill tool (`sales:<skill>`). Never re-implement one here.

## Step 0 — orient, in one line each

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/paths.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/sales_profile.py check
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/scout.py stats
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/sequence.py due
```

- Nothing rendered yet (no `48-sales/Pipeline.md`) → `scout.py starter` first: the brain-only
  shortlist and the dashboard, no network, no cost — then continue.
- Profile incomplete → `sales-onboarding`, then continue.
- Say the level in one line: *"Running supervised — every send waits for your OK."* /
  *"Running autonomous — I send within your caps; first touches still come to you for the first
  batches."* The level is `sending.md`'s, never how the request was phrased.

## The modes — pick from what the seller asked

| Asked | Do |
|---|---|
| "Run my sales day" / the daily routine | replies first (`sales-reply`) → due steps (`sales-send`) → if the shortlist is stale, leads (`sales-scout`) → report |
| "Find me leads" / "who should I sell to" | `sales-scout` (brain + every market's sources) → the Leads report; offer to research the top rows |
| "Who would take my call?" | `sales-scout` brain tier only (`warm_rank.py`) — no web, no cost |
| "Who's hiring for what I sell?" | `sales-scout` hiring-signal pass only |
| "Research <Account>" / "add these to my pipeline" | `sales-research` per account (state the fan-out first), then `ledger.py stage KEY target` |
| "Start sequences" | `sales-sequence` for the targets without one; first touches come back as ONE approval batch |
| "Send what's due" | `sales-send` |
| "Work my replies" / a pasted email | `sales-reply` |
| "Brief me for my next call" | `sales-brief` |
| "How is it going?" | `ledger.py kpi`, then `sales-optimize` if a week has passed |
| A drag on the Pipeline board ("Move X to Meeting") | `ledger.py stage KEY meeting` — `won`/`lost` only with `--by user` and the reason the seller gives |

## The gates — how many is the seller's setting, never your call

- `send_guard.py` decides every outward act: ALLOW · GATE · ASSIST · BLOCK. It is code; you do
  not argue with it, retry around it or re-word a blocked message to slip it through.
- **GATE** → one approval card for the whole batch (`batch.py add` per message, then `batch.py card`,
  whose ```approval fence goes in the reply right before ONE `AskUserQuestion`): the recipients, the
  real text of each message in the batch note, where each hook came from, the cap counter ("12 of 25
  today → 18 after this") and the consequence ("sends from <mailbox> · cannot be unsent"). Options: *Approve all* · *Approve, skip some* · *Edit first* ·
  *Deny — say why*. On approve → `ledger.py approve --batch <id>`; on deny →
  `ledger.py deny --batch <id> --reason "<their words>"` and save the reason to memory.
- **ASSIST** → social automation is off: open the profile in Chrome, put the message in the box
  (or show it to copy), and the seller presses Send; they say "sent" → `send_guard.py sent`.
- **BLOCK** → never sent; it is listed in the report with its rule.
- **First ever** real send and first ever social action: always a GATE, whatever the level.

## The report — always this order

1. The number that matters: replies, meetings booked since the last run.
2. What needs the seller: approvals waiting, replies that need their judgement (pricing, legal,
   objections), hand-offs (captchas, walled forms), decisions.
3. What was done: leads found (the sweep line), accounts researched, steps sent per channel,
   what was blocked and why.
4. What is due next, with dates.

Render after every change: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/render_sales.py`.
The Pipeline board and `Pipeline.md` redraw from what it writes.

Example of the closing line: *"Sent 14 (12 ✉, 2 LinkedIn). Parked 2 for you — both pricing
questions. Booked 1, Thursday 10:00. One referral to a COO came in; first touch waits for you."*
