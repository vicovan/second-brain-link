# data/company/ — one folder per company

`data/company/<company>/<source>/…` — the folder name is the company. Each builds
a Company Brain at `vault/company/<company>-brain/`. Sources: linkedin_company,
google_workspace, slack, notion, confluence, jira, salesforce, hubspot, zendesk,
email, microsoft365, teams — plus the document stores `git_docs` and `google_drive`,
which are LINKED rather than copied: the source folder holds only a
`_SOURCE_LINK.json` (`python3 engine/scripts/doclink.py init …`, or Studio's
"Link folder…") pointing at the original docs, which are read-only and never
modified. Employee PII is stripped by default; HR/payroll/security/admin-log files
are quarantined; documents carrying secrets become metadata-only stubs.
