---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/travel-planner
id: routine-this-weekend
agent: travel-planner
skill: trip-pipeline
goal: "[[Try my city]]"
schedule: FRI 16:00
only_when:
  - "cmd: today.py check | exit 0"
max_per_day: 1
max_minutes: 20
notify: news
enabled: false
status: validated
---
# This weekend

The weekend edition of *Today near me*: on Friday afternoon, what to do on Saturday and Sunday
near where I am — a day trip from my saved-but-never-visited places, the weekend's events and
markets with when each page was seen, and a longer walk through a neighbourhood I have not been
to. Written to `Today near me weekend <date>` (the Map one click away). Nothing booked.
