---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/__ID__
id: routine-daily-__ID__
agent: __ID__
skill: __ID__-pipeline
goal: "[[__GOAL__]]"
schedule: WEEKDAYS 08:30
only_when:
  - "stamp_not_today: last-run.txt, snooze.txt"
max_per_day: 1
max_minutes: 30
notify: news
enabled: false
status: validated
---
# Daily __WHAT__

Run today's __WHAT__: discover what is new (my brain first, then the proven sources and today's
explore slice), screen and score it against my profile, put the ranked list in the dated note, act
within my autonomy level — stopping at every gate `level:` asks for — then render and report.

When nothing new fits, say so in one line — that is a quiet run, not a failure.
