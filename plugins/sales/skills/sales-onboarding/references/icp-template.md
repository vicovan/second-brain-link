# Ideal customer — who to find, where, and on what signal

Written by `sales-onboarding` into `<sales layer>/profile/icp.md`. `sales-scout` reads nothing
else to decide what a lead is: change a line here and the next sweep follows it.

```settings
# 1 segments
industries: software, fintech, logistics
size_min: 20
size_max: 500
size_strict: off
# 2 roles: who buys, who champions, which hires reveal the need
buyer_roles: COO, CTO, Head of Operations, VP Operations
champion_roles: Head of Knowledge, RevOps, Operations Manager
need_roles: knowledge manager, revops, salesforce administrator, data migration
intent_phrases: onboard our slack history, company knowledge base, migrate off confluence
# 3a markets: Name = a regex over a location, a country or a city
market.Iberia: lisbon|porto|portugal|madrid|barcelona|spain
market.DACH: germany|deutschland|berlin|munich|austria|vienna|switzerland|zurich
market.UK: united kingdom|london|manchester|\buk\b
# 3b sources (on / off)
source.linkedin-public: on
source.linkedin-signed-in: off
source.chrome-directories: off
source.registries: on
source.threads: on
# 4 buying signals and their weights
weight.hiring: 3
weight.migration: 3
weight.intent: 3
weight.funding: 2
weight.exec_hire: 2
weight.brain: 2
weight.revival: 3
weight.expansion: 1
weight.event: 1
weight.news: 1
half_life_days: 30
# 5 knock-outs (comma-separated)
competitors:
exclude:
exclude_domains:
exclude_markets:
# 6 the day's target, and the floor nothing below may pass
daily_target: 10
floor: 60
```

## Notes the scout should know

- <a market quirk, a segment to avoid, a lookalike you love>
