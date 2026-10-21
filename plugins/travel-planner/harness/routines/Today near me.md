---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/travel-planner
id: routine-today-near-me
agent: travel-planner
skill: trip-pipeline
goal: "[[Try my city]]"
schedule: DAILY 08:10
only_when:
  - "cmd: today.py check | exit 0"
  - "stamp_not_today: today-run.txt"
max_per_day: 1
max_minutes: 20
notify: news
enabled: false
status: validated
---
# Today near me

Every morning: where I am today (the active trip's stop, else my home city, else what I said —
never the device), then five or six picks that are new to me — one coffee, one lunch or dinner,
one activity, one event, one new neighbourhood, a social option when my profile wants it — my own
saved and loved places first, then the web for what's on this week with when each page was seen;
on a trip, the itinerary's day first and the picks fill the gaps near its route — as a dated
shortlist, one section per slot (the Map one click away); nothing booked or bought; I say "I went
to #2" and it remembers.

A day with nothing new near me is a quiet run, not a failure.
