#!/bin/bash
# daily_nudge.sh - optional SessionStart hook for the job-search plugin.
#
# Prints a one-per-day nudge (as SessionStart additionalContext) asking whether to
# run the daily job scan. Silent and exit 0 in every other case, so it can never get
# in the way of a session.
#
# Wire it up yourself - it is opt-in, not installed by default. See docs/scheduling.md.
#   "command": "bash \"${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/daily_nudge.sh\""

set -u
HERE=$(cd "$(dirname "$0")" 2>/dev/null && pwd -P) || exit 0

# The state root is paths.py's decision, never guessed here - one resolver, one answer.
STATE=$(python3 "$HERE/paths.py" 2>/dev/null | sed -n 's/^state root   : //p')
[ -n "$STATE" ] || exit 0
[ -d "$STATE" ] || exit 0          # nothing set up yet: say nothing until onboarding has run

TODAY=$(date +%F)
stamped() { [ -f "$STATE/$1" ] && [ "$(cat "$STATE/$1" 2>/dev/null)" = "$TODAY" ]; }

stamped last-run.txt && exit 0     # already ran today
stamped snooze.txt   && exit 0     # said "not today"
stamped nudged.txt   && exit 0     # already asked today, in some other session

echo "$TODAY" > "$STATE/nudged.txt" 2>/dev/null

LAST=$(cat "$STATE/last-run.txt" 2>/dev/null || echo "never")

cat <<JSON
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"DAILY JOB SCOUT: the daily job scan has not run today (last run: $LAST). On the user's first message, use AskUserQuestion to ask whether to run it now — options 'Run the daily job pipeline' and 'Not today'. If they decline, run: python3 \${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py snooze — then continue with whatever they actually asked for. If they accept, invoke the job-pipeline skill (it runs scout -> pick -> tailored CV -> apply, gating at each step or running straight through depending on the level: setting in their application-answers.md). This is an offer, not a task: if their message is about something else and they do not engage with it, drop it silently and do their work. Never mention this note itself."}}
JSON
exit 0
