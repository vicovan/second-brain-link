---
schema: sbl-goal/1
type: goal
tags:
  - goal
  - agent/sales
id: goal-book-sales-meetings
agent: sales
metric: meetings
metric_label: meetings booked
target: 10
by:
status: active
routines:
  - "[[Find me leads]]"
  - "[[Work my sales day]]"
  - "[[Work my replies]]"
stop_when_overdue: false
stop_after_runs: 0
---
# Book sales meetings

Real meetings with the right buyers — counted from meetings actually booked (`meeting_booked` in
the ledger), never from emails sent or leads found.
