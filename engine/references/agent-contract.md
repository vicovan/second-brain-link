# The agent contract — `sbl-agent/1` (reference)

Every Second Brain agent is a plugin whose `studio.json` carries this contract. Studio reads
**only** the contract (no agent-specific code), `harness.py` schedules from it, `build_plugin.py`
refuses a plugin that is not contract-complete, and `validate_agent.py` is the rule book in code
(its TypeScript twin in Studio — `discover.ts` / `main/agents.ts` — must agree). Plan of record:
`second-brain-link-docs/docs-agents/AGENT-OPERATING-MODEL.md`.

## One loop, every agent

```
GOAL (96-agents/Goals, counted by `<ledger> count <success>`)  →  ROUTINE (Daily <what>, seeded off)
→ DAILY RUN through daily.py: preflight · recall · orient · OPEN THE DATED NOTE (## Status first)
  · discover (brain first → proven sources → 20 % explore) · screen + score · shortlist into the note
  · act behind the gates of `level:` · log · render after every change · reflect · handoff (the report, twice)
→ WEEKLY (Mon): kpi.py → optimize.py → reports/<Review> <date>.md  (caps never loosen)
```

## The keys

| Key | Required | Meaning |
|---|---|---|
| `schema` | yes | `"sbl-agent/1"` |
| `id` `label` `icon` `blurb` | yes | the agent; `color` optional (`#rrggbb`; Studio's palette otherwise) |
| `grounding` `entrySkill` | yes | `studio/grounding.md`; the `<x>-pipeline` skill that sequences the others |
| `subjects` `providers` | yes | `["personal","company"]`; `["claudecode"]` (+ `"codex"`) |
| `network` | yes | `{"declared": bool, "what": "…"}` — what the network is used for (the engine itself is zero-network) |
| `layer` | yes | one folder, the same name in both subjects (`45-jobs`, `46-fundraising`, `47-travel`, `48-sales`) |
| `layout` | yes | `dashboard` `kpi` `lessons` (file names) · `profile` `reports` (folders) · `items` `{kind: folder}` · `work` `{kind: folder}` · `extras` (declared extra notes/folders) — §Layout |
| `homeNote` | yes | the **dated daily note**: `<layer>/<reports>/<daily.note>.md` with `{date}` (and `{city}` for Travel — Studio matches `.+`, newest wins) |
| `homeNoteFallback` | yes | the Dashboard |
| `plan` | no | a living strategy note (Fundraising's `Funding Plan.md`) |
| `daily` | yes | `note` (`"Raise today {date}"`), `weekly` (`"Raise update {date}"`), `steps` (the toggles in the Daily settings tab), optional `sections` (the note's headings after Status/Goal/Picking up), optional `orient` (extra one-line commands daily.py runs at start) |
| `pipeline` `render.cmd` | yes | `<layer>/pipeline.json` and the agent's own deterministic render script (no AI, no network) |
| `home.cmd` | no | a starter view while the home note is missing |
| `canvas` | yes | `lines` · `map` (+ `canvasData`, `canvasLayers` under the layer) · `none` |
| `funnels` | yes | one per item kind: `{id, label, item, success, success2?, stages[{id, label, role, next?, gate?}]}` — fixed IDs; the user's labels/hidden stages live in `profile/stages.json` (sbl-stages/1), applied at render time |
| (pipeline.json) `throughput` | written by the render | `{label, value, series[12]}` — the lane monitor on idle lanes (`pipeline_doc.throughput()`); the contract's `throughput.cmd` stays the live counter |
| `floor` | yes (shipped agents) | ≤ 8 machine groups `{id, label, stages[], funnel?}`; without `funnel` the IDs match in every funnel (a shared machine); open/positive stages only; each `(funnel, stage)` in at most one group |
| `goals` | yes | one per funnel: `{template, metric, target}` — `template` names `harness/goals/<template>.md`, `metric` an `outcomes` key |
| `outcomes` | yes | `{key: {label, cmd}}` — a script that prints ONE number (`ledger.py count meetings`); the goal counters |
| `throughput` | yes | `{label, cmd}` — the lane monitor (applications/day, touches/day) |
| `routines` | yes | `[{template, kind: daily|weekly|monthly}]` — `harness/routines/<template>.md`, seeded **off** by onboarding; R5 naming `Daily <what>` / `Weekly <what>` |
| `optimize` | yes | `{sources, scoring, signals[], explore}` — the ONLY files the optimizer may edit, the item attrs it groups by, the explore share |
| `concurrency` | yes | `{weight: heavy|light, browser, parallel_items}` — heavy runs take one of `max_concurrent` (2) slots |
| `inspector` | yes | `{item kind: job|account|target|trip|place|generic}` — the Inspector card layout per kind |
| `persona` | yes | the Avatar persona id |
| `settings` | yes | the existing files/keys/form blocks + `"daily": true` (the generic Daily tab: time · days · steps · level · goal target/by · apply optimizations · explore share) |
| `requires` | yes | `{profile, onboardSkill}` — the file whose absence means "not set up" |
| `preflight` | yes | `profile_present` · `chrome_connected` · `ai_signed_in` · `brain_built` |
| `suggestions` | yes | the chat bar chips `{t, q, stage: setup|today|do|track, short?, when?}` — `today` cards are the daily's own actions one at a time (Studio lists them under the daily card as **Today**) |
| `templates` | yes | the folder of goal/routine templates (`harness`) |
| `tools` `chrome` `watchGlob` | as before | the tool ceiling, the Chrome flag, what Studio watches |

## The standard layout (Jobs is the standard)

```
<layer>/
  <Agent> Dashboard.md        living overview — written by render.cmd only; the home fallback
  <Agent> KPI.md              funnel counts, conversions, rates at n ≥ 20, trends (kpi.py)
  <Agent> Lessons.md          the readable mirror of _memory/ scope <agent> (inferred items flagged)
  pipeline.json               sbl-pipeline/2 with funnels + floor — machine data, always rewritten
  profile/                    the user's facts, filters, scoring.md, sources.md, stages.json — onboarding + the optimizer only
  reports/<Daily> <date>.md   the dated daily note (the home) · reports/<Review> <date>.md (weekly)
  <items>/<key>.md            one living note per item
  <work>/<date>/<key>/        per-item work on a date
  (extras)                    declared in layout.extras
.plugins/<agent>/             the ledger (name per plugin) · events.jsonl · lock · _<AGENT>_GENERATED.json · daily/<date>.json · stamps
```

Renames go through `render.cmd --migrate-layout`: a file still matching the manifest is moved and
gets `aliases: [old title]`; a user-edited file stays where it is and is reported (never
destroyed). `--refresh` and the next render are byte-stable afterwards.

## The shared libraries (byte-identical in every plugin; `build_plugin.SHARED_FILES`)

| File | Responsibility | A new agent supplies |
|---|---|---|
| `daily.py` | the runner: `start` (preflight · recall · orient · the dated note · the run · first render) · `status` (## Status + run step `[phase] line` + debounced render) · `section` (script text between `<!-- x:begin/end -->` markers) · `explore` · `pace` · `close` (the fence → sbl-report, final render) | nothing |
| `ledger_base.py` | `Ledger` (records + events + transitions + lock + `count` `table` `since` `due` `migrate`), the R6 `Writer` (manifest; edited notes kept, `.new.md` beside), `replace_between`, `add_alias` | its record file name, its transitions, its due rules |
| `kpi.py` | funnel counts · conversions · success rate (n ≥ 20) · 7/28-day trend · by-signal · `KPI.md` body | nothing |
| `optimize.py` | proposals from the pipeline + events + sources (leak · reweight · promote/drop · idea); applies per level inside the optimizer marker block; refuses `cap.*`, `max_*`, `level`, gates | its `optimize.signals` |
| `explore.py` | `profile/sources.md` (Proven / Candidates tables with yield), deterministic daily rotation, promotion / demotion | its sources file |
| `report.py` | `normalise` · `fence` · `chat` (the fixed order) · `close` | nothing |
| `stages.py` | `profile/stages.json` defaults / validation / `apply` | nothing |
| `pipeline_doc.py` `harness.py` `memory.py` | the pipeline file, the harness, the memory layer | nothing |

Run phases (`daily.py status --phase`): `picking-up` · `discovering` · `screening` · `shortlisting` ·
`acting` · `rendering` · `reflecting` — each run step line is `[<phase>] <text>`; Studio's Worker
groups the steps by them.

## The rules (R-list, from the plan of record)

R1 render early, render always · R2 numbers from scripts, never from the model · R3 the home, the
dashboard and the daily note are declared · R4 links by title, never to a note that does not
exist · R5 routine names `Daily <what>` / `Weekly <what>` · R6 never destroy a hand edit · R7 one
writer per ledger · R8 the report, twice · R9 Studio derives · R10 memory: recall / observe /
reflect · R11 wording: stage labels Title case, one or two words · R12 honesty fields (`quoted_at`,
`seen_at`, `from_brain`, rates at n ≥ 20, no bought data, a guessed address never sent).

## Build an agent

```bash
python3 packaging/new_agent.py --id briefing --label "Briefing Agent" --layer 49-briefs \
    --funnel "meetings=upcoming>briefed>held*;cancelled~" --what briefing
python3 engine/scripts/validate_agent.py plugins/briefing       # ok
python3 packaging/build_plugin.py briefing                        # both packagings
```

The scaffold passes every check with stub logic. Then replace `sources.py` (discovery),
`score.py` (the rubric), `actions.py` (what "act" means, behind the gates), the words of
`<id>-pipeline/SKILL.md` and the profile files `<id>-onboarding` writes. See `plugins/README.md`
→ *Build an agent*.
