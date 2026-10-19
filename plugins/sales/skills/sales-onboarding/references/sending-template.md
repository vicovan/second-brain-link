# Sending — autonomy, caps, mailbox

Written by `sales-onboarding` into `<sales layer>/profile/sending.md`. `send_guard.py` enforces
every line here in code; how a request is phrased in chat never changes it.

```settings
# draft: nothing is ever sent · supervised: every send waits for your OK · autonomous: the
# agent sends within the caps (first touches stay gated for the first batches)
level: supervised
# LinkedIn / X / WhatsApp Web messages sent BY THE AGENT in your signed-in Chrome.
# LinkedIn's terms do not allow automation and the account at risk is yours. Off = the agent
# opens the profile and prepares the message; you press Send.
social_auto: off
eu_gate: on
autonomous_gated_batches: 3
cap.email: 25
cap.linkedin_invite: 10
cap.linkedin_dm: 15
cap.x_dm: 10
cap.whatsapp: 10
cap.form: 10
max_sends_per_run: 25
days: MON,TUE,WED,THU,FRI
quiet_start: 08:00
quiet_end: 18:00
timezone: Europe/Lisbon
min_social_gap_s: 90
max_social_gap_s: 300
social_paused_until:
# your own mailbox (the password is never written here - mail.py keychain-set)
mail_user: jane@example.com
from_name: Jane Doe
smtp_host: smtp.example.com
smtp_port: 465
imap_host: imap.example.com
imap_port: 993
signature: Jane Doe\nNorthwind Data
opt_out: Reply 'no thanks' and I won't write again.
```
