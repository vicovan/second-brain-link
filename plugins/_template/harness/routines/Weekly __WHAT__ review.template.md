---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/__ID__
id: routine-weekly-__ID__-review
agent: __ID__
skill: __ID__-pipeline
goal: "[[__GOAL__]]"
schedule: MON 09:30
only_when:
  - "cmd: ledger.py count actions --days 7 | gt 0"
max_per_day: 1
max_minutes: 20
notify: news
enabled: false
status: validated
---
# Weekly __WHAT__ review

What converted last week and where the funnel leaks (`kpi.py`), the proposals that follow from
the evidence (`optimize.py` — re-weight the scoring, promote or drop sources, new queries), applied
only at `autonomous` and otherwise brought to me as one card; written to `reports/__WEEKLY__ <date>.md`.
