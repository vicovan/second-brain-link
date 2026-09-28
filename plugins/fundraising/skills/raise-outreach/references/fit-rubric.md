# Fit rubric — 100 points, scored per package

`package.py fit <key>` computes the mechanical parts from the target record's claims and the
founder's `round.md`; the agent adds the judgement (`--comparable N --why "…"`) and up to three
objections to pre-empt. Re-running `fit` keeps the objections the agent wrote.

| Dimension | Max | How it is scored |
|---|---|---|
| Thesis match | 30 | thesis verdict × stamp — pass ✅ 1.0 · pass 3P/📋 0.7 · unknown 0.4 · fail 0 |
| Cheque & stage | 20 | low end ≥ floor 20 · only the high end ≥ floor 12 · unknown 6 · below the floor 0 |
| Geography & eligibility | 15 | pass 15 · conditional (relocation / entity) 10 · unknown 6 · fail 0 |
| Access | 10 | a ✅ email or form 10 · a third-party path 6 · warm intro only 2 · none 0 |
| Comparable deals | 15 | the agent: a portfolio company or published piece that proves they fund this category |
| Timing | 10 | rolling or open 10 · deadline ≥ 7 days 8 · < 7 days 3 · closed 0 |

**Bands:** ≥ 75 **prepare** · 60–74 **prepare only with a ✅ hook** · < 60 **park** (the reason
goes to the ledger; if the research tiered it high, that mismatch is a lesson for memory).

The score ranks where the founder's evenings go. It never replaces the investor review — a 95
that the reviewer passes on is still parked.
