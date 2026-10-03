---
name: docs-connector
description: Connect a company's remote document store to its Second Brain — clone a Git docs repository by URL, or pull a Google Drive folder through the Drive API with the user's own OAuth client — into a local mirror, link it, keep it in sync and report status. Use for "connect our Google Drive", "pull the docs repo", "sync the company docs".
---

# docs-connector (OpenAI)

> The **OpenAI/Codex packaging** of the Second Brain Link `docs-connector` plugin. The script is
> byte-identical to the Claude packaging; workflows are in `references/`, code in `scripts/`.

Read `references/docs-connect.md` in full before acting. The script is `scripts/connector.py`.
It fetches into a mirror outside the data folder and writes the link file; the
`second-brain-link` engine reads that mirror read-only on the next reseed.
