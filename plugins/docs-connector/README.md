# docs-connector — pull a remote document store into a brain

The Second Brain Link engine seeds a Company Brain from a company's documents through two
sources, `git_docs` (a docs repository) and `google_drive` (a Drive folder). The engine only
ever **reads a local folder** — zero network calls, read-only, every file tiered by a local
sensitivity scanner (files with credentials or secrets become metadata-only notes).

This plugin is the **networked half**, kept out of the engine on purpose:

| Store | How it is fetched | Credentials |
|---|---|---|
| Git repository | clone, then fast-forward on every sync | your own SSH key / credential helper — a URL with an embedded password is refused |
| Google Drive | Drive API v3, **read-only** scope; native Docs/Sheets/Slides exported to .docx/.xlsx/.pptx; incremental (unchanged files are not downloaded again) | your **own** OAuth client ("Desktop app" type, from your Google Cloud project); the refresh token is stored with mode 0600 |

Files land in a **mirror outside the data folder** (`~/.second-brain/sources/<entity>/<source>/mirror`),
which this plugin owns. It then writes `data/company/<entity>/<source>/_SOURCE_LINK.json`
(mode `connector`) pointing at the mirror, plus — for Drive — the metadata sidecar
`_SOURCE_MANIFEST.json` (ids, mime types, dates, sizes, owners' display names; never e-mail
addresses, never tokens). Reseed the brain and the engine takes over.

```bash
S=<plugin>/skills/docs-connect/scripts   # the Codex packaging: <skill>/scripts
python3 $S/connector.py add-git   --entity acme --url <remote> [--branch main]
python3 $S/connector.py add-drive --entity acme --folder <folder-id> --client-secret ~/client_secret.json
python3 $S/connector.py sync      [--entity acme]
python3 $S/connector.py status
```

`--data` defaults to `$SBL_DATA_DIR`, else `~/Documents/SecondBrainLink/data` (Second Brain
Studio's default workspace). Second Brain Studio shows a **Sync now** button on any source
linked by this plugin.

## Where your data lives

- the mirror: `~/.second-brain/sources/…` (override with `--mirror` or `$SBL_CONNECTOR_HOME`)
- the Drive token: `~/.second-brain/connectors/google_drive/token.json` (mode 0600)
- nothing in this repository, nothing uploaded anywhere
