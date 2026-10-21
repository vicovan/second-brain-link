---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/fundraising
id: routine-weekly-raise-update
agent: fundraising
skill: raise-pipeline
goal: "[[Raise my round]]"
schedule: MON 09:00
only_when:
  - "cmd: ledger.py count actions --days 7 | gt 0"
max_per_day: 1
max_minutes: 30
notify: news
enabled: false
status: validated
---
# Weekly raise update

What converted last week and where each funnel leaks (`kpi.py`, rates only once a group has 20),
the proposals that follow from the evidence (`optimize.py`: sources, tiers, angles, channels —
applied only at `autonomous`, otherwise brought to me as one card), every stale Tier 1–2 claim
re-verified on its own page, the Funding Plan rebuilt (the previous one archived), and
`reports/Raise update <date>.md`: since last week · deadlines in the next 30 days · what I changed
and why. Caps and gates never change here.
