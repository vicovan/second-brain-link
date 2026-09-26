---
description: Record what came back from an application — paste the email or say what happened
---

Record an employer's reply against the application it answers: $ARGUMENTS

1. If the user pasted an email, read it and classify it: `rejected` (a no, generic or not),
   `screen` (a recruiter call or questionnaire), `interview` (a hiring-manager or panel stage),
   `offer`, or `none` (an acknowledgement only — not a result). Quote the sentence that decided it.
2. Match it to a job key. List the open applications and pick by company and role:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py pending
   ```
   If two could match, ask which one — never guess a key.
3. Record it, with the employer's own words when they gave a reason:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py set-result --job-key <key> \
       --result <result> --feedback "<their reason, verbatim, if any>"
   ```
   Several at once: `--keys a,b,c`. "They all came back as generic rejections":
   `--all-open --result rejected --note generic` — confirm the count with the user first.
4. Re-render and show the effect:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/render_brain.py --quiet
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/job-scout/scripts/learn.py kpi
   ```
   With five or more results, add `learn.py calibrate` and say in one line what it suggests.
5. A screen or interview: offer interview prep from that application's `fit.md` (the gaps to be
   ready for) and `profile/stories.md` (the stories that fit the role).

Reading the user's mailbox is not part of this command; it works from what they paste.
