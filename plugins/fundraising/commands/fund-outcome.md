---
description: Record what came back from an investor or a program — paste the email or say what happened
---

Record a reply against the target it answers: $ARGUMENTS

Follow "Recording an outcome" in the `raise-pipeline` skill: classify (quote the deciding sentence), match the record (ask if two could match), then

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py log-outcome <key> <result> --note "<their words>"
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/render_brain.py --quiet
```

Reading the mailbox is not part of this command; it works from what is pasted.
