# Safety — what this plugin will and will not do

## Money and identity — never, at any level

The agent never types, stores or asks to store:

- a payment card number or CVV
- a passport or national ID number
- a password, or anything into a login form
- a date of birth or passport expiry **unless** the user opted in, in §2 of
  `booking-answers.md` (and even then only into a booking form, which this version never opens)

It never creates an account, never solves a CAPTCHA, and never retries a blocked site more
than once. **Nothing is booked in this version**: every level of `level:` ends at a
pre-filled link the user follows.

## Self-transfer — a feature with a warning label

Separate tickets mean bags are not through-checked, the second carrier owes nothing when the
first is late, a missed connection is paid for twice, and a landside transfer means entering
the country. Three enforcement points, not one warning:

1. `interline.py` **refuses** a separate-ticket connection below the airport's self-transfer
   floor (`references/airports.json` `mct_self`, +120 min for an airport change).
2. Every self-transfer leg carries the risk sentence in the rendered notes.
3. Studio's Map draws self-transfer legs **dashed**.

The planner never decides a visa is unnecessary. A landside transfer into a country the
traveller has not listed in `visa_ok` is flagged "check visa rules".

## Prices

Every price carries `quoted_at` — the moment it was read — and the URL. `itinerary.py`
refuses a price without one, and the renderer withholds any that slips through.

## Where you are — never the device

*Today near me* needs to know where you are. It takes that from, in order: the active trip's stop
whose dates include today; `home_city` in `profile/traveler.md`; what you said today ("I'm in
Porto", stamped for the day only). It never reads a location from the machine, the browser, a photo
or a network — and it never writes one anywhere but your own profile and the day's stamp.

## Today's picks

Nothing is booked or bought; a reservation is a link you follow. An opening time or an event is
shown only with the moment its page was seen (`seen_at`) and the page; a price only with
`quoted_at`. Web picks are marked *web only*; your own places cite their notes. The only thing the
agent remembers from a day is what you tell it: went · loved · not for me.

## The vault

The plugin writes only its own layer (`47-travel/`) and its hidden ledger
(`.plugins/travel-planner/`), keeps its own manifest (`_TRAVEL_GENERATED.json`) so an engine
`--refresh` leaves its notes alone, and never creates a note named like a place.

## Python

Stdlib only, Python 3.9+, no `requirements.txt` — deliberately. Studio can inherit a minimal
`PATH` whose `python3` has no site-packages; a planner that needed a package would fail there
or, worse, degrade silently. Keep it dependency-free.
