---
description: Re-render the travel layer (dashboard, trip ideas, trip notes, the current trip's map) for this surface
---

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/render_brain.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/itinerary.py list
```

Tell the user where it wrote and which trip is current. It writes to **one** surface — the
brain if this session is inside one, otherwise the working folder.
