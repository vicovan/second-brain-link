---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/sales
id: routine-work-my-sales-day
agent: sales
skill: sales-pipeline
goal: "[[Book sales meetings]]"
schedule: WEEKDAYS 09:00
only_when:
  - "cmd: sequence.py due --count | gt 0"
max_per_day: 1
max_minutes: 30
notify: news
enabled: false
status: validated
---
# Work my sales day

Send the sequence steps that are due today, within my caps and my autonomy level — anything
gated waits in the Inbox for my OK. Runs only on days when a step is actually due.
