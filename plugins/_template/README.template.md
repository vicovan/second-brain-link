# __LABEL__ — a Second Brain Link agent (`__ID__`)

> Scaffolded by `packaging/new_agent.py` on the `sbl-agent/1` contract. Replace every
> "stub" below with the domain logic; the loop, the contract and the shared libraries are done.

**What it does.** __BLURB__

**Where your data lives.** Everything about you comes from `__LAYER__/profile/` (written by
`__ID__-onboarding`, never shipped). The agent writes its results into `__LAYER__/` in your brain —
the dated daily note (`reports/__DAILY__ <date>.md`), `__SHORT__ Dashboard.md`, `__SHORT__ KPI.md`,
`__SHORT__ Lessons.md`, one note per item under `__ITEMS__/`, and `pipeline.json` for Studio's
Runtime. Its machinery (the ledger, events, the manifest) sits in `<brain>/.plugins/__ID__/`.

**The loop (every run).** recall → orient → open the daily note → discover (brain first, proven
sources, a 20 % explore slice) → screen and score → shortlist into the note → act behind the
gates of `level:` → log → render → reflect → report. Shared runner: `daily.py`; weekly:
`kpi.py` → `optimize.py` → `reports/__WEEKLY__ <date>.md`.

**Network.** __NETWORK__

## Install

```bash
python3 packaging/build_plugin.py __ID__ --provider claude --install
```

## Files to fill in

| File | Stub to replace |
|---|---|
| `skills/__ID__-core/scripts/sources.py` | discover candidates (the proven sources + today's explore slice) |
| `skills/__ID__-core/scripts/score.py` | the deterministic rubric from `profile/scoring.md` |
| `skills/__ID__-core/scripts/actions.py` | what "act" means for this agent (always behind the gates) |
| `skills/__ID__-pipeline/SKILL.md` | the domain words of each step |
| `skills/__ID__-onboarding/SKILL.md` + `references/` | the profile files the agent reads |
