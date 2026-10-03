---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/job-search
id: routine-daily-job-scout
agent: job-search
skill: job-pipeline
goal: "[[Get hired]]"
schedule: WEEKDAYS 07:00
only_when:
  - "stamp_not_today: last-run.txt, snooze.txt"
max_per_day: 1
max_minutes: 45
notify: news
enabled: false
status: validated
---
# Daily job scout

Run today's job pipeline: sweep the boards for new roles that fit my criteria, score them,
tailor a CV for the best ones and fill the applications — stopping at every approval my
`level:` setting asks for. Never apply twice to the same role, never invent a fact, and stop
on anything that needs a password, an ID or a CAPTCHA.

When nothing new fits, say so in one line — that is a quiet run, not a failure.
