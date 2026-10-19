---
name: sales-brief
description: Write the pre-call brief for a booked meeting or any account — the deal history from the brain's pipeline layer, everyone on the seller's side who ever touched the account, the shared connections, the people on the call and their public roles, what they said in their replies, their public signals and posts, the open questions and the one outcome to aim for — as a note beside the account. Use for "brief me for my next call", "prep me for <account>", "what do we know about <account>", or after a meeting is booked.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebFetch
---

# Sales Brief

Read-only on the world: at most a WebFetch of the account's own news page or the attendees'
public posts from the last month. Everything else is the brain and the ledger.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py get <KEY>
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py events --account <KEY> --json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/sequence.py timeline <KEY>
```

Write `<sales layer>/accounts/<Name> — brief.md` (front matter `type: sales-brief`, `account:`,
`meeting:`), in this order:

1. **The one outcome to aim for** — the next step that would count (a pilot scope, a second call
   with the economic buyer), not "build rapport".
2. **Who is on the call** — name, role (with its source), their own words from the replies,
   your tie (strength, last contact, shared people).
3. **History** — every deal note for the account, the people on the seller's side who touched it
   (the pipeline layer and mail-header signals in the brain), and why the last one stopped.
4. **Why now** — the dated signals.
5. **What they will ask** — from the offer profile's "who it is not for", past objections in
   memory, and the reply classes so far; an honest answer for each, from the profile only.
6. **Open questions** — what you do not know yet and should ask.

No claim about the seller's product that is not in `offer.md` or materials. Say "unknown" where
the brain is silent — a blank is honest, a guess is not.

Then `render_sales.py` and one line back with the outcome to aim for.
