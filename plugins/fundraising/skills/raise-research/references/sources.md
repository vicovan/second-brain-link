# Sources — where targets come from, and what not to retry

## Good inputs
- Lists the founder hands over: CSV exports, pasted posts and newsletters, a deck's "investors we
  like" slide.
- `95-goals/fundraising.md` in the brain (written by the engine's analyze step): connections whose
  titles or companies indicate they invest — warm paths, and funds to add.
- `15-organizations/` notes for funds the founder already knows.
- The target's own site: team page, FAQ, "for founders"/"pitch" page, portfolio page.
- Program pages: the apply page, the FAQ, the terms page.

## Known-unfetchable
- Shared Airtable / Notion views (JavaScript apps) — ask for a CSV export.
- Login-walled databases — not used, by design.
- Sites that return 403 to automated fetch — record ⚠ "blocked to fetch", do not retry more than once.

## Never
- Paid databases, scraping behind a login, LinkedIn automation, guessing an email address pattern.
