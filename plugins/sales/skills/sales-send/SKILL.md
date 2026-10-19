---
name: sales-send
description: Send the steps that are due — email from the seller's own mailbox, LinkedIn, X and WhatsApp Web messages in the seller's own signed-in Chrome, and the company's own contact forms — each written per contact from the seller's voice and the account's evidence, checked by the claims linter, and passed through send_guard.py (level, do-not-contact, stop-on-reply, guessed addresses, caps, working hours, social spacing), batched into one approval card when a gate applies, and logged. Use for "send what's due", "send the first touches", "do today's steps", or the daily sales routine.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion, Agent, mcp__claude-in-chrome__*
---

# Sales Send

## Memory — every run
Follow `references/memory-protocol.md`; tool `${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/memory.py`,
scope `sales`, tags `send,voice,channels`. A denied batch's reason is an outcome — save it.

**`send_guard.py` decides. You never send around it.** It is the same code for every channel:

| Verdict | Exit | Do |
|---|---|---|
| `ALLOW` | 0 | send (email: `mail.py send` sends it; social/form: do it, read it back, `send_guard.py sent`) |
| `GATE` | 3 | collect into ONE approval batch for the seller; re-check with the approved `--batch` |
| `ASSIST` | 4 | social automation is off — prepare it in Chrome; the seller presses Send |
| `BLOCK` | 1 | never sent; report it with its rule. Do not reword a message to slip past a rule |

## 1. What is due

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/sequence.py due --json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/sales_profile.py show sending
```
Batch id for this run: `B=run-$(date +%Y%m%d-%H%M)`.

## 2. Write each message (`references/email-playbook.md`, `references/social-playbook.md`)

Per row: read the account (`ledger.py get`), the contact's brain note, the step's `brief`, the
voice profile and the brain's voice layer. Write it to `$SCRATCH/<key>-<contact>-<step>.md`:
- the first line names *their* reason now (the signal, with its date) or the shared history;
- one proof point, only from `offer.md` / materials;
- one question; nothing to click in a first email;
- the opt-out line (`sending.md` `opt_out`) at the end of every email.

Check it: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/lint_claims.py FILE --channel email --first-touch`.
Red → fix by removing the claim, never by inventing the missing fact.

## 3. Guard, gate, send — email

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/send_guard.py check --channel email \
    --account <KEY> --contact "<Name>" --to <address> --body-file FILE --kind first --batch $B --step <n>
```
Collect every GATE (and every BLOCK, so the seller sees what was held back) into the batch:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/batch.py add --batch $B --account <KEY> --contact "<Name>" \
    --channel email --to <address> --subject "<subject>" --body-file FILE --hook-source "<note or URL>" \
    --verdict GATE|BLOCK [--rule "<the guard's rule>"] --step <n>
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/batch.py card --batch $B
```
`batch.py card` writes the batch note (every message in full) and prints an ```approval fence.
**Put that fence in your reply, then ask ONE `AskUserQuestion`** — Studio draws the approval card from
it: the consequence line with the cap counter, the batch note to open, one row per recipient with
the hook's source, and the blocked rows. Options: *Approve all* · *Approve, skip some* (Other: names)
· *Edit first* · *Deny — say why*. Approve → `ledger.py approve --batch $B`; deny →
`ledger.py deny --batch $B --reason "<their words>"`.
Then send each allowed message:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/mail.py send --account <KEY> --contact "<Name>" \
    --to <address> --subject "<subject>" --body-file FILE --kind first --batch $B --step <n>
```
`mail.py` re-runs the guard itself and refuses without ALLOW. A failure is logged; never retry
more than once.

**The very first real send** of this plugin is a rehearsal: everything up to the card, and the
seller approves it explicitly, whatever the level says.

## 4. Social steps — LinkedIn, X, WhatsApp Web (`references/social-playbook.md`)

Browser not connected → `references/browser-setup.md`. Guard first (`--channel linkedin_invite|
linkedin_dm|x_dm|whatsapp`, `--kind connect|dm`).
- `ASSIST` (social automation off): open the profile, fill the note/message box, stop; the seller
  presses Send and says so → `send_guard.py sent …`.
- `ALLOW` (`social_auto: on`): click Send yourself, then **read the conversation back** and only
  then `send_guard.py sent --channel … --account … --contact … --step n --batch $B --evidence "<what the page shows>"`.
- Any captcha, "unusual activity", restriction or weekly-limit banner → stop every social step,
  set `social_paused_until` in `sending.md` to two days from today, `ledger.py log platform_warning`,
  and tell the seller. Never solve a captcha.
- One tab, one action at a time; the guard enforces the gap — wait it out, do not batch clicks.

## 5. Contact forms (`references/form-playbook.md`)

`detect_form.py URL` first. Guard with `--channel form --kind form`. Fill every field from the
account and offer profile, the message within the field's limit; verify each field in the DOM.
`ALLOW` → submit, keep the confirmation text → `send_guard.py sent --channel form … --evidence "<confirmation>"`.
Captcha, login or payment → hand-off with the URL.

## 6. Finish

`render_sales.py`, then report: sent per channel, gated (waiting), blocked with rules, assisted
steps waiting for the seller, the caps used today.
