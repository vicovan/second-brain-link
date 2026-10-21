---
name: __ID__-onboarding
description: Set up (or update) the user's __WHAT__ profile — the facts, filters, scoring weights, sources and autonomy level every other skill reads — from their Second Brain first, asking only the decisions. Use on first run, when no __LAYER__/profile exists, or when the user says "set me up", "update my profile" or their situation changed.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion
---

# __SHORT__ onboarding

Writes `__LAYER__/profile/` in the user's brain — the ONLY source of facts about them. Nothing
personal ships in the plugin. `S=${CLAUDE_PLUGIN_ROOT}/skills/__ID__-core/scripts`.

| File | Holds | Template |
|---|---|---|
| `profile.md` | the facts, the filters, `level:` (supervised by default) | `references/profile-template.md` |
| `scoring.md` | the weights behind the score and the floor | `references/profile-template.md` §Scoring |
| `sources.md` | proven sources and candidates (explore.py's table) | written by `explore.py add` |
| `stages.json` | stage labels / hidden stages (sbl-stages/1) | `stages.py init` |

## Steps
1. Read the brain first (`00-me` or `00-org`, `10-people`, `15-organizations`); propose; ask only decisions.
2. Write the files above. `python3 $S/stages.py init --contract ${CLAUDE_PLUGIN_ROOT}/studio.json --profile __LAYER__/profile`.
3. Seed the goals and routines (off): `python3 $S/harness.py seed __ID__`.
4. First render: `python3 $S/render.py --quiet`.
5. Say: *"Your daily is ready — switch it on in Routines or the Daily tab."*
