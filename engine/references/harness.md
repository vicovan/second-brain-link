# The Harness — goals, routines, reports, activity (reference)

The layer that lets agents work toward your goals while you're away. Everything is a plain note in
the brain under the `agentwork` layer (folder resolved per subject; `96-agents/` by default):

```
96-agents/
  Goals/<Title>.md      sbl-goal/1      an outcome with a finish line, counted from real results
  Routines/<Title>.md   sbl-routine/1   work that repeats: schedule + "only when" conditions
  Reports/<Title>.md    sbl-report/1    the handoff a run leaves: Done / Not done yet / Next step / Needs you
  Activity/<Title>.md   sbl-run/1       what exactly happened on one run, step by step
.plugins/harness/       state.json (last fired per routine, inbox marks) + _HARNESS_GENERATED.json
_REVIEW.json            sbl-review/1    suggestions about people/orgs, waiting for a human
```

Script: `scripts/harness.py` (stdlib, no network, no model). Studio calls it; so can you.

**Goal vs routine — does it have an end?** A goal has a finish line ("3 interviews by Nov 30"); a
routine repeats ("weekdays 07:00: scout new jobs"). A goal usually has routines working toward it,
and when it is met they switch off.

## Every run follows five steps

| Step | What | Where |
|---|---|---|
| 1. Check before starting | brain built? agent installed and set up? schedule readable? (Studio adds: AI signed in, Chrome connected). A failure is a `preflight-failed` run with a plain reason — no model is called | `harness.py preflight` |
| 2. Pick up where it left off | the last report's Not done / Next / Needs you is injected as a `=== LAST REPORT ===` block | `harness.py last-report --block` |
| 3. Work within limits | the agent's own folder, the tool ceiling, `max_per_day`, `max_minutes`, `only_when` | the caller + `due` |
| 4. Independent check | a Done item counts only with evidence (pass-gate); Studio's checker judges the rest | `harness.py verify` |
| 5. Clean handoff | the report; a run with nothing new is **quiet** (Activity only, no Inbox item) | `harness.py run-close` |

## Frontmatter — flat on purpose

Obsidian Properties and the engine's reader take `key: value` and `key:` + `- item` lists only.

**sbl-routine/1** — `schema, type: routine, tags, id, agent, skill, goal ("[[Goal]]"), schedule,
only_when (list), max_per_day, max_minutes, notify (news|always|never), enabled (true|false),
status (draft|validated|retired), created`. Body: plain English — what to do each run.

**sbl-goal/1** — `schema, type: goal, tags, id, agent, metric, metric_label, target, by (ISO date),
status (active|met|stopped|archived), routines (list of "[[Routine]]"), stop_when_overdue, created`.
`metric` names an outcome counter the agent declares in `studio.json` `outcomes` (a script that
prints one number — interviews, investor meetings, trips planned), or `manual` with a `progress`
field. **Progress counts real outcomes, never activity** (interviews, not applications sent).

**sbl-run/1** — `schema, type: run, tags, id, agent, routine, goal, trigger
(manual|schedule|chat|goal), status (queued|preflight-failed|running|awaiting|interrupted|capped|
failed|denied|done|skipped), convo, started, ended, report, verified`. Body: `## Steps` (one line
per step, appended as it happens), `## Questions and answers`, `## Wrote`.

**sbl-report/1** — `schema, type: report, tags (news|quiet), agent, routine, goal, run, status,
news (true|false), date, at, provisional`. Body: `## Done`, `## Not done yet`, `## Next step`,
`## Needs you`.

## Schedules

`manual` · `DAILY 07:00` · `WEEKDAYS 07:00` · `WEEKENDS 10:00` · `MON 08:00` · `MON,THU 08:00` ·
`MONTHLY 1 07:00` (day 1–28) · `EVERY 6h`. A missed slot (the machine was asleep) runs once on wake
and says so; it never runs twice to catch up.

## "Only when" conditions — deterministic, zero tokens

```
stamp_not_today: last-run.txt, snooze.txt     # the agent's own .plugins/<agent>/ stamps
cmd: ledger.py due --days 14 --count | gt 0   # the agent's OWN scripts only (| exit N, gt N, eq N, ge N)
stale_days: 30                                 # the brain wasn't rebuilt in 30 days
```

## The handoff a run ends with

An agent run ends its final answer with a fenced block the harness turns into the report:

````
```report
{"done": [{"text": "Applied to Acme — Staff Engineer", "evidence": "`45-jobs/applications/…/answers.md`"}],
 "not_done": ["Umbrella wants a cover letter I couldn't source"],
 "next": ["Follow up with Globex on Thursday"],
 "needs_you": [],
 "news": true}
```
````

`news: false` (nothing new) keeps the run quiet. Any open question, failure or Needs-you item
always makes it news.

## Templates (agents)

An agent ships templates in `<plugin>/harness/routines/*.md` and `harness/goals/*.md` and names the
folder in `studio.json` `"templates": "harness"`. `harness.py seed` copies them in **off**; once the
user edits one it is never overwritten (an update lands beside it as `<name>.new.md`).
`analyze.py` also seeds one routine per goal workspace from its "▶ Ask your AI to act" prompt.
