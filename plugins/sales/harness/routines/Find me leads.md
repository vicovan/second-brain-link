---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/sales
id: routine-find-me-leads
agent: sales
skill: sales-scout
goal: "[[Book sales meetings]]"
schedule: WEEKDAYS 07:30
only_when:
  - "cmd: sales_profile.py check | exit 0"
max_per_day: 1
max_minutes: 30
notify: news
enabled: false
status: validated
---
# Find me leads

Run today's lead sweep — my brain first, then every market's sources and the companies' own
sites — with the coverage gate, and leave the shortlist in the lead report. Finding leads sends
nothing.
