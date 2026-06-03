# data/company/ — one folder per company

`data/company/<company>/<source>/…` — the folder name is the company. Each builds
a Company Brain at `vault/company/<company>-brain/`. Sources: linkedin_company,
google_workspace, slack. Employee PII is stripped by default; HR/payroll/security/
admin-log files are quarantined.
