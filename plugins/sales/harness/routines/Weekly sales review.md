---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/sales
id: routine-weekly-sales-review
agent: sales
skill: sales-optimize
goal: "[[Start trials]]"
schedule: MON 08:45
only_when:
  - "cmd: ledger.py count sent --days 7 | gt 0"
max_per_day: 1
max_minutes: 20
notify: news
enabled: false
status: validated
---
# Weekly sales review

What worked last week by origin, segment, channel, step, signal and strategy (`kpi.py`, rates
only once a group has 20 sends), where the funnel leaks, the proposals that follow from the
evidence (`optimize.py`: signal weights, sequence steps, sources — applied only at `autonomous`,
otherwise one card), lookalikes of the accounts that replied, written to
`48-sales/reports/Sales review <date>.md`. Caps, the level and the send guard never change here.
