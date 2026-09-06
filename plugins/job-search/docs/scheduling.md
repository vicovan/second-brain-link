# Running the job hunt on a schedule

Nothing here is required — the plugin works fine run by hand with `/jobs`. This is for
having it ask you once a day.

## How the daily prompt works

`skills/job-scout/scripts/daily_nudge.sh` is a **SessionStart hook**. On the first Claude
Code session of a day it prints a short note asking whether to run the scan. It is silent
in every other case: already ran today, snoozed today, already asked today, or no state
root yet.

It resolves the state root by calling `paths.py`, so it needs no configuration of its own.

Wire it up in your Claude Code settings:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/daily_nudge.sh\"" }
        ]
      }
    ]
  }
}
```

To stop being asked for a day: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/scout_state.py snooze`

To re-arm today's prompt after a run: delete `last-run.txt` from the state root
(`python3 .../paths.py` prints where that is).

## A real schedule

The hook only fires when you open a session. If you want the machine to nudge you at a
fixed time, add an OS-level reminder that opens one.

**macOS — launchd.** Save as `~/Library/LaunchAgents/com.secondbrainlink.jobsearch.plist`,
then `launchctl load -w` it. Add more `StartCalendarInterval` entries to fire more than once
a day.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.secondbrainlink.jobsearch</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/osascript</string>
    <string>-e</string>
    <string>display notification "Run today's job scan?" with title "Job search"</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>20</integer></dict>
  </array>
  <key>StandardErrorPath</key><string>/tmp/jobsearch-launchagent.err</string>
</dict>
</plist>
```

**Linux / cron.** `crontab -e`:

```cron
20 8 * * 1-5  notify-send "Job search" "Run today's job scan?"
```

**Windows.** Task Scheduler → daily trigger → an action that shows a toast or opens your
terminal.

Note that the scout's search window shrinks to whatever is actually new since the last run
(`scout_state.py window`, clamped to 1–14 days), so running more often costs less each time
rather than re-reading the same market.
