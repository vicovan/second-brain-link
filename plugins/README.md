# plugins/ — capability packs that sit on top of a brain

The **engine** (`../engine/`) builds a brain: it turns your data exports into a private,
local, Obsidian-native knowledge vault. It is deterministic, stdlib-only, and makes
**zero network calls**.

A **plugin** is the other half: something that *uses* a brain to do work. It is a
[Claude Code plugin](https://docs.claude.com/en/docs/claude-code) — skills, commands and
scripts under a `.claude-plugin/plugin.json` — that reads the vault, acts in the world,
and writes its results back as a normal vault layer.

| | engine | plugin |
|---|---|---|
| Job | builds the brain | does work with the brain |
| Network | never | may, if it declares it |
| Ships as | `second-brain-link.skill` | its own zip / `--plugin-dir` |
| Lives in | `engine/` | `plugins/<name>/` |

> **Naming note.** "Plugin" here means a *Second Brain Link plugin*, not an **Obsidian
> community plugin**. The vault the engine emits still needs no Obsidian plugins at all —
> that promise is unchanged. Where this repo's docs discuss Dataview or Map View, those
> are Obsidian's plugins, not these.

## Why plugins are a separate distribution surface

The engine's zero-network guarantee is load-bearing: it is the reason the privacy claim is
verifiable rather than promised. A plugin that reaches job boards, or any other live service,
must not be able to weaken that.

So plugins are **not bundled into `second-brain-link.skill`**. `packaging/build_skill.py`
does not copy this directory. Installing the engine never installs a plugin, and a plugin's
network access is declared in its own manifest:

```json
"network": { "required": true, "why": "...", "endpoints": ["..."] }
```

This is OUR field, not Claude Code's. `claude plugin validate` warns that it is unknown and
ignores it at load time — that warning is expected, and the field stays: it is how a plugin
states, in the manifest a user can read before installing, what the engine's zero-network
promise does not cover.

## The contract

```
plugins/<name>/
  .claude-plugin/plugin.json     required — identity, licence, and the network declaration
  README.md                      required — what it does, and where the user's data lives
  skills/<skill>/SKILL.md        the actual capability
  commands/*.md                  optional — slash commands
  studio.json                    optional — makes it an Agent in Second Brain Studio
                                 (Studio reads your INSTALL; it bundles no copy)
  studio/grounding.md            required when studio.json is present
  providers/openai/SKILL.md      optional — the Codex packaging's manifest
  providers/openai/agents/*.yaml optional — Codex skill metadata
  docs/                          optional
  requirements.txt               optional — a plugin may have dependencies; the engine may not
```

## Two packagings, one source

The same split the engine skill uses, for the same reason: one implementation, thin
per-provider manifests.

| | Claude Code | OpenAI Codex |
|---|---|---|
| Unit | a **plugin** — several skills under one root | a **skill** — one self-contained folder |
| Layout | as authored | **flattened**: all `scripts/` in one dir, each skill's `SKILL.md` becomes `references/<skill>.md` |
| Script paths | `${CLAUDE_PLUGIN_ROOT}/skills/<s>/scripts/x.py` | `scripts/x.py` (rewritten at build time) |
| Manifest | `.claude-plugin/plugin.json` | `providers/openai/SKILL.md` |
| Built to | `dist/plugins/claude/<name>.zip` | `dist/plugins/openai/<name>/` + `.skill` |
| Installed | `~/.claude/skills/<name>` (`--install`), or `--plugin-dir` for a one-off | `~/.agents/skills/<name>` (`--install`) |

Flattening is only safe while **no two skills share a script or reference basename** —
`tests/run.py` checks the built archive for exactly that, and `build_plugin.py` refuses
the build on a collision rather than silently overwriting one file with another.

A packaging may honestly be narrower than the other. `job-search` on Codex does not fill
web forms, because Codex has no browser tooling; its manifest says so rather than implying
a capability it lacks.

Three rules a plugin must not break:

1. **Never write user data inside the plugin folder or this repository.** Resolve a state
   root from the environment, the user's brain, or their home directory. `job-search`'s
   `paths.py` is the reference implementation, and its module docstring explains the failure
   mode it exists to prevent.

   Inside a brain, that root is **`<brain>/.plugins/<plugin-name>/`**. Dot-prefixed on
   purpose: Studio's vault walker and Obsidian both skip dot-entries, so a plugin's working
   files travel with the brain — move it, sync it, back it up and its history comes along —
   without appearing in the tree beside the notes the user actually reads. It is also
   subject-agnostic, so it does not depend on resolving a layer name. A plugin's *output*
   belongs in a real layer; only its machinery lives here.
2. **Never hardcode a vault layer folder.** Layer *keys* are stable, folder *names* vary by
   subject (`45-jobs` for a person, `45-hiring` for a company) — go through
   `mappings/brain/layout.json`, as the engine does.
3. **Ship nothing personal.** No names, employers, locations, salary figures, or run history.
   Everything a plugin knows about its user comes from files that user's own onboarding wrote.

## Plugins in this repo

| Plugin | Does |
|---|---|
| [`job-search`](job-search/) | Runs a whole job hunt: sweeps open ATS boards against your criteria, tailors a CV per role, fills the application, and writes it all into `45-jobs/` |
| [`fundraising`](fundraising/) | Runs a raise: screens funds and programs against your own filter chain, verifies them on their own sites, writes a dated Funding Plan, drafts applications and investor emails (never sends them), and tracks it all in `46-fundraising/` |
| [`travel-planner`](travel-planner/) | Plans a trip from the places already in your brain — trip ideas from cities you saved and never visited, a day-by-day itinerary on Studio's Map, then flights (with self-transfer stopover nights), stays, ground and food read from public sites in your own browser — into `47-travel/`. Developer preview; books nothing |

## Install one

From a checkout of this repo (`git clone https://github.com/vicovan/second-brain-link && cd second-brain-link`):

```bash
python3 packaging/build_plugin.py <name> --provider claude --install   # → ~/.claude/skills/<name>
python3 packaging/build_plugin.py <name> --provider openai --install   # → ~/.agents/skills/<name>
```

`<name>` is `job-search`, `fundraising` or `travel-planner`. The Claude install is what the
CLI **and both Studios** (desktop and browser) read — one install, and the agent appears in
Studio's Agents tab. `claude --plugin-dir plugins/<name>` loads a plugin for one CLI session
only; Studio never sees it.

## Build one

```bash
python3 packaging/build_plugin.py <name>                          # both providers → dist/plugins/
python3 packaging/build_plugin.py all                             # every plugin
claude --plugin-dir plugins/<name>                                # try it from source, no install
```
