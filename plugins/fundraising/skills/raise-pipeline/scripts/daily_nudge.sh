#!/bin/bash
# daily_nudge.sh - optional SessionStart hook for the fundraising plugin.
#
# Once a day, and ONLY when something is due (a follow-up, a deadline within 14 days,
# a dated claim to re-verify), prints a one-line offer as SessionStart
# additionalContext. Silent and exit 0 in every other case, so it can never get in the
# way of a session. Opt-in — see docs/scheduling.md.
#   "command": "bash \"${CLAUDE_PLUGIN_ROOT}/skills/raise-pipeline/scripts/daily_nudge.sh\""

set -u
HERE=$(cd "$(dirname "$0")" 2>/dev/null && pwd -P) || exit 0
# Claude packaging: the shared library lives in raise-research/scripts. Codex packaging
# flattens every script into one folder, so try the sibling first.
LIB="$HERE"
[ -f "$LIB/ledger.py" ] || LIB="$HERE/../../raise-research/scripts"
[ -f "$LIB/ledger.py" ] || exit 0

STATE=$(python3 "$LIB/paths.py" 2>/dev/null | sed -n 's/^state root   : //p')
[ -n "$STATE" ] && [ -d "$STATE" ] || exit 0      # nothing set up yet: say nothing

TODAY=$(date +%F)
stamped() { [ -f "$STATE/$1" ] && [ "$(cat "$STATE/$1" 2>/dev/null)" = "$TODAY" ]; }
stamped last-run.txt && exit 0
stamped snooze.txt   && exit 0
stamped nudged.txt   && exit 0

N=$(python3 "$LIB/ledger.py" due --days 14 --count 2>/dev/null || echo 0)
[ "${N:-0}" -gt 0 ] 2>/dev/null || exit 0
echo "$TODAY" > "$STATE/nudged.txt" 2>/dev/null

cat <<JSON
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"FUNDRAISING: $N item(s) are due in the next 14 days (follow-ups, program deadlines, or dated claims to re-verify). On the user's first message, use AskUserQuestion to offer: 'Show what is due' or 'Not today'. If they decline, run: python3 \${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py snooze — then do what they actually asked. If they accept, invoke the raise-pipeline skill in 'what is due' mode. This is an offer, not a task: if their message is about something else and they do not engage, drop it silently. Never mention this note itself."}}
JSON
exit 0
