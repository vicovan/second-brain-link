---
name: sales-research
description: Research one shortlisted account in depth before anyone is contacted — the buying team (the economic buyer and the champion) from public pages, a reachable channel for each person with its evidence, the why-now from its dated signals, then the strategy (the angle, which offer to get them to try, use, buy or partner on, the conversion goal) and the reach-out mix ranked with reasons. Use for "research <account>", "who should I talk to at <account>", "what's the angle for <account>", "add these to my pipeline", or after the daily note's top rows are approved.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, Agent
---

# Sales Research — one account, in depth

Memory: `memory.py recall --scope sales --tags research` first
(`${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/memory.py`).

**Fan-out is told first.** Researching N accounts in parallel spends N agents: say the number
before spending it (default at most 3 at once), and research in the main thread when it is 1–2.
Important research agents inherit the main model — never a smaller one.

## For each account

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py get <KEY>
```

1. **What the brain already knows** — the account's contacts with `person_note`, the deal
   history, intro paths. Read those notes (and the org note if one exists) before the web.
2. **The buying team** — from the company's own team / leadership / about / press pages, and
   public posts. Find the **economic buyer** (an `icp.md` buyer role) and a **champion** (a
   champion role, or whoever the signal names — the hiring manager of the posted role, the person
   who wrote the post). Two to four people, never a spray of every name on the page.
3. **A way in per person** — record each with its evidence:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py contact <KEY> --name "Dana Reyes" \
       --role "VP Operations" --role-source "https://globex.example/team" \
       [--email <the published address> --email-source public-page] [--profile-url https://linkedin.com/in/…] \
       [--channels email,linkedin] [--tz Europe/Berlin] [--region eu]
   ```
   - An address goes in **only** when it is written on a public page (team page, press release,
     speaker bio, docs, the person's own site) or in the brain. Keep the page as `--role-source`.
   - A pattern you inferred (first.last@domain) → `--email-source pattern-unverified`. It is
     shown, never sent; route that person through the form, social or an intro.
   - A connector who can introduce → add them as a contact with role "connector" and
     `--tie-via` naming whom they know.
   - The company's own contact or demo form → `ledger.py set <KEY> form '{"url": "…", "platform": "…"}'`
     (classify it with `detect_form.py URL`).
4. **Why now** — the one or two dated signals that make this the week (already on the account
   from the sweep; add any the site showed as a signal row and re-merge).
5. **Segment** — `ledger.py set <KEY> segment "<the icp segment it fits>"` (KPIs group by it).
6. **The strategy** — from the `offers:` block of `profile/offer.md` (each offer has a `kind`:
   **try** — a trial, a demo, a free tier · **use** — onboarding, a done-for-you pilot · **buy** — a
   paid plan · **partner**) and the account's dated signals, decide in three lines:
   - *why now* — the signal that makes this the week;
   - *the angle* — the one claim from the offer that meets that signal (a proof point the linter
     will accept, never an invented number);
   - *the conversion goal* — "get them to **try** <offer>" (or use / buy / partner): the smallest
     next commitment that fits the signal.
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py set <KEY> strategy "try"
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py set <KEY> offer "<offer name from offer.md>"
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py set <KEY> angle "<one line: the signal → the claim>"
   ```
7. **The reach-out mix** — rank the channels for this account with a reason each, as choices
   (the seller or the level decides, the sequence follows them):
   warm intro via a brain tie · email from the seller's own mailbox (a published address only) · a
   LinkedIn / X note (social steps are **off by default**; LinkedIn's terms do not allow automation
   and the account at risk is the seller's) · the company's contact form · a community or event
   touch · content to share. `ledger.py set <KEY> channels '["intro","email","form"]'` — in order.

## Finish

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/lead_score.py why <KEY>
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py stage <KEY> researched
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/render_sales.py
```

Report per account in one line: the buyer, the way in, the why-now, the strategy and angle, the best
channel, and anything that stops it
(no reachable buyer, a knock-out found on the site — e.g. they already use a competitor and
`competitors` lists it). Then offer `sales-sequence`.

Never: invent a title or an address; read anything behind a login; keep personal (non-business)
addresses or phone numbers; research a person beyond their professional role.
