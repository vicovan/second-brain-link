---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/fundraising
id: routine-whats-due-in-my-raise
agent: fundraising
skill: raise-pipeline
goal: "[[Raise my round]]"
schedule: WEEKDAYS 08:00
only_when:
  - "stamp_not_today: last-run.txt, snooze.txt"
  - "cmd: ledger.py due --days 14 --count | gt 0"
max_per_day: 1
max_minutes: 30
notify: news
enabled: false
status: validated
---
# What's due in my raise

Work through what is due in the next two weeks — follow-ups, program deadlines and claims that
have gone stale — and draft what each needs. Draft only: nothing is ever sent, and a target is
marked contacted only when I say I sent it.

Runs only on days when something is actually due, so a quiet week costs nothing.
