---
description: What's due — follow-ups, deadlines in the next two weeks, stale claims to re-verify
---

List what is due, then offer to draft the due follow-ups:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py due --days 14
```

For each follow-up, invoke `raise-outreach`. For each deadline, name the program, the days left and whether its year is confirmed.
