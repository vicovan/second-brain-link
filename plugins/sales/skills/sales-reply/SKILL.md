---
name: sales-reply
description: Work the replies — read new mail from the people the seller has written to (the seller's own mailbox over IMAP, or a reply the seller pastes), classify each one, stop that contact's sequence, suppress an unsubscribe at once, answer routine replies and propose meeting times from the seller's calendar, book the meeting when the prospect picks a slot, route referrals to a new contact, and hand pricing, legal and objections to the seller. Use for "work my replies", "did anyone reply", a pasted reply, "book it", or the replies routine.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion, mcp__claude_ai_Google_Calendar__*
---

# Sales Reply

Memory: `memory.py recall --scope sales --tags reply,objections` first; every outcome (a meeting,
a no, a "not now" and its date, an objection and how it went) → `observe --source outcome`.

## 1. Read

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/mail.py read --days 7
```
Or the reply the seller pasted. Match each to the ledger (`account`, `contact`); two candidates →
ask, never guess. Mark each one read in the ledger so it is not worked twice:
`ledger.py log reply_read --account KEY --contact "Name" --data '{"message_id": "…"}'`.

## 2. Classify — and quote the sentence that decided it

| Class | Do | Gate |
|---|---|---|
| `meeting-ask` | propose three slots (step 4) | routine — sent at `autonomous` |
| `info-ask` | answer from `offer.md` / materials only | routine |
| `scheduling` | confirm / move the time | routine |
| `ooo` | `ledger.py log ooo` with the return date; the sequence waits | none — nothing is sent |
| `referral` | thank them (routine), add the new person (`ledger.py contact … --tie-via "<replier>"`); their first touch quotes the referral and **always gates** | thanks routine; new touch gated |
| `not-now` | thank them; `sequence.py start KEY --sequence "Not now — wake later"` on the date they named (else ninety days on) | routine |
| `objection` / `pricing` / `legal` / `security` | draft an answer for the seller; never send it yourself | **always GATE** |
| `unsubscribe` / "no thanks" | `ledger.py suppress <address> --reason unsubscribed` at once, `ledger.py log unsubscribed`, no answer | none — nothing is sent |
| `bounce` | `ledger.py log bounced`; route that person through another channel | none |
| `negative` (not interested) | a one-line thank-you only if the seller wants those; stage stays | gated |

Log the reply: `ledger.py log replied --account KEY --contact "Name" --channel email --data '{"reply_class": "<class>", "summary": "<one line>"}'`,
and `ledger.py stage KEY replied` (a meeting ask moves on to `meeting` once booked). The sequence
stops for that contact on its own (stop-on-reply).

## 3. Answer

Write the answer like `sales-send` step 2 (short, their words, one thing), lint it, then:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/mail.py send --account KEY --contact "Name" \
    --to <their address> --subject "Re: <their subject>" --body-file FILE --kind reply \
    --reply-class <class> --in-reply-to "<their Message-ID>" --batch $B
```
The guard gates every reply at `supervised`, and the non-routine classes at every level — gated
answers go into one batch and one approval card exactly as in `sales-send` (`batch.py add` / `batch.py card`).
After a sent answer: `ledger.py log answered --account KEY --contact "Name"`.

## 4. Meetings

- Free/busy from the Google Calendar connector when it is connected (otherwise ask the seller for
  three times). Offer three slots in the prospect's time zone across two days, inside working hours.
- The prospect picks one: at `autonomous`, create the event (title "<Company> × <Seller company>",
  the prospect as attendee, the seller's meeting link if `offer.md` has one); otherwise propose it
  to the seller in one card. Then `ledger.py log meeting_booked --account KEY --contact "Name" --data '{"when": "<ISO>"}'`,
  `ledger.py stage KEY meeting`, and offer `sales-brief`.

## 5. Finish

`render_sales.py`. Report: replies by class, what was answered, what waits for the seller (with
the drafted answer), meetings booked, suppressions added.
