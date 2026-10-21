---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/sales
id: routine-work-my-replies
agent: sales
skill: sales-reply
goal: "[[Start trials]]"
schedule: WEEKDAYS 11:00
only_when:
  - "cmd: ledger.py count sent --days 30 | gt 0"
max_per_day: 1
max_minutes: 20
notify: news
enabled: false
status: validated
---
# Work my replies

Read new replies from the people I've written to, stop their sequences, answer the routine ones,
propose times and book what's agreed. Pricing, legal and objections wait for me with a drafted answer.
