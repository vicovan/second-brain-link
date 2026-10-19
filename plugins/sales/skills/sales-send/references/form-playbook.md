# Contact-form playbook — the company's own "contact us" or "book a demo"

A company that publishes no address usually publishes a form. It is a sanctioned way in, and it
is how the agent reaches buyers without guessing an address.

1. Classify: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/detect_form.py URL [--html saved.html]`.
   A login, a fee or a captcha → hand-off with the URL; never fight it.
2. Fields: name, work email, company, phone (leave it empty unless the offer profile has a
   business number), message, and any picklist (choose the honest option — "Partnership" or
   "Other", never "I'm a customer").
3. The message: the email's first touch, shorter, within the field's limit — type one character
   to see whether the counter is characters or words.
4. Verify every field in the DOM before submitting.
5. Guard: `send_guard.py check --channel form --kind form …`. ALLOW → submit; keep the
   confirmation text as evidence → `send_guard.py sent --channel form … --evidence "<confirmation>"`.
6. One form per company per sequence. A demo-booking widget that asks for a time is a meeting:
   pick a slot only when the seller's calendar is free and the level allows it.
