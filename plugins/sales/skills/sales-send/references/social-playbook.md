# Social playbook — LinkedIn, X, WhatsApp Web

All of it happens in the seller's own signed-in Chrome. Nothing is rented, nothing logs in as
anyone else. Whether the agent presses Send is `social_auto` in `sending.md` (default off).

## LinkedIn connection request (`linkedin_invite`)

- Under 300 characters (the linter enforces it). Name the signal or the shared context; no pitch,
  no link.
- Open the profile URL from the account record. Check the page IS that person's profile (name,
  current company) before typing anything. A different person → stop that step.
- Already connected → skip the step (`sequence.py` moves on), log `ledger.py log connected`.

## LinkedIn message (`linkedin_dm`)

- Only to a connection (`requires: connected`). Two to four sentences, the same question as the
  email, shorter. No attachments.

## X DM (`x_dm`) and WhatsApp Web (`whatsapp`)

- Only where the person publishes that channel for business contact. WhatsApp only to a business
  number the person or company published for contact.

## Reading back

After pressing Send, read the conversation pane and confirm the message is there. Only then:
`send_guard.py sent --channel … --account … --contact … --step n --batch B --evidence "<the visible line>"`.
Not there → do not log it as sent; report it.

## Stop signs — stop every social step, pause 48 hours, tell the seller

A captcha · "unusual activity" · "you've reached the weekly invitation limit" · an account
restriction notice · a forced sign-in · any page that is not the expected profile or thread.

## Never

Like, follow, endorse, comment, view profiles in bulk, export connections, use Sales Navigator
automation, or message anyone not on the account record.
