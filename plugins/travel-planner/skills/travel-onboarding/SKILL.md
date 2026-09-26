---
name: travel-onboarding
description: Set up a person's travel profile — home airports, citizenships, companions, pace, budget, the taste the planner scores by, settled booking answers and preferred sites — reading their Second Brain places first so it only asks what the brain cannot know. Use on first run, when no travel profile exists, or when the user says "set me up for travel", "update my travel preferences", or their situation has changed.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, TodoWrite
---

# Travel onboarding

Writes five Markdown files into `<travel layer>/profile/` — and **nothing else ever writes
them**. Every other skill reads them.

| File | Holds | Missing means |
|---|---|---|
| `traveler.md` | home airports, citizenships (`visa_ok`), companions, cabin/seat, red-eyes, loyalty programme names, mobility and dietary needs | nothing can be shopped — ask first |
| `travel-criteria.md` | trip length, seasons, climate, pace, flight limits, layover and **stopover-night** tolerance, avoid-list, budget bands | the scout proposes the whole world |
| `taste.md` | cuisines, coffee, hotel style, neighbourhood, activity types — **proposed from the brain, confirmed by the user** | suggestions fall back to generic |
| `booking-answers.md` | **§0 Autonomy**, name as on passport, opt-in DOB and passport expiry, loyalty numbers | every run re-asks |
| `providers.md` | currency, preferred and blocked sites, metasearch order | neutral defaults |

Templates: `references/traveler-template.md`, `references/travel-criteria-template.md`,
`references/booking-answers-template.md`, `references/providers-template.md`. `taste.md`
comes from `taste.py`.

## Where to write, and where to look first

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/paths.py   # profile dir, other profile
```

Read order: **this surface** → **the other surface** (a profile in the other place: say so in
one line and offer to copy it) → onboard. Being asked to onboard twice, once per surface, is
the failure this order prevents. A file that exists is not rewritten unless the user asks —
show what would change first.

**One exception, copied from job-search:** if `booking-answers.md` exists but has no
`## 0. Autonomy`, ask the one question and **insert that section**, leaving every other line
untouched. Otherwise the setting is unreachable for long-standing users.

## Look before you ask

Mine the brain first, then **confirm every extracted fact** rather than assuming it:

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/trip-planner/scripts/
python3 $S/places.py                # places by city: saved, visited, reviewed
python3 $S/taste.py                 # the candidate taste.md, every line citing its notes
python3 $S/scout.py --no-write      # where the brain says they have been meaning to go
```

Also read, when present: `00-me/identity.md` (name, home city), the voice layer's
`interests.md`, and the mirror layer's `inferences.md` — resolve those folders with
`paths.py`, never by spelling a folder name.

Then say what you found in a few lines — *"You saved 9 places in Lisbon and visited none; you
rated three third-wave coffee bars ★5 and a buffet breakfast ★2."* — and ask only what the
brain cannot know:

1. Home airports (and any others they would fly from).
2. Citizenships, and any countries they have confirmed they may enter (`visa_ok`). Never
   decide a visa is unnecessary.
3. Who usually travels with them.
4. Pace, trip length, and whether **stopover nights on separate tickets** appeal — explain
   the self-transfer risk in one sentence before they answer.
5. Budget bands.
6. The autonomy level — explain `research` is the only level with any effect today.

Use `AskUserQuestion` for choices with few options; ask free text in prose.

## Writing

- `owner:` in every file's frontmatter must be the `title:` of `00-me/identity.md` —
  `find_brain.py` matches on it to know this brain is theirs.
- `taste.md`: run `taste.py --owner "<name>"`, show the candidate, apply the user's
  corrections, and write it with `status: confirmed`. Never write the candidate unconfirmed
  over an existing `taste.md`.
- Each file is independent. A run that can only fill three writes those three and says which
  are still missing — no placeholders, no refusal.
- **Never store** a passport or national ID number, a card number, or a password, even if
  offered. Date of birth and passport expiry go in §2 of `booking-answers.md` **only** if the
  user explicitly opts in.
- Run `render_brain.py --quiet` afterwards so the dashboard's profile line updates.

**Acceptance:** a second run with nothing changed writes nothing.
