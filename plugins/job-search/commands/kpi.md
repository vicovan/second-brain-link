---
description: The north-star number — interviews won, and the interview rate behind it
---

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py kpi
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py pending
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py target
```

Report the numbers, leading with interviews and the interview rate, then the archetype and
score-band tables, then the daily pace — valid applications today against `daily-target:` and
the last seven days. If anything has been pending more than ~14 days, say so once — it is probably
a silent rejection worth recording as `--result none` so the statistics stay honest. If five or
more results exist, also run `learn.py calibrate` and report whether the score predicts replies.
