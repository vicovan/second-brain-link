---
name: sales-onboarding
description: Set up the seller's sales profile — the offer and its proof points, the do-not-claim list, the ideal customer (segments, buyer and need roles, markets, buying signals, exclusions, the daily target and floor), the voice, and the sending settings (autonomy level, social automation, caps, working hours, the mailbox) — from the brain, the deck and the facts file first, asking only the decisions. Use on first run, when no sales profile exists, or for "set me up", "update my ICP", "change my caps", "connect my mailbox" or "turn on social steps".
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion
---

# Sales Onboarding

Writes `<sales layer>/profile/` — the only place the other skills read facts and settings from.

| File | Template | Holds |
|---|---|---|
| `offer.md` | `references/offer-template.md` | company, product, one-liner, **`offers:` (each with a `kind`: try · use · buy · partner)**, proof points, who it is not for, **## Do not claim** |
| `icp.md` | `references/icp-template.md` | segments, roles, `market.<Name>` regexes, sources on/off, signal weights, knock-outs, `daily_target`, `floor` |
| `voice.md` | `references/voice-template.md` | tone rules |
| `sending.md` | `references/sending-template.md` | `level`, `social_auto`, caps, working hours, time zone, mailbox, signature, opt-out line |
| `suppression.md` | written by `ledger.py suppress` | do-not-contact, append-only |
| `materials/` | Studio's settings uploads | deck, one-pager, case studies |
| `sources.md` | `explore.py` | the proven sources per market and the candidates the daily explores (20 %) |
| `scoring.md` | `references/scoring-template.md` | the lead score weights; the optimizer appends to its own block only |
| `stages.json` | `stages.py init` | stage labels / hidden stages (sbl-stages/1) |

Settings are `key: value` lines inside each file's first fenced block — keep that shape, the
gates parse it (`sales_profile.py show icp` prints what they see).

## Read first, ask last

1. The brain: the root layer's identity / organisation note, the voice layer (posts, content),
   the pipeline layer (won deals → existing customers and the segments that bought; lost deals →
   revival), `95-goals/sales-bd.md` if analyze.py wrote it.
2. `profile/materials/` — the deck and the facts file. **Every proof point must come from here or
   from the seller's own words in this conversation.** A number nobody wrote down is not a proof point.
3. Draft all four files, then ask only what the brain cannot know.

## The decisions to ask (AskUserQuestion, at most 4 questions per card)

- **What you sell and to whom** — confirm the drafted one-liner and segments, and the **offers**
  a buyer can take up: for each, its `kind` — *try* (a trial, a demo, a free tier), *use* (onboarding,
  a done-for-you pilot), *buy* (a paid plan), *partner*. The daily's strategy step picks one per account.
- **Markets** — which countries/cities, one `market.<Name>` line each.
- **Never a lead** — your own companies (current employers, your own startups), existing customers
  and competitors. The brain only knows roles marked current in your export, so ask; write them to
  `icp.md` `exclude` / `competitors` / `exclude_domains`, then `lead_score.py score --all`.
- **The daily target and floor** — defaults 10 and 60; a higher floor means fewer, better leads.
- **Autonomy** — `draft` (nothing is sent) · `supervised` (every send waits for your OK — the
  default) · `autonomous` (sends within the caps; first touches stay gated for the first
  `autonomous_gated_batches` batches; EU first touches gated while `eu_gate: on`).
- **Social steps** — ask it with the risk in plain words, never as a convenience:
  > *"When on, I send LinkedIn, X and WhatsApp Web messages myself in your signed-in Chrome, at
  > a human pace, and I stop for 48 hours on any warning page. LinkedIn's terms do not allow
  > automation, and the account at risk is yours. When off, I open the profile and prepare the
  > message — you press Send."* Default **off**.
- **The mailbox** — address, SMTP/IMAP host. Never ask for the password in chat. Tell the seller
  to run, in their terminal: `! python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/mail.py keychain-set`
  (macOS Keychain), or to set `SBL_MAIL_PASSWORD` for the session; then
  `mail.py check` (logs in, sends nothing). Gmail / Workspace need an app password.

## Finish — seed the daily, then show the line

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts
python3 $S/sales_profile.py check
python3 $S/sequence.py seed
python3 $S/stages.py init --contract ${CLAUDE_PLUGIN_ROOT}/studio.json --profile 48-sales/profile
python3 $S/explore.py add --sources 48-sales/profile/sources.md --source "<a source icp.md turns on, per market>" --proven
python3 $S/explore.py add --sources 48-sales/profile/sources.md --source "<a candidate: a directory, an event list, a community>"
python3 $S/harness.py seed sales                  # Goals: Start trials · Routines: Daily sales, Work my replies, Weekly sales review (off)
python3 $S/render_sales.py --quiet                # the first render: the dashboard, the KPI, the line
```

Say in one line what is set (level, markets, target/floor, mailbox connected or not), then:
*"Your daily is ready — switch it on in Routines or the Daily tab."*

Updating: change only the lines the seller named; never rewrite a file they edited by hand
without showing the diff. `level: autonomous` is set only when the seller asks for it in so many words.
