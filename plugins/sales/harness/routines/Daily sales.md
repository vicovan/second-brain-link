---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/sales
id: routine-daily-sales
agent: sales
skill: sales-pipeline
goal: "[[Start trials]]"
schedule: WEEKDAYS 07:30
only_when:
  - "cmd: sales_profile.py check | exit 0"
max_per_day: 1
max_minutes: 45
notify: news
enabled: false
status: validated
---
# Daily sales

Run today's sales: work the replies first, send the sequence steps that are due within my caps and
my autonomy level (anything gated waits in the Inbox as one batch), then find today's leads — my
brain's warm ties and lost deals first, then every market's sources with the coverage gate and a
20 % explore slice — give each shortlisted account a strategy (why now · the angle · which offer to
get them to try, use, buy or partner on) and a reach-out mix, start the sequences that fit, render
and report. The first real send is always gated; a guessed address is never sent.

When nothing is due and nothing clears the floor, say so in one line — a quiet run, not a failure.
