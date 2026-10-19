# Safety — what the Sales Agent will and will not do

## Enforced in code (`skills/sales-scout/scripts/send_guard.py`), not in a prompt

- `level: draft` sends nothing. `supervised` gates every send. `autonomous` sends within the caps;
  first touches stay gated for the first batches, EU first touches stay gated while `eu_gate: on`,
  and non-routine replies (pricing, legal, objections) are always gated.
- The first real send and the first real social action always need the owner's OK.
- Never sent: anyone on the do-not-contact list; a contact who unsubscribed, bounced, replied (for
  anything but a reply) or booked; a guessed address; a message with a claim that is not in the
  profile, a do-not-claim term, a leftover marker or a missing opt-out line.
- Daily caps per channel, working hours in the recipient's time zone, a minimum gap between social
  actions, a 48-hour social pause after any platform warning.
- `mail.py` runs the guard itself before it opens a connection; `send_guard.py sent` refuses to log
  a social or form step without a fresh ALLOW.

**One thing that is not code:** the *verdict* is code, but a GATE is *cleared* by
`ledger.py approve --batch`, which the agent records after you answer the approval card — the same
shape as job-apply's submit gate. The card is the decision; the ledger line is its record. Every
hard rule above (caps, do-not-contact, stop-on-reply, guessed addresses, the claims linter, working
hours, `draft`) holds even if a batch is approved.

## By design

- No data broker, enrichment API or email verifier. No tracking pixel, no link redirect.
- One real mailbox (yours). The password lives in the macOS Keychain or `SBL_MAIL_PASSWORD`, never
  in the brain, never in a log.
- Social steps run in your own signed-in browser. Automation is off by default; turning it on is
  your decision, made with the risk stated: LinkedIn's terms do not allow automation and the
  account at risk is yours.
- Every send, block and gate is an event in the ledger. `ledger.py export --contact NAME` lists
  everything held on one person.
