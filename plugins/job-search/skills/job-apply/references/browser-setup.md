# Browser setup — getting the user's Chrome connected

Shared by every skill in this plugin that works in the user's browser. The same file ships in
each plugin that has browser skills; keep the copies identical.

The browser is the **Claude in Chrome** extension running in the user's own Chrome. It does not
connect to this machine directly: it signs in to the user's **claude.ai account**, and every
Claude Code session on that account (the terminal, and the Studio agents, which run Claude
Code) sees the browsers connected to it. So "the extension is not connected" is almost always
one of five things, and each has a fix the **user** must do. Your job is to find which one and
tell them exactly what to click — not to retry in a loop, and never to guess.

## When to run this

- Before the first browser action of a run, as part of connecting.
- Whenever a browser tool fails with "not connected", "no browser", an unknown `deviceId`, or a
  permission block.

## The diagnosis, in order

**1. Are the browser tools in this session at all?** If no `mcp__claude-in-chrome__*` tool
exists, the session was started without Chrome. Tell the user:
- *In Studio:* "Start a new chat with this agent — it runs with Chrome enabled."
- *In a terminal:* "Restart Claude Code with `claude --chrome`, or run `/chrome` in the session."
- *In Codex, claude.ai or mobile:* there is no browser control; go straight to the fallback.

**2. `list_connected_browsers`.**
- **One or more browsers** → ask which one (AskUserQuestion: one option per browser, the ones on
  this computer first, display name as the label and the deviceId in brackets, plus the
  extension's "open a confirmation screen in every connected Chrome extension" option), then
  `select_browser` (or `switch_browser` for that last option). Ask once per run, even when only
  one is connected — the extension requires the user to choose.
- **An empty list** → the extension is not signed in or not running. Go to step 3.
- **`select_browser` says "No connected browser has deviceId …"** → the ID you had is stale.
  A browser gets a NEW deviceId after it signs in again or Chrome restarts. Never reuse an ID
  from an earlier run; list again.

**3. Tell the user how to connect it** — the steps below, as one short numbered list, then ask
(AskUserQuestion) with two options: **"Connected — try again"** and **"Skip the browser — give
me everything to do it myself"**. Wait for the answer; do not poll.

1. **Install it** if they don't have it: in Chrome, open the Chrome Web Store, search for
   **"Claude" by Anthropic**, and click *Add to Chrome*. It needs a paid Claude plan.
2. **Pin it**: click the puzzle-piece (Extensions) icon in Chrome's toolbar, then the pin next
   to Claude, so its icon stays in the toolbar.
3. **Open it and sign in**: click the Claude icon to open the side panel. If it shows
   **"Log in"**, click it and sign in.
4. **Use the SAME account as Claude Code.** A browser signed in to a different claude.ai account
   is invisible to this session. To see which account Claude Code uses, run `/status` in a Claude
   Code terminal; the Studio agents use that same login.
5. **Still nothing after signing in?** Quit Chrome completely (Cmd+Q on a Mac, not just the
   window), reopen it, and open the Claude panel once more.
6. Reply **"Connected"**.

When they say connected: `list_connected_browsers` again. If it is still empty, say so plainly,
point at the likeliest cause (step 4, the account), and ask once more. **At most two rounds** —
then take the fallback rather than burning the run.

**4. A site is blocked.** The extension asks permission per site. If a tool reports the domain
is not allowed, name the domain and tell the user: "In the Claude panel in Chrome, allow
`<domain>` when it asks (or in the extension's site permissions), then say *try again*." Don't
drop the task over a permission prompt; everything else can continue meanwhile.

## Never

- Enter, ask for, or handle the user's claude.ai password. Signing in is theirs to do.
- Say or imply the browser is connected until `list_connected_browsers` shows it, or narrate a
  browser step you did not actually take.
- Pick a browser for the user, or keep retrying the same failing call.
- Send the user to a terminal when they are in Studio (except to read `/status`, which is optional).

## The fallback — always finish something useful

If the browser can't be connected, finish every step that doesn't need it and hand over a
**manual packet**: the form or booking URL, the files to attach (with their paths), and every
answer or detail ready to copy — then say in one line what was skipped and why.

## While you drive the browser

- **Say what you're about to do, then do it.** One line before each fill or click — what, why,
  and where the value came from: `Filling "Years of experience": 12 ← [[00-me/identity]]`. A
  value with no source in the brain is left blank and said so: `Leaving "Salary" blank — no
  source in your brain`. Watching a cursor move with no reason reads as possession; a stated
  reason reads as help — and it is the user's own brain filling the form.
- **When the user takes over** (a login, a code, a CAPTCHA, or they just did something in the
  tab), **re-read the page before you continue** and say what changed: "You filled the email
  field — continuing from the cover-letter step." Never resume from a stale plan.
- **One tab at a time.** Helpers may research in parallel; only one run fills a form.
