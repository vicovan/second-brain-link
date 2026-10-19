# Search method — how to run a lead sweep for anyone

**What to search for is not here.** Segments, roles, markets, signals, knock-outs, the daily
target and the floor all live in the seller's `profile/icp.md`. This file is the procedure that
turns those into a shortlist, and it is the same procedure for every seller.

If no profile is reachable, **stop and run onboarding**. Never guess an ICP, a market or a role —
a day of outreach built on invented criteria spends the seller's reputation, not just their time.

## 1. Freshness and volume

Sweep what is new since the last run (`scout.py since-seconds`). Deliver only what clears the
floor, up to the target. Widening the *sources* to reach it is expected; widening the *ICP* or
lowering the floor to reach a number is not — a padded list is how a week of messages goes to
companies that were never going to buy.

## 2. Source order — the brain, then the market, then companies, then their own sites

1. **The brain** (`warm_rank.py`): revival deals, warm and dormant-strong decision-makers, intro
   paths. Free, private, and the half no cloud tool can see on day one.
2. **Discovery, per market** (`sources.md`, `regional-sources.md`): hiring signals, funding and
   news, directories, events, registries, intent threads — limited to what is new.
3. **The companies' own sites**: the domain, the team page, the press page, the careers board,
   the contact form. The company's own page wins over any aggregator on every fact.
4. **Lookalikes** (weekly): accounts like the ones that replied or booked.

Then `scout.py merge` collapses the same company seen on several sources into one account and
marks what is new, and `scout.py coverage` decides whether each market was actually searched.

**Never conclude a market is empty from one source.** Global aggregators cover US and EU tech
well and other regions hardly at all. A market with no qualified accounts from fewer than three
sources is a failure to widen, not a result to report.

## 3. A lead is only a lead when there is a way in

Before an account reaches the shortlist it needs a reachable buyer (`lead_score.py` → `reach`):
a brain tie, an intro path, a business address **published on a public page**, the company's own
contact form, or a public profile. A guessed address is recorded as `pattern-unverified` and is
never sent. Unreachable accounts are listed with "find me a way in", never hidden.

## 4. Evidence on every fact

Every signal row carries its `url` and the date it was `seen`. Every buyer added by research
carries the page their role came from (`role_source`). A fact with no source is not a fact.
