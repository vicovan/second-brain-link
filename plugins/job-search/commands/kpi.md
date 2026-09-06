---
description: The north-star number — applications actually submitted
---

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py kpi
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py pending
```

Report the numbers, leading with successful applications. If anything has been pending more than
~14 days, say so once — it is probably a silent rejection worth recording as `--result none` so the
statistics stay honest.
