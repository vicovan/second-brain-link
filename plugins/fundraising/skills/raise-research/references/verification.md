# Verification — the stamps, and what a subagent returns

## Stamps

| Stamp | Means | May appear in |
|---|---|---|
| ✅ | read on the target's **own** site or page, on the date in `at` | everything |
| 3P | third-party only — a directory, a database, a press piece | the plan, flagged; never quoted in an application |
| 📋 | desk-screened from a list's one-line description — no page read | screening tables only |
| ⚠ | unverified, conflicting, or a deadline whose year is not on the page | the plan, as a question |

Claims merge by rank (✅ > 3P > 📋 > ⚠), then recency. An import can never downgrade a ✅.

## Rules learned the hard way

- **A list is a lead, never a source.** Circulated lists are wrong often enough — dead domains,
  wrong cheque sizes, an omitted US-only gate, a crypto accelerator under a generic name — that a
  row is worth nothing until the target's own page says the same thing.
- **Posts carry no year.** A deadline is ⚠ until `year_confirmed: true` from the program's page.
- **Net cash.** A program's cash claim is `{"gross": …, "fee": …, "contingent": …, "net": …}`.
  The floor uses `net` = gross − fee; contingent follow-ons ("potential up to …") are not counted.
- **Perks are not cash.** Credits and in-kind "value" never count toward the floor.
- **Exclusions are checked on the program's own page** — an affiliation (a token side letter, a
  chain's foundation as a partner) is often absent from the post that circulated it.
- **Unfetchable is an answer.** A site that blocks automated fetch is recorded as ⚠ with that note —
  not retried more than once, not scraped through the browser.

## Fields

`cheque` · `cash` (programs) · `stage` · `geography` · `thesis` · `cold_path` · `contact_email` ·
`entity_required` · `solo_ok` · `deadline` (+`year_confirmed`) · `status_open` · `cohort` ·
`in_person` · `fee` · `portfolio_signal` (a comparable they backed) · `notes`.

## What a verification subagent returns

```json
{"key": "example-fund",
 "claims": {
   "cheque":     {"v": "$250K–$750K first cheque", "stamp": "✅", "src": "https://example.vc/faq", "at": "2026-01-15"},
   "geography":  {"v": "US and Europe", "stamp": "✅", "src": "https://example.vc/faq", "at": "2026-01-15"},
   "thesis":     {"v": "developer tools, data infrastructure", "stamp": "✅", "src": "https://example.vc", "at": "2026-01-15"},
   "cold_path":  {"v": "pitch form", "stamp": "✅", "src": "https://example.vc/pitch", "at": "2026-01-15"}},
 "people": [{"name": "A. Partner", "role": "partner", "why": "leads infra deals"}],
 "notes": "no public email; form only"}
```

A program adds:

```json
"deadline": {"v": "2026-01-15", "stamp": "✅", "src": "https://example.org/apply", "at": "2026-01-15", "year_confirmed": true},
"cash":     {"v": {"gross": 100000, "fee": 0, "contingent": 0, "net": 100000}, "stamp": "✅", "src": "https://example.org/terms"}
```
