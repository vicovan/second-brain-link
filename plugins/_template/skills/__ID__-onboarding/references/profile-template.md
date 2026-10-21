---
type: __ID__-profile
title: __SHORT__ profile
updated: <YYYY-MM-DD>
---

> Written by `__ID__-onboarding` into `__LAYER__/profile/profile.md`. The only source of facts.

```settings
level: supervised
daily_target: 5
max_actions_per_run: 10
```

## Facts
- (what the agent may state about the user — every line true, every line checkable)

## Filters (cheapest first)
- (the knock-outs: what to drop before anything is scored)

## Do not claim
- (what is never said)

## Scoring
```scoring
weight.fit: 3
weight.signal: 2
weight.warmth: 2
floor: 60
```
