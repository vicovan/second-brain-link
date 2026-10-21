---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/travel-planner
id: routine-weekly-trip-check
agent: travel-planner
skill: trip-pipeline
goal: "[[Plan my next trip]]"
schedule: MON 09:30
only_when:
  - "cmd: itinerary.py count upcoming | gt 0"
max_per_day: 1
max_minutes: 20
notify: news
enabled: false
status: validated
---
# Weekly trip check

For every upcoming trip: which flight and stay quotes have gone stale (older than a week), what
still needs me (a self-transfer leg, "I booked it"), what the week's picks taught about my taste
(`kpi.py` → `optimize.py` on the picks funnel: the kinds and sources that I actually went to),
written to `reports/Trip check <date>.md`. Books nothing.
