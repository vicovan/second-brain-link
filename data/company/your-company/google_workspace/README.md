# Google Workspace (admin) export

Drop your unzipped **Workspace admin / org Takeout** export here (or pass a `.zip`).
Contents are git-ignored. Builds a company-rooted brain: directory users →
employees, shared calendars → events, shared drives → projects.

Privacy: employee emails/phones are stripped by default; HR/payroll/security/
admin-log files are quarantined (never imported). Use `--full` only on data you
are authorized to retain in full.
