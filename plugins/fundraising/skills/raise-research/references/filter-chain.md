# The filter chain

The founder's `round.md` sets the filters **and their order**. The ledger applies them in that
order and records the first failure as the reason a record is out.

| Filter | Fails when | Passes / unknown / conditional |
|---|---|---|
| `floor` | the cheque's upper bound is below `min_net_cash` | pass when the lower bound clears it; unknown otherwise |
| `geo` | the target invests only in regions outside `geography_ok` | pass on global or an overlap; **conditional** when only US-focused and `relocation: ok` |
| `thesis` | only `off_thesis` terms match | pass on a `thesis_keywords` match; unknown when mixed or silent |
| `access` | never fails | records cold path vs warm-only |
| `entity` | a required entity is not in `entities_ok` | unknown when unstated |
| `exclusions` | any exclusion (and its synonyms) appears | pass otherwise |

Why cheapest-first: money and geography can be judged from a one-line description, so they remove
the most candidates before a single page is fetched.

`unknown` never fails a record — it becomes a question for the pitch form or the plan. A desk
verdict that is wrong is corrected with `ledger.py set-verdict <key> <filter> <value> --why "…"`;
overrides survive every rescreen.

Changing `round.md` and running `ledger.py rescreen` re-tiers the whole universe without fetching
anything — the right move when the founder's constraints change mid-raise.
