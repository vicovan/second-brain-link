---
schema: sbl-goal/1
type: goal
tags:
  - goal
  - agent/__ID__
id: goal-__GOAL_SLUG__
agent: __ID__
metric: __METRIC__
metric_label: __METRIC_LABEL__
target: __TARGET__
by:
status: active
routines:
  - "[[Daily __WHAT__]]"
  - "[[Weekly __WHAT__ review]]"
stop_when_overdue: false
stop_after_runs: 0
---
# __GOAL__

Counted from the ledger's `__SUCCESS__` stage (`ledger.py count __SUCCESS__`) — real outcomes,
never activity. Set a date in Goals or the Daily tab to get pacing.
