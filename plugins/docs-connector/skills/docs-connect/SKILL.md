---
name: docs-connect
description: Connect a company's remote document store to its Second Brain — clone a Git docs repository by URL, or pull a Google Drive folder through the Drive API with the user's own OAuth client — into a local mirror, link it, keep it in sync, and report status. Use for "connect our Google Drive", "pull the docs repo from GitHub", "sync the company docs", "seed the company brain from Drive", or when a linked document store needs refreshing.
allowed-tools: Read, Bash, AskUserQuestion
---

# docs-connect — remote document stores → a Company Brain

Script: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/docs-connect/scripts/connector.py` (stdlib only).

## What it does — and does not do
- Fetches into a **mirror outside the data folder** and writes the link file
  `data/company/<entity>/<git_docs|google_drive>/_SOURCE_LINK.json` (mode `connector`).
- Never writes into the brain, never reads document contents itself, never uploads anything.
- The engine (`second-brain-link` skill) then reads the mirror read-only on reseed; its
  local scanner keeps files with credentials/secrets out as metadata-only notes.

## Steps
1. **Which company and which store?** Get the entity slug (the folder under
   `data/company/` — `ls` it) and either the repository URL or the Drive folder.
   - Git: SSH (`git@host:org/repo`) or HTTPS without credentials. If the user pastes a URL
     with a password or token in it, refuse and tell them to use an SSH key or credential
     helper — the script refuses it too.
   - Drive: a folder id (from the folder's URL, after `/folders/`) or `root` for My Drive,
     `--shared-drive <id>` for a shared drive, and the path to the user's own OAuth
     `client_secret.json` (Google Cloud Console → APIs & Services → Credentials → OAuth
     client ID → **Desktop app**, with the Drive API enabled). Creating it is free; it is the
     user's own project. Never ask for or handle the client secret's contents — only its path.
2. **Add + first sync:**
   `connector.py add-git --entity <slug> --url <url> [--branch <b>]`
   `connector.py add-drive --entity <slug> --folder <id> --client-secret <path>` — the first
   Drive run opens the browser for consent (read-only scope); the token is saved mode 0600.
3. **Later syncs:** `connector.py sync [--entity <slug>] [--source git_docs|google_drive]`.
4. **Status:** `connector.py status`.
5. **Reseed** the brain so the engine picks the mirror up (Studio → Reseed, or
   `build_vault.py <data> -o <vault> --refresh`). Then `docscan.py audit <brain>` must print 0.

## Rules
- `--data` defaults to `$SBL_DATA_DIR` or `~/Documents/SecondBrainLink/data`; pass it when the
  user's workspace is elsewhere.
- Never delete a mirror or a link file without the user's explicit yes.
- A sync failure leaves the previous mirror as it was and records `last_result` in the link.
