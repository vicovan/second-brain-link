# answers.md — template

`level:` is read from the frontmatter. **The shipped default is supervised** — the founder changes it,
never the agent.

```markdown
---
type: fundraising-profile
title: Settled answers
level: supervised
max_submits_per_run: 5
---

# §0 Autonomy

- `supervised` — three gates: pick the targets, approve the answers, submit.
- `autonomous` — no gates; the agent submits after lint and DOM verification, up to the cap.
  Accounts, fees, videos, missing facts and red lints still stop that one application.

# §1 Settled answers (reused on every form)

| Question | Answer |
|---|---|
| Company name | Example Payments |
| Website | https://example.com |
| Deck URL | https://example.com/deck.pdf |
| Location (company) | Lisbon, Portugal |
| Founders full-time? | Yes, both |
| Incorporated? | Yes — Portuguese Lda |
| Raised so far | None |
| Founder video | (record per program — never reuse across different briefs) |
| Demo / product link | https://example.com/demo |
```
