# Install Second Brain Link — the complete guide (for people and for AI agents)

> **If you are an AI agent** (Claude Code, Codex, Claude Desktop…) and the user asked you to install Second Brain
> Link: follow this file top to bottom. Detect before you act, **ask the user before every step that installs
> software or changes their system**, never ask for or type a password or API key yourself, and finish with the
> checks in §7. Explain each step in one plain sentence — the user may not be technical.
>
> **If you are a person:** the easiest way is the desktop app — download it from
> <https://secondbrainlink.com/download> and its Setup wizard does everything below for you, Python included.

## What gets installed

| Piece | What it does | Where it goes |
|---|---|---|
| **An AI tool** — Claude Code (recommended) or OpenAI Codex | The AI that builds and uses the brain, on the user's own plan | The vendor's standard location |
| **The brain builder** (`second-brain-link` skill) | Turns data exports (LinkedIn, Google, Facebook…) into a private brain | `~/.claude/skills/second-brain-link` · Codex: `~/.agents/skills/second-brain-link` |
| **Agents** — Jobs (`job-search`), Fundraising (`fundraising`), Travel (`travel-planner`) | Use the brain to do work | `~/.claude/skills/<name>` · Codex: `~/.agents/skills/<name>` |
| **Python 3.8+** | Runs the brain builder and the agents' scripts | System (the desktop app has its own built in) |
| **Second Brain Studio** (optional, recommended) | The app: see the brain, chat with it, run agents | Applications / Program Files / AppImage |
| **Claude in Chrome** (optional) | Lets the Jobs and Travel agents fill forms and search flights in the browser | Chrome extension |

`~` is the user's home folder on every OS (Windows: `%USERPROFILE%`).

## 1. Detect the computer

| Check | macOS / Linux | Windows (PowerShell) |
|---|---|---|
| OS + chip | `uname -sm` | `$env:PROCESSOR_ARCHITECTURE` |
| Claude Code | `claude --version` | `claude --version` |
| Codex | `codex --version` | `codex --version` |
| Python | `python3 --version` | `python --version` or `py -3 --version` |
| Already installed? | `ls ~/.claude/skills ~/.agents/skills` | `dir $HOME\.claude\skills, $HOME\.agents\skills` |

A folder in `~/.claude/skills` that is a **symlink** is a developer install — never replace or delete it.

## 2. The AI tool

Ask which AI the user wants to pay for:
- **Claude Code** (Claude Pro/Max plan) — recommended; the only one that runs the agents inside Studio.
- **Codex** (ChatGPT plan) — builds and chats; the agents install as Codex skills.
- **Neither / an API key** — then use the desktop app: it builds the brain with its own Python and chats through the key.

Install (after the user says yes):

| | macOS / Linux | Windows |
|---|---|---|
| Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash` | `irm https://claude.ai/install.ps1 \| iex` |
| Codex | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh` (or `brew install --cask codex`) | `irm https://chatgpt.com/codex/install.ps1 \| iex` |

Official pages if a command changed: <https://docs.anthropic.com/en/docs/claude-code/setup> ·
<https://github.com/openai/codex>.

**Sign in:** `claude auth login` (Codex: `codex login`) opens the browser; the user completes the login themselves —
never handle their credentials. Check it worked: `claude auth status` shows `"loggedIn": true` (Codex:
`codex login status`).

## 3. Python

Needed for terminal use (the desktop app brings its own). If `python3 --version` (Windows: `python --version`) fails
or is below 3.8, ask, then:

| OS | Command |
|---|---|
| macOS | `xcode-select --install` (or the installer from <https://www.python.org/downloads/>) |
| Windows | `winget install Python.Python.3.12` |
| Ubuntu / Debian | `sudo apt install python3` |
| Fedora | `sudo dnf install python3` |

Optional, for PDF CVs from the Jobs agent: `python3 -m pip install --user reportlab`.

## 4. The brain builder and the agents

One command installs everything for every AI tool it finds, verifying each file's checksum:

| OS | Command |
|---|---|
| macOS / Linux | `curl -fsSL https://secondbrainlink.com/install.sh \| sh` |
| Windows | `irm https://secondbrainlink.com/install.ps1 \| iex` |

Options: `--claude` / `--codex` (one tool only), `--no-agents` (brain builder only); Windows: `-Claude`, `-Codex`,
`-NoAgents`.

**Manual fallback** (no script): download the files listed in
<https://github.com/vicovan/second-brain-link/raw/main/dist/manifest.json> (each entry has `file`, `sha256` and
`installs_to`) from `https://github.com/vicovan/second-brain-link/raw/main/dist/<file>`, unzip each (a `.skill` is a
zip) and move the single folder inside to `~/<installs_to>`.

**Developers:** `git clone https://github.com/vicovan/second-brain-link && cd second-brain-link && python3
packaging/build_skill.py all --install && python3 packaging/build_plugin.py all --provider all --install`.

## 5. Browser extension (only for the Jobs and Travel agents' browser steps)

1. Install **Claude in Chrome** from the Chrome Web Store and pin it.
2. Sign in to it with the **same Claude account** as Claude Code.
3. Restart Chrome; in Claude Code the agent then connects on its own. Full playbook inside each agent:
   `skills/*/references/browser-setup.md`.

## 6. First brain

1. Download the user's data exports (LinkedIn, Google Takeout, Facebook, Instagram…) — how, per source:
   <https://secondbrainlink.com/sources>.
2. **With Studio:** Sources → add yourself → upload each `.zip` → **Build**.
   **In the terminal:** put them in `data/personal/<your-name>/<source>/` and tell Claude Code / Codex:
   *"Build my second brain from data/"*.
3. Agents: in Studio open the **Agents** tab → "Set up my profile". In Claude Code: `/job-search:onboard`,
   `/fundraising:fund-onboard`, `/travel-planner:onboard`.

## 7. Verify

| Check | Expect |
|---|---|
| `ls ~/.claude/skills` (or `~/.agents/skills`) | `second-brain-link` (+ `job-search`, `fundraising`, `travel-planner`) |
| `claude plugin list` | `job-search@skills-dir`, `fundraising@skills-dir`, `travel-planner@skills-dir` |
| `cat ~/.claude/skills/second-brain-link/VERSION` | a version number |
| Studio → Help → Set up Second Brain | every step ✓ |

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `claude: command not found` right after installing | Open a new terminal (PATH refresh); on macOS/Linux check `~/.local/bin` is on PATH |
| Studio says "Claude Code not found" | Quit and reopen Studio after installing; Studio reads your login-shell PATH |
| Studio says "not signed in" | Run `claude auth login` (Codex: `codex login`) and finish the browser login |
| An agent is missing in Studio | Re-run the install command in §4, then reopen the Agents tab |
| "left as is — developer link" | Expected for a developer checkout; nothing to do |
| macOS: "app can't be opened" | Right-click the app → Open → Open (first launch only) |
| Windows: "Windows protected your PC" | More info → Run anyway |
| Linux AppImage won't start | `chmod +x SecondBrainStudio-linux-x64.AppImage` |
| Chrome steps say "not connected" | §5: same account in the extension and Claude Code, then restart Chrome |
| Checksum mismatch | Re-run §4 (a download was interrupted) |

Everything installed runs locally. The brain builder makes no network calls; agents declare the sites they reach in
their own `.claude-plugin/plugin.json`.
