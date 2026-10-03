---
description: Sync every remote document store linked by the docs-connector (Git repositories and Google Drive folders), then say what changed
---

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/docs-connect/scripts/connector.py sync $ARGUMENTS
python3 ${CLAUDE_PLUGIN_ROOT}/skills/docs-connect/scripts/connector.py status
```

Report each store in one line (pulled / downloaded / unchanged / removed, or the error), then
remind the user to reseed the brain so the engine picks the changes up.
