---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/job-search
id: routine-weekly-job-review
agent: job-search
skill: job-pipeline
goal: "[[Get hired]]"
schedule: MON 08:30
only_when:
  - "cmd: learn.py count applications --days 7 | gt 0"
max_per_day: 1
max_minutes: 20
notify: news
enabled: false
status: validated
---
# Weekly job review

What converted last week and where the funnel leaks — interview rate by portal, role type, market
and source from the ledger (`kpi.py`, rates only once a group has 20 applications) — then the
proposals that follow from the evidence (`optimize.py`: re-weight the scoring, promote or drop
sources, new queries and markets), applied only at `autonomous` and otherwise brought to me as one
card. Written to `45-jobs/reports/Job review <date>.md`. Caps and gates never change here.
