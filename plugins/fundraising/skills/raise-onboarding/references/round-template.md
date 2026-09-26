# round.md — template

Copy the block below into `46-fundraising/profile/round.md` and replace the example values. The
frontmatter is read by `founder_profile.py`; keep keys and list syntax exactly as shown. The worked example
is a fictional payments-infrastructure founder, not a real person.

```markdown
---
type: fundraising-profile
title: Round
ask: 1500000
currency: EUR
instrument: SAFE
min_net_cash: 150000
geography_ok: [global, europe]
relocation: no
entity_now: pt-lda
entities_ok: [pt-lda, us-delaware]
cofounder: has
exclusions: [crypto]
thesis_keywords: [payments, fintech infrastructure, api, b2b, embedded finance, developer]
off_thesis: [consumer, health, climate, proptech, hardware]
filter_order: [floor, geo, thesis, access, entity, exclusions]
max_research_agents: 3
followup_days: 7
---

# The round

- Raising a seed on a SAFE; the lead writes at least the minimum above.
- Will not relocate; a US entity is acceptable if a lead requires it.
- Decisions still open: the valuation cap (founder decision, the plan lists it).
```

Notes:
- `min_net_cash` is **net**: a program that pays 50K and charges a 35K fee is a 15K cheque.
- Region tags the screen understands: global, us, europe, cee, nordics, mena, israel, anz, asia, latam.
- `relocation: ok` makes a US-only fund *conditional* ("only after relocating") instead of *out*.
