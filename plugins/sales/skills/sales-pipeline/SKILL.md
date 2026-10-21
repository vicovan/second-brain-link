---
name: sales-pipeline
description: Run the seller's outbound end to end from their Second Brain — onboard if needed, then the daily (replies first, the due steps within the caps, today's leads with a strategy and a reach-out mix per account, the sequences that fit) and the weekly review — the dated note opened first, every send through the guard, holding whatever gates the seller's autonomy setting calls for. Use for "run my sales day", "run today's sales", "find me leads", "work my pipeline", "what's due", "work my replies", the daily or weekly sales routine, or any sales request where the right skill is not obvious.
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
The daily, in the seller's words (made generic): *finding new companies and strategies to sell
[the offer] to, have them try or use it, and different ways to reach out.* The product, its proof
points and the do-not-claim list come only from `profile/offer.md`.

## The shape of every run — the shared runner (`daily.py`)

`S=${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts`. Eleven steps, every day; the scripts guarantee
the shape, this file the words:

```bash
python3 $S/daily.py start --agent sales --routine "Daily sales"     # 0-3: preflight · memory recall · orient (profile check, scout stats, due count, counters, goal pace) · OPEN THE DATED NOTE
```

It prints the goal line with its pace (*trials started 1 of 5 · on pace*), the `=== LAST REPORT ===`
block (pick those up first), what memory says, and the note it opened: **`48-sales/reports/Sell
today <date>.md`** — `## Status` first, then *New today · Due steps · Replies to work · Approvals
waiting · Explored today · Needs you*. Studio shows it beside this chat for the whole run.

| Step | What | Mark it |
|---|---|---|
| 4a replies | `sales-reply` first — the due queue starts with what came back | `daily.py status "worked N replies" --phase acting` |
| 4b due steps | `sales-send` for what `sequence.py due` lists, every act through `send_guard.py` (GATE → one approval card for the batch) | `--phase acting` |
| 4c discover | `sales-scout`: brain first (`warm_rank.py`), then per market with the **coverage gate**, then each company's own site; today's explore slice: `python3 $S/daily.py explore --agent sales` names the new sources / queries to try | `daily.py status "swept N sources: M new" --phase discovering` |
| 5 screen + score | knock-outs → `lead_score.py` → shortlist ≥ floor | `--phase screening` |
| 6 strategy + the note | `sales-research` for the approved rows — the **strategy** (why now · the angle · which offer: try · use · buy · partner · the conversion goal) and the **reach-out mix** per account (`ledger.py set KEY strategy/angle/offer/channels`); then `python3 $S/ledger.py table shortlist \| python3 $S/daily.py section "New today" --agent sales --file -` (account · strategy · angle · best channel · why) — `render_sales.py` keeps that section current too | `--phase shortlisting` |
| 7 act | `sales-sequence` starts the cadence that fits `attrs.channels`; first touches come back as ONE batch; `sales-send` within the caps | `--phase acting` |
| 8 log | `ledger.py log` / `stage` — the guard sets `contacted` on the first real send, the seller sets `won` / `lost`, `trial` when they start one | — |
| 9 render | `render_sales.py` after every change (status calls render too, debounced) | `--phase rendering` |
| 10 reflect | the memory block above (≤ 3 inferred lessons) | `--phase reflecting` |
| 11 handoff | `report.json` → `python3 $S/daily.py close --agent sales --report report.json`; paste what it prints LAST in your reply: the chat report (trials · done · needs you · due next), then the ```report fence | — |

Record what an explored source produced: `python3 $S/explore.py record --sources 48-sales/profile/sources.md --source "<name>" --found N [--converted N]`.

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

- Nothing rendered yet (no `48-sales/Sales Dashboard.md`) → `scout.py starter` first: the brain-only
  shortlist and the dashboard, no network, no cost — then continue.
- Profile incomplete → `sales-onboarding`, then continue.
- Say the level in one line: *"Running supervised — every send waits for your OK."* /
  *"Running autonomous — I send within your caps; first touches still come to you for the first
  batches."* The level is `sending.md`'s, never how the request was phrased.

## The modes — pick from what the seller asked

| Asked | Do |
|---|---|
| "Run my sales day" / "run today's sales" / the daily routine (*Daily sales*) | **daily** — the table above |
| the weekly routine (*Weekly sales review*) | `sales-optimize` — `kpi.py` → `optimize.py` → `48-sales/reports/Sales review <date>.md` (it starts and closes its own run with `daily.py --mode week`) |
| "Find me leads" / "who should I sell to" | `sales-scout` (brain + every market's sources) → the Leads report; offer to research the top rows |
| "Who would take my call?" | `sales-scout` brain tier only (`warm_rank.py`) — no web, no cost |
| "Who's hiring for what I sell?" | `sales-scout` hiring-signal pass only |
| "Research <Account>" / "add these to my pipeline" | `sales-research` per account (state the fan-out first) — the buying team, the strategy, the reach-out mix — then `ledger.py stage KEY researched` |
| "Start sequences" | `sales-sequence` for the targets without one; first touches come back as ONE approval batch |
| "Send what's due" | `sales-send` |
| "Work my replies" / a pasted email | `sales-reply` |
| "Brief me for my next call" | `sales-brief` |
| "How is it going?" | `ledger.py kpi`, then `sales-optimize` if a week has passed |
| A drag on the Lines view ("Move X to Meeting") | `ledger.py stage KEY meeting` — `won`/`lost` only with `--by user` and the reason the seller gives; `trial` when the seller says they started one; `contacted` only from a real send (the guard sets it) |

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

## The report — always this order, and twice

1. The goal counter: trials started (then meetings booked, replies) since the last run — from `ledger.py count`, never typed.
2. What needs the seller: approvals waiting, replies that need their judgement (pricing, legal,
   objections), hand-offs (captchas, walled forms), decisions.
3. What was done: leads found (the sweep line), accounts researched, steps sent per channel,
   what was blocked and why.
4. What is due next, with dates.

Then the ```report fence `daily.py close` prints. Render after every change:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/render_sales.py`. The Lines view, the
dated note's *New today* section and `Sales Dashboard.md` redraw from what it writes.

Example of the closing line: *"Sent 14 (12 ✉, 2 LinkedIn). Parked 2 for you — both pricing
questions. Booked 1, Thursday 10:00. One referral to a COO came in; first touch waits for you."*
