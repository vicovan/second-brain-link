---
schema: sbl-goal/1
type: goal
tags:
  - goal
  - agent/job-search
id: goal-get-hired
agent: job-search
metric: interviews
metric_label: interviews
target: 3
by:
status: active
routines:
  - "[[Daily job scout]]"
stop_when_overdue: false
stop_after_runs: 0
---
# Get hired

Land interviews for roles that fit — counted from the results you record (an invitation to
interview), never from applications sent. When the target is reached the scout pauses itself.
