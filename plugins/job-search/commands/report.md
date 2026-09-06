---
description: Re-render the job layer (dashboard, application notes, shortlists) for this surface
---

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/render_brain.py
```

Then tell the user the path it wrote to and the submitted/tracked counts. Remember it writes to
**one** surface — the brain if this session is inside one, otherwise the working folder.
