---
name: __ID__-pipeline
description: Run the __WHAT__ day end to end from the user's Second Brain — onboard if needed, discover what is new (brain first, proven sources, an explore slice), screen and score, act within the user's autonomy level, log, render and report — holding every gate the setting asks for. Use for "run my __WHAT__", the daily routine, the weekly review, or any __WHAT__ request where the right skill is not obvious.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, Skill, Agent, TodoWrite, AskUserQuestion
---

# __SHORT__ Pipeline

The orchestrator. It **owns no logic of its own** — it sequences the scripts and the other skills
through the shared runner and holds the gates. `S=${CLAUDE_PLUGIN_ROOT}/skills/__ID__-core/scripts`.

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/__ID__-core/references/`), scope `__ID__`.
1. `memory.py recall --scope __ID__` first (daily.py prints it); apply it, never re-ask what it answers.
2. The user states a fact or a rule → `observe --source user` at once.
3. An outcome lands → `observe --source outcome` with the evidence.
4. Last: at most 3 inferred lessons → `observe --source agent` (flagged as inferred). End with *"Learned: …"*.

## The modes

| Asked | Mode |
|---|---|
| the daily routine, "run my __WHAT__" | **daily** (below) |
| the weekly routine, "how is it going" | **week**: `kpi.py` → `optimize.py` → `reports/__WEEKLY__ <date>.md` |
| "set me up" / no profile | `__ID__-onboarding`, then continue |

## The daily — the eleven steps (daily.py guarantees the shape)

```bash
python3 $S/daily.py start --agent __ID__ --routine "Daily __WHAT__"     # 0-3: preflight · recall · orient · the dated note (opened FIRST)
```
Read what it printed: the goal line and its pace, the LAST REPORT block (pick those items up first),
what memory says, and the note path. Say the `level:` in one line.

4. **Discover** — brain first (ties in `10-people`, `_correlations`, the user's own notes), then the
   proven sources, then today's explore slice: `python3 $S/daily.py explore --agent __ID__` names them.
   `python3 $S/sources.py discover` is the stub to replace with the real discovery.
   After each source: `daily.py status "swept <source>: N new" --phase discovering`.
5. **Screen + score** — `python3 $S/score.py` (deterministic, from `profile/scoring.md`); knock-outs
   first; `ledger.py upsert` the survivors (they land on the first stage).
6. **Shortlist** — the day's ranked table into the note: `ledger.py table shortlist | daily.py section "New today" --file -`.
7. **Act** — behind the gates of `level:` (supervised by default): `python3 $S/actions.py <item>`;
   confirm-gated stages ask with `AskUserQuestion`. `daily.py status "…" --phase acting` after each.
8. **Log** — every outcome through `ledger.py stage KEY TO` / `ledger.py log`; follow-up clocks `ledger.py next`.
9. **Render** — happens after every status call (`render.py`), debounced.
10. **Reflect** — the memory block above; `daily.py status "reflecting" --phase reflecting`.
11. **Handoff** — write `report.json` (done with evidence · not_done · next · needs_you · news) and
    `python3 $S/daily.py close --agent __ID__ --report report.json`; paste what it prints as the last
    thing in your reply (the chat report, then the ```report fence).

## The gates — never your call
`level:` in `profile/profile.md`: draft · supervised (default) · autonomous. Never create an
account, type a credential, solve a CAPTCHA, send, post, buy or book.

## The report — always this order
The goal counter first; what was done; what needs the user; what is due next, with dates.
