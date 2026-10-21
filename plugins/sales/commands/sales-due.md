---
description: What's due — sequence steps today, replies waiting, approvals waiting
---

List what is due, then offer to send it:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/sequence.py due
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/render_sales.py
```

Then read `48-sales/Sales Dashboard.md` (and today's `reports/Sell today <date>.md`) → *Needs you* and name each reply or approval that waits for the seller. Offer `sales-send` for the due steps and `sales-reply` for the replies.
