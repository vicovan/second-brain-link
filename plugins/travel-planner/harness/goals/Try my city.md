---
schema: sbl-goal/1
type: goal
tags:
  - goal
  - agent/travel-planner
id: goal-try-my-city
agent: travel-planner
metric: went
metric_label: places tried
target: 8
by:
status: active
routines:
  - "[[Today near me]]"
  - "[[This weekend]]"
stop_when_overdue: false
stop_after_runs: 0
---
# Try my city

Places I actually went to from the daily picks — counted when I say "I went" (`learn.py went`),
never from picks suggested. Meant as a monthly number: set `by:` to the end of the month in Goals
or the Daily tab and move it each month; the agent never books or buys anything toward it.
