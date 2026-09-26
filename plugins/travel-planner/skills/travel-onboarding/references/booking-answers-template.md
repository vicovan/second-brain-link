---
type: travel-profile
title: Booking answers
tags: [travel, profile, answers]
owner: <Full Name>
updated: <YYYY-MM-DD>
---

> Answered once, on purpose, so no booking form asks again. Anything not here is asked, never guessed.

# Booking answers

## 0. Autonomy
How far the agent goes toward a booking on its own. The shipped value is the cautious one —
change it deliberately, not by accident.

```
level: research            # research | supervised | autonomous
max-bookings-per-run: 3
max-spend-per-run: 0
```

- **`research`** — plans, prices and pre-filled links. It never opens a checkout. **This is
  the only level with any effect in this version: booking is not built yet.**
- **`supervised`** — (when booking ships) fills guest and passenger details and stops at the
  payment page for you.
- **`autonomous`** — (when booking ships) books without gates, capped by the two limits above.

No level ever types a payment card, CVV, passport or national ID number, or a password;
none creates an account or solves a CAPTCHA; none infers a level from how a request is phrased.

## 1. Names
- Full name exactly as on the passport (for tickets):

## 2. Opt-in only — leave blank unless you want the agent to fill it
Airlines genuinely require these. They are **never inferred**; without them the agent fills
everything else and stops with a clear reason.
- Date of birth:
- Passport expiry (month/year only):

## 3. Programmes and preferences
- Frequent-flyer numbers (programme: number):
- Hotel loyalty (programme: number):
- Travel insurance: I buy my own | offer it | never
- Billing country:
