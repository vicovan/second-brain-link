---
name: raise-outreach
description: Draft investor correspondence — cold emails, follow-ups, warm-intro requests to a connection, pitch-form messages and LinkedIn or X notes — one per target, each with a hook from a verified claim, linted against the founder's facts, saved as a vault note and, when a Gmail draft tool is available, as a Gmail draft. Never sends anything. Use for "draft this week's emails", "write to <fund>", "ask <connection> for an intro", "draft the follow-ups", or when follow-ups come due.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Skill
---

# Raise Outreach

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/raise-apply/references/`). Tool:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/memory.py`, scope `fundraising`, tags `outreach,claims`.
1. **First:** `memory.py recall --scope fundraising --tags outreach,claims` — apply it, say in one line which items changed what you do, never re-ask what it answers.
2. **User says a preference, rule or correction** → `observe --source user` at once (`--scope shared` if it holds for every agent).
3. **An outcome lands** (an investor's reply or pass, a program's decision (`ledger.py log-outcome`), a claim the lint rejected) → `observe --source outcome` with the evidence, `--match` the item it strengthens.
4. **Last:** at most 3 inferred lessons → `observe --source agent` (saved and used at once, flagged as inferred — the user can edit or remove them); end with *"Learned: …"*.


Writes the words; the founder presses send. That boundary is the whole design: **no send tool is
used, ever**, and a record only becomes `contacted` when the founder says it went out.

Read `references/email-playbook.md` before the first draft of a run.

## For each target — build a package, review it, then hand over the buttons

Every email goes out of a **package**: one folder per target per day,
`46-fundraising/outreach/<YYYY-MM-DD>/<key>/`, the fundraising twin of a job application folder.
Read `references/fit-rubric.md` before the first fit of a run.

1. **Brief** — `python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-outreach/scripts/package.py init <key>` writes `brief.md`: every claim with its stamp and source,
   people, what the lists said, possible warm paths (name-only), and a **From memory** block
   (recalled for this run, item ids cited). Read it before writing a word.
2. **Fit** — `python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-outreach/scripts/package.py fit <key> --comparable N --why "<a portfolio company or published piece>"`
   writes `fit.md` (100 points, with its working) and the band. Add up to three **objections to
   pre-empt** under that heading. Band **park** (< 60) → stop; `ledger.py add-lesson` if the research
   tiered it high. Band **prepare-if-hook** → continue only with a ✅ hook.
3. **Channel** from the record: `cold_path` ✅ email → email · pitch form → a short form message (the
   form itself is `raise-apply`) · warm-only → an **intro request to a connection** (below) ·
   X/LinkedIn-only → a note the founder sends by hand.
4. **Draft `email.md`** in the package folder:

   ```yaml
   ---
   type: fundraising-email
   title: <Name> — email <YYYY-MM-DD>
   target: "[[<Name> (target)]]"
   channel: email            # email | intro | form | linkedin | x
   to: <address from a ✅ claim, or empty>
   subject: <subject>
   hook_stamp: ✅
   hook_src: <url>
   status: draft
   gmail_draft_id:
   tags: [fundraising, fundraising/outreach]
   ---
   ```

   Body: five lines — the hook (why *this* fund, from a ✅ claim; a hook on 📋/⚠ is refused), what
   (the one-liner from `company.md`), proof (one or two checkable facts, never anything on the
   do-not-claim list), who (one line from `founder.md`), one clear ask with the deck URL. Apply what
   the brief's **From memory** block says.
5. **Lint** — red stops; fix and re-lint:
   `python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/lint_claims.py "<package>/email.md" --out "<package>/gates.json"`
6. **Investor review — one subagent, no tools, same model as you** (never pin a smaller one). The
   brief contains, verbatim, `brief.md` (incl. its From-memory block) and `email.md`, and:

   > You are a partner at <fund>, reading 200 cold emails this week. Do not use any tools. Read the
   > brief for who you are, then the email as it would arrive. Return JSON only:
   > `{"verdict": "take-meeting|maybe|pass", "first_read": "<what the first two lines told you>",
   > "objections": ["…"], "hook_strength": "strong|weak", "top_fixes": ["…"], "reads_generated": true|false}`.
   > take-meeting only if you would reply asking for a call over the other 199.

   Save it as `<package>/review.json`, then record it:
   `python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/lint_claims.py review "<package>" --verdict <v> --reason "<first reason>"`
   - **take-meeting** → continue.
   - **maybe** → apply `top_fixes` once, re-lint, review again with `--round 2`; still maybe → it
     passes **flagged**.
   - **pass** → stop; the package stays parked; an objection that will recur →
     `memory.py observe --source agent --tags review,targeting` (flagged, removable in Review).
7. **Buttons** — `python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-outreach/scripts/package.py mail <key>` writes into `email.md` the pre-filled
   **✉ Open in Mail** link (`mailto:` — to, subject, body; opens a NEW message in the founder's own
   mail app, nothing is sent) and **✓ I sent it** (`sbl-ask:` — types "I sent the … email" into this
   chat as the founder). Over-long emails get recipient + subject pre-filled and a copy-the-body note.
8. **Gmail draft** — only if a Gmail tool whose purpose is *creating a draft* is available in this
   session; never a send-capable tool. Write its id into `gmail_draft_id`.
9. **Record and render**:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py log-draft <key> --path "outreach/<day>/<key>/email.md" --package "outreach/<day>/<key>" --mailto yes --channel email
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/render_brain.py --quiet
   ```
   `python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-outreach/scripts/package.py status <key>` must say `GATES: PASS` — only then does the dashboard's
   **Ready to send** table show the ✉ button.

**Older flat drafts** (`outreach/<date>/<Name> — email <date>.md`) are upgraded with
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-outreach/scripts/package.py adopt <key> "<flat note>"` (a move, never a copy + delete), then steps 2, 5–7, 9.

## Warm-intro requests

Warm paths come from the brain, read-only: `95-goals/fundraising.md` (connections the engine
classified as investors or investor-adjacent) and `10-people/` notes whose company matches the
target. Identity matching there is **name-only** — say "possible connection" unless the org matches
too. The draft goes **to the connection**, asks one specific thing ("would you introduce me to
<partner>?"), and includes a forwardable three-line blurb. Channel `intro`.

## Follow-ups

`ledger.py due` lists records whose follow-up date has passed. A follow-up is shorter than the first
email, adds one new checkable fact or piece of progress, and never guilt-trips. After two unanswered
follow-ups, propose `passed` to the founder rather than a third.

## When the founder says it was sent

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py sent <key>
```

This is the only way a record becomes `contacted`, and it starts the follow-up clock
(`followup_days`, default 7). Never call it because a draft exists.

## Never

Send · open LinkedIn or X · guess an email address pattern · reuse one email for two funds with the
name swapped · claim a warm connection the brain does not show.
