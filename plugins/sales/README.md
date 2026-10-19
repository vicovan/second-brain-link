# sales — run outbound from your Second Brain

A Second Brain Link plugin. It finds leads, researches the buying team, runs your sequences, sends
from **your own** mailbox and browser within **your** caps, works the replies and books the
meetings — as the `48-sales/` layer of your brain, and as the **Sales Agent** in Second Brain
Studio (with the **Pipeline** board on the centre canvas).

> **Warm first.** Before it searches the web, it reads what your brain already knows: decision-makers
> you are warm with, strong ties gone quiet, lost deals worth reopening, people someone you know
> can introduce you to. Then it adds companies with a reason to buy now — and ranks both on one scale.

## What it does

| You say | It does | Skill |
|---|---|---|
| "Set me up" | builds your offer, ideal customer, voice and sending settings from the brain and your deck; asks only the decisions | `sales-onboarding` |
| "Who would take my call?" | the leads your brain already holds — no web, no cost | `sales-scout` (brain tier) |
| "Find me leads" | the daily sweep: brain → every market's sources → the companies' own sites → merge → **coverage gate** → knock-outs → score → shortlist above your floor | `sales-scout` |
| "Research Globex" | the buying team, a reachable channel for each person (with evidence), why now | `sales-research` |
| "Start sequences" | a cadence per account; first touches come back as one approval batch | `sales-sequence` |
| "Send what's due" | email from your mailbox, social steps in your Chrome, contact forms — every one through the send guard | `sales-send` |
| "Work my replies" | read, classify, answer, propose times, book; unsubscribes suppressed at once | `sales-reply` |
| "Brief me for my next call" | history, who's on the call, why now, the one outcome to aim for | `sales-brief` |
| "How is it going?" | replies and meetings by origin / segment / channel / step; at most three changes | `sales-optimize` |

Commands: `/sell` · `/sales-leads` · `/sales-onboard` · `/sales-due` · `/sales-outcome` · `/sales-kpi`.

## The rules it keeps

- **`send_guard.py` decides every outward act** — deterministic code, the same for every channel:
  ALLOW · GATE (your approval card) · ASSIST (you press Send) · BLOCK (never sent, logged with the
  rule). The hard rules hold whatever you approve; a GATE is cleared by the agent recording your
  answer to the card (`ledger.py approve`). See `docs/safety.md`.
- **Autonomy is a setting.** `level: supervised` (the default) gates every send; `autonomous` sends
  within your caps, with first touches still gated for the first batches; `draft` sends nothing.
- **Every claim traces to your profile.** A number that is not in your offer or materials is refused.
- **No bought data.** Addresses come from your brain or a public page; a guessed one is never sent.
- **A market is never "empty" on one source.** Fewer than three sources and no leads = a coverage
  failure, and the sweep widens.

## Where your data lives

Nothing personal ships in this plugin. Everything is written into **your** brain:

```
<brain>/48-sales/            notes you read: Pipeline.md, pipeline.json (the board), accounts/,
                             leads/Leads <date>.md, sequences/, profile/ (written by onboarding
                             and Studio's Sending tab)
<brain>/.plugins/sales/      machinery, hidden from the tree: accounts.jsonl, events.jsonl
                             (append-only), scout_state.json, last_shortlist.json, _SALES_GENERATED.json
```

Outside a brain the state root is `$SALES_HOME`, else `~/.second-brain/sales`.
`python3 skills/sales-scout/scripts/paths.py` prints every decision.

## Your mailbox

Set `mail_user`, `smtp_host` and `imap_host` in `profile/sending.md`. The password never goes in
the brain: run `python3 skills/sales-scout/scripts/mail.py keychain-set` in a terminal (macOS
Keychain) or set `SBL_MAIL_PASSWORD` for the session, then `mail.py check` (logs in, sends nothing).
Gmail and Google Workspace need an app password.

## Install

```bash
python3 packaging/build_plugin.py sales --provider claude --install   # → ~/.claude/skills/sales (CLI + both Studios)
python3 packaging/build_plugin.py sales --provider openai --install   # → ~/.agents/skills/sales (Codex)
claude --plugin-dir plugins/sales                                    # one CLI session only
```

MIT licensed. Part of [Second Brain Link](https://secondbrainlink.com).
