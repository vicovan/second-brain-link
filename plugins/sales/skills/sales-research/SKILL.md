---
name: sales-research
description: Research one shortlisted account in depth before anyone is contacted — the buying team (the economic buyer and the champion) from the company's own team, about and press pages and public posts, a reachable channel for each person (a brain tie, an intro path, a business address published on a public page, the contact form, a public profile), the why-now from its dated signals, every fact stamped with the page and the date it came from. Use for "research <account>", "who should I talk to at <account>", "add these to my pipeline", or after the lead report's top rows are approved.
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

## Finish

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/lead_score.py why <KEY>
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/ledger.py stage <KEY> target
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sales-scout/scripts/render_sales.py
```

Report per account in one line: the buyer, the way in, the why-now, and anything that stops it
(no reachable buyer, a knock-out found on the site — e.g. they already use a competitor and
`competitors` lists it). Then offer `sales-sequence`.

Never: invent a title or an address; read anything behind a login; keep personal (non-business)
addresses or phone numbers; research a person beyond their professional role.
