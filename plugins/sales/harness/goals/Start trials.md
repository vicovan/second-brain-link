---
schema: sbl-goal/1
type: goal
tags:
  - goal
  - agent/sales
id: goal-start-trials
agent: sales
metric: trials
metric_label: trials started
target: 5
by:
status: active
routines:
  - "[[Daily sales]]"
  - "[[Work my replies]]"
  - "[[Weekly sales review]]"
stop_when_overdue: false
stop_after_runs: 0
---
# Start trials

Accounts that started to try, use or buy what you sell — counted from the ledger's `trial` stage
(and `won` beyond it), never from emails sent or leads found. Meetings booked stay a counter on
the dashboard. Set a date in Goals or the Daily tab to get pacing.
