# scoring.md — template

Copy into `48-sales/profile/scoring.md`. The lead score (`lead_score.py`) reads its weights from
`icp.md` (`weight.<signal>`); this file holds the seller's own notes on what matters and the block
the weekly optimizer may append to — nothing else. The worked example is fictional.

```markdown
---
type: sales-scoring
title: Scoring
updated: <today>
---

# Scoring

```scoring
weight.fit: 3          # the segment and the roles match the ICP
weight.signal: 2       # a dated reason to buy now
weight.warmth: 2       # a tie in the brain, a lost deal to revive
weight.reach: 1        # a published address, a form, an intro path
floor: 60
```

## Optimizer weights

<!-- optimizer:begin -->
<!-- optimizer:end -->
```
