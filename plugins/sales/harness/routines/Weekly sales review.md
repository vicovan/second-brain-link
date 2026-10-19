---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/sales
id: routine-weekly-sales-review
agent: sales
skill: sales-optimize
goal: "[[Book sales meetings]]"
schedule: MON 08:00
only_when:
  - "cmd: ledger.py count sent --days 7 | gt 0"
max_per_day: 1
max_minutes: 20
notify: news
enabled: false
status: validated
---
# Weekly sales review

What worked last week by origin, segment, channel and step, at most three changes to make, and
lookalikes of the accounts that replied for the next sweep.
