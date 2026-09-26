# Reminders — the daily nudge

Nothing here is required; `/fund-due` works by hand. This is for being asked once a day **when
something is actually due**.

`skills/raise-pipeline/scripts/daily_nudge.sh` is a **SessionStart hook**. On the first Claude Code
session of a day it runs `ledger.py due --count`; if follow-ups, deadlines within 14 days, or stale
dated claims exist, it adds a short note asking whether to show them. It is silent in every other case:
nothing due, already ran today, snoozed today, already asked today, or no state root yet.

Wire it up in your Claude Code settings:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/skills/raise-pipeline/scripts/daily_nudge.sh\"" }
        ]
      }
    ]
  }
}
```

Snooze for today: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py snooze`.
A completed plan run stamps `last-run.txt` (`ledger.py mark-run`).

In Second Brain Studio the same information is the **Due** block of `Fundraising Dashboard.md` and
the *What's due?* suggestion.
