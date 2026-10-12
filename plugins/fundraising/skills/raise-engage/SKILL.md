---
name: raise-engage
description: Find the public conversations where the founder's investors, operators and buyers are already arguing about the founder's problem — LinkedIn posts, X threads, Hacker News, Reddit — score them, and draft one useful comment per thread that answers what the thread is actually asking. Never posts, likes, follows or messages anyone; the founder pastes and posts. Use for "find threads to comment on", "where should I comment this week", "threads like this one", the daily engagement routine, or when the founder pastes a post they want to join.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, Agent
---

# Raise Engage — comment where the conversation already is

## Memory — every run (recall → act → reflect)
Follow `memory-protocol.md` (in `skills/raise-apply/references/`). Tool:
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/memory.py`, scope `fundraising`, tags `engage,claims`.
1. **First:** `memory.py recall --scope fundraising --tags engage,claims` — apply it, say in one line which items changed what you do, never re-ask what it answers.
2. **User says a preference, rule or correction** → `observe --source user` at once (`--scope shared` if it holds for every agent).
3. **An outcome lands** (a reply to a comment, a DM, an intro or a meeting that started in a thread) → `observe --source outcome` with the evidence, `--match` the item it strengthens.
4. **Last:** at most 3 inferred lessons → `observe --source agent`; end with *"Learned: …"*.

A cold email asks a stranger for time. A good comment in a thread a partner wrote — or a thread
their portfolio founders are arguing in — gives them something first, in public, where they
already are. This skill finds those threads and drafts the comment. **The founder posts it.**

## The boundary (never bends)
- **Nothing is posted, liked, followed, connected or messaged by you.** No social network is ever
  logged in to or driven in a browser — not through Chrome, not through any tool. You read
  **public** pages (WebSearch, WebFetch) and write notes. A thread becomes `posted` only when the
  founder says so (`threads.py posted <id>`, or the ✓ button which types it for them).
- A page you cannot read (a login wall, a removed post) is recorded `--unreadable` with what the
  search snippet said, and its comment note carries ⚠ — the founder reads the thread before posting.
- Every number and product claim in a comment passes the same facts lint as an email
  (`threads.py check` runs it). A red stops that comment.

## Step 0 — orient
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-engage/scripts/threads.py queries
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-engage/scripts/threads.py due
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-engage/scripts/threads.py list --status posted
```
`queries` reads `46-fundraising/profile/engage.md` (topics, adjacent products, people to watch,
platforms, `window_days`, `max_per_run`) plus the partners on Tier 1–2 targets. No `engage.md` →
write one from `round.md`'s `thesis_keywords` and `company.md`'s one-liner (template in
`references/comment-playbook.md`), show it to the founder in one line, and continue.

Drafted-but-unposted comments come first: list them (`due`) before finding more — a pile of
unposted drafts means the founder needs fewer, better ones, not more.

## Step 1 — find (cheap first)
1. Run the queries with WebSearch, newest first. A seed post the founder pasted counts as the
   first result; search for its topic, its author's other posts, and the people commenting on it.
2. Keep a thread only if **all** hold: inside `window_days`; the author or the commenters are
   people the founder wants to reach (an investor on the ledger, a partner, an operator in the
   space, a buyer); it has an **open question** a founder in this space can answer from
   experience; the founder has something true and specific to add.
3. Read the survivors' pages (WebFetch). More than 3 to read → say the fan-out, then at most
   `max_research_agents` read-only subagents; each returns `{url, author, posted, engagement,
   open_questions, readable}` — only you write the ledger.
4. `threads.py add --url … --platform linkedin|x|hn|reddit|other --author … --title … --posted
   YYYY-MM-DD --topic … --engagement "N reactions · M comments" --question "…" (repeat)
   --angle "…" --fit N [--investor-key KEY] [--unreadable]`. The fit score (0–100): who is in the
   thread 40 · an open question you can answer 30 · freshness 15 · reach 15. Under 60 → do not
   draft; it stays `found`.

## Step 2 — draft (at most `max_per_run`, best fit first)
Write each comment to a scratch file, following `references/comment-playbook.md`:
- **Answer the thread's open question** with something the founder actually knows — a mechanism, a
  number from the profile, a failure seen first-hand. Agreement and praise are not comments.
- **Complement, don't fight.** Never argue against the author's product or a competitor in their
  own thread; show where the founder's angle fits beside it.
- Name the founder's product **at most once**, and only where it is the honest answer to what was
  asked. Often the best comment never names it — the profile link does that work.
- 80–180 words; no hashtags; at most one link and only if asked for; end with a real question or
  a concrete offer ("happy to share the schema we use").

Then:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-engage/scripts/threads.py draft <id> --file <scratch>
```
It refuses a red comment (pitch phrases, the product named twice, more than one link, too long,
a number the profile does not hold) and writes `46-fundraising/engage/<day>/<Author> — <topic>.md`
with the thread, its open questions, the comment in a copy block, an **↗ Open the thread** link and
a **✓ I posted it** button. Fix and re-run on red; never "fix" a number by inventing it.

## Step 3 — close the run
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-engage/scripts/threads.py mark-run
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/render_brain.py --quiet
```
Report: how many threads were read, how many drafted (with links to the notes), the one to post
first and why. "Nothing worth joining today" is a normal, good result — say it in one line.

## When the founder reports back
- "I posted the comment on t-…" → `threads.py posted <id>` at once (sets a check-replies date two
  days out), re-render, one line back.
- A reply, a DM, an intro or a meeting that came from a thread → record it on the target
  (`ledger.py log-outcome` / `upsert` with origin `thread:<id>`) and `memory.py observe --source
  outcome`: which kind of thread and which kind of comment worked is the lesson that compounds.
- "Skip it" → `threads.py skip <id> --why "…"`.
