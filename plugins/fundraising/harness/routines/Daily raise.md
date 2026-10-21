---
schema: sbl-routine/1
type: routine
tags:
  - routine
  - agent/fundraising
id: routine-daily-raise
agent: fundraising
skill: raise-pipeline
goal: "[[Raise my round]]"
schedule: WEEKDAYS 08:00
only_when:
  - "stamp_not_today: last-run.txt, snooze.txt"
max_per_day: 1
max_minutes: 45
notify: news
enabled: false
status: validated
---
# Daily raise

Run today's raise: find new programs and investors (my brain's ties and correlations first, then the
proven sources and today's explore slice), screen them against my filter chain, verify the survivors
on their own sites, open today's note with what is new and what is due, apply to the programs and
draft the investor angles my autonomy level allows, draft the follow-ups that are due, find the
public threads worth a comment — then render and report. Drafts are never sent and comments never
posted; a target is contacted only when I say I sent it.

When nothing new fits and nothing is due, say so in one line — that is a quiet run, not a failure.
