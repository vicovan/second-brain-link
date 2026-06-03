# data/company/your-company/ — a template company (rename me)

Example company folder showing the layout. **Rename it to your actual company** —
e.g. `data/company/acme/` — then drop each export into the matching source
subfolder. The folder name becomes the Company Brain at
`vault/company/<company>-brain/`.

Sources: `linkedin_company/`, `google_workspace/`, `slack/` (use the one(s) you
have — one is enough). Everything you add here is git-ignored; only these
placeholder READMEs are tracked. While the folder holds only READMEs the builder
skips it, so it's safe to leave in place until you add data.

Employee emails/phones are stripped by default and HR/payroll/security/admin-log
files are quarantined; `--full` keeps everything for data you're authorized to retain.
