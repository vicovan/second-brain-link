# Scoring rubric — what `lead_score.py` computes

```
score = 100 × (0.30·fit + 0.30·signal + 0.20·warmth + 0.20·reach)
```

| Term | From | How |
|---|---|---|
| fit | `icp.md` §1–3 | the mean of: market (in a profile market 1 · elsewhere 0 · unknown ½), role (a hiring or contact role matches a buyer / champion / need role 1 · else 0.4), industry (named 1 · another stated 0.3 · unknown ½), size (in band 1 · outside 0 · unknown ½) |
| signal | the account's signals | Σ weight(kind) × ½^(age / half-life), ÷ 6, capped at 1. News-like signals age on `half_life_days` (default 30); ties and lost deals (`brain`, `revival`) age over a year |
| warmth | the contacts | the strongest tie: strength/5 × recency (a year's half-life). A name-only match (`tie: possible`) counts zero |
| reach | `reach_of()` | green (warm · intro · public) 1.0 · yellow (form · social) 0.6 · red (guessed address) 0.2 · hand-off 0 |

Default signal weights (override in `icp.md` as `weight.<kind>`): hiring 3 · migration 3 ·
intent 3 · revival 3 · funding 2 · exec_hire 2 · brain 2 · lookalike 2 · expansion 1 · event 1 ·
news 1 · directory 1 · registry 1.

**Knock-outs** are removed before scoring and listed with the rule: an `exclude` or
`competitors` term, an `exclude_domains` domain, the do-not-contact list, an existing customer
(a won deal in the brain or the ledger), an `exclude_markets` market, a size outside the band
when `size_strict: on`.

**Floor and target.** Deliver what clears `floor`, up to `daily_target`. Short → more sources.

**Learning.** `ledger.py kpi` shows reply and meeting rates by origin, segment, channel and step
once a group has 20 sends (counts only below that). `sales-optimize` proposes weight changes from
it; at `autonomous` it may apply them to `icp.md`, otherwise it asks.
