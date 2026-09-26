---
name: raise-outreach
description: Draft investor correspondence — cold emails, follow-ups, warm-intro requests to a connection, pitch-form messages and LinkedIn or X notes — one per target, each with a hook from a verified claim, linted against the founder's facts, saved as a vault note and, when a Gmail draft tool is available, as a Gmail draft. Never sends anything. Use for "draft this week's emails", "write to <fund>", "ask <connection> for an intro", "draft the follow-ups", or when follow-ups come due.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Skill
---

# Raise Outreach

Writes the words; the founder presses send. That boundary is the whole design: **no send tool is
used, ever**, and a record only becomes `contacted` when the founder says it went out.

Read `references/email-playbook.md` before the first draft of a run.

## For each target

1. **Pick the channel** from the record: `cold_path` ✅ email → email · pitch form → a short
   form message (the form itself is `raise-apply`) · warm-only → an **intro request to a
   connection** (below) · X/LinkedIn-only → a note the founder sends by hand.
2. **The hook** — one sentence on *why this fund*, taken from a ✅ claim on the target (their
   thesis page, a portfolio company, a partner's published piece), with the claim's URL kept in the
   note. A hook resting on a 📋 or ⚠ claim is refused by the linter: verify it first or write a
   plainer email.
3. **The body** — five lines: who (one line from `founder.md`), what (the one-liner from
   `company.md`), proof (one or two checkable facts — never anything on the do-not-claim list), the
   hook, one clear ask. Links: deck URL from `answers.md`, site. No attachment claims you cannot keep.
4. **Write the note** at `46-fundraising/outreach/<YYYY-MM-DD>/<Name> — email <YYYY-MM-DD>.md`
   (the filename *is* the title, so links resolve):

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

   Body below the frontmatter, then a `mailto:` link line the founder can click.
5. **Lint it** — red stops this draft (fix and re-lint, or skip with a reason):

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/lint_claims.py "<note path>" --out "<folder>/gates.json"
   ```
6. **Gmail draft** — only if a Gmail tool whose purpose is *creating a draft* is available in this
   session. Create the draft (to, subject, body), write its id into `gmail_draft_id`. If only a
   send-capable tool exists, **do not use it**; say in one line that drafts are in the vault only.
   Never BCC, never one draft to several investors.
7. **Record it**:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py log-draft <key> --path "<note path>" --channel email [--gmail-id <id>]
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/render_brain.py --quiet
   ```

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
