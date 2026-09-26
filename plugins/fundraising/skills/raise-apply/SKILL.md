---
name: raise-apply
description: Apply to one accelerator, fellowship, grant or fund pitch form end to end — find the real form, classify it, draft every answer from the founder's profile and stories within each field's tested limit, lint the answers against the facts file, fill the form in the founder's browser, verify every field in the DOM, then submit or stop at the approval gate per the founder's autonomy level. Use when the founder picks a program, says "apply to <program>", or names a row from the plan's Tier 1.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebFetch, WebSearch, Skill, Agent, mcp__claude-in-chrome__*
---

# Raise Apply

Turns one chosen program into a filed application: answers drafted and linted, every field filled
and verified in the DOM, then either **one gate** or **submission on the founder's behalf** —
whichever `level:` in `profile/answers.md` says. Read `references/field-policy.md` before touching
any form. It is not advisory.

## Autonomy — read it first, every run

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/founder_profile.py | head -4
```

| | `supervised` (default) | `autonomous` |
|---|---|---|
| Pick the program | gate | by tier + nearest deadline |
| The answers | gate (show `answers.md`) | self-approved once lint is green |
| Submit | gate — every time | you click submit, up to `max_submits_per_run` |

**Never switched off at either level** — each stops *this* application, reports one line, and
moves on: login or account creation · CAPTCHA · **a fee of any amount** · an identity number, date
of birth, payment detail or password · a **required video** (write talking points; the founder
records it — never reuse a video recorded for a different brief) · a `[CONFIRM]` or a required fact
the profile cannot answer · a red `lint_claims` gate · a field that will not verify in the DOM · a
limit whose unit you have not tested.

## The flow

### 1. Resolve and classify

Find the program's **own** application URL (never a third-party mirror). Save the page text when you
read it, then:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-apply/scripts/detect_form.py "<url>" [--html <saved page>]
```

A `needs_login`, `fee_signal` or `video_signal` is handled per the table above *before* any drafting.

### 2. Create the folder NOW — before a word is drafted

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/ledger.py log-app <key>
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/render_brain.py --quiet
```

The folder `46-fundraising/applications/<YYYY-MM-DD>/<key>/` appears in the founder's tree
immediately. An empty tree during a long drafting pass reads as nothing happening.

### 3. Read every question, then draft

Record the questions exactly as the form states them, with each field's limit. **Test the unit** of
any counter that does not say characters or words: type one character into the live field — if the
counter drops by one it counts characters. Record `"unit": "chars" | "words"`; until tested it is
`"unknown"` and the linter warns.

Draft from `company.md`, `founder.md`, `stories.md` and `answers.md` only, tailored to the program's
✅ thesis claims on its record. Write both:

- `answers.md` — paste-ready, one block per question with its count against its limit;
- `answers.json` — `{"program": …, "url": …, "fields": [{"label", "answer", "required", "limit":
  {"n", "unit"}}]}`, the permanent record of what was submitted.

Free-text answers are always composed, never left blank or handed back. Factual answers the profile
cannot support are **asked** (supervised) or **stop this application** (autonomous) — never guessed.

### 4. Lint — red stops

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/raise-research/scripts/lint_claims.py "<folder>/answers.json" --out "<folder>/gates.json"
```

### 5. Gate on the answers (supervised)

Three lines: the program, the nearest deadline, anything amber. Then `AskUserQuestion`: Approve ·
Edit · Skip. Not a field-by-field review.

### 6. Fill in the browser

Connect in THIS session (a subagent cannot): `list_connected_browsers` → **gate on which browser once
per run** (the extension requires the user to choose) → `select_browser` → `tabs_context_mcp`.
Fill every field from `answers.json`. Upload materials from `profile/materials/` only when a field
asks for that exact document.

**Read every field back from the DOM.** A field that displays a value it never registered is the
most common failure and is invisible unless checked; a dropdown that auto-selected something the
founder never said is a false statement made in their name. Record the result in `gates.json` under
`"dom": {"ok": …, "red": […]}`.

### 7. Finish according to the level

- `autonomous` and every gate green → click submit, confirm the success state (a confirmation page or
  message), then
  `ledger.py set-status <key> filed --by agent --note "submitted <url>"`.
- `supervised` → gate **Submit / Not yet**. On Submit, click, confirm, and log `filed --by founder`.
- A red anywhere → leave it filled, do not submit, say which field and why, move on.

Then `render_brain.py --quiet` and report in three lines what went out.

## Several programs at once

Steps 1–4 fan out as parallel subagents (≤ `max_research_agents`), each returning `answers.json` +
`gates.json`; steps 5–7 happen one program at a time in the one browser. **Only the main session
writes the ledger.**

## When the browser is not available

Say which it was (tool missing, no browser connected, a domain blocked by the extension — name the
domain), then hand over `answers.md` and the form URL for the founder to paste. That is an honest
outcome; sending the founder to a terminal is not.
