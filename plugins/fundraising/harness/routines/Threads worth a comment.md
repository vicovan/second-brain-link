---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/fundraising
id: routine-threads-worth-a-comment
agent: fundraising
skill: raise-engage
goal: "[[Raise my round]]"
schedule: WEEKDAYS 09:00
only_when:
  - "stamp_not_today: engage-run.txt, snooze.txt"
max_per_day: 1
max_minutes: 20
notify: news
enabled: false
status: validated
---
# Threads worth a comment

Find today's public threads — LinkedIn posts, X threads, Hacker News, Reddit — where the people I
want to reach are already discussing my problem space, and draft one useful comment for each of
the best few (at most `max_per_run` in my `engage.md`). Answer what the thread is actually asking;
never pitch. Draft only: nothing is posted, liked or messaged for me, no social network is logged
in to, and a thread is marked posted only when I say I posted it.

Cost: one search sweep plus a handful of page reads a day. When nothing is worth joining, say so in
one line — that is a quiet run, not a failure.
