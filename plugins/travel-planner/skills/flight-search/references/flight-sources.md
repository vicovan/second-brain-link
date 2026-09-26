# Flight sources — where to look, and the pre-filled links for when a site blocks

Honest limits: these are public sites read through the user's own browser. There is no
partner API, no affiliate agreement and no guaranteed coverage. Metasearch prices are often
stale; the carrier's own site is the fare that is actually sold.

| Site | Use it for | Pre-filled link (dates YYYY-MM-DD) |
|---|---|---|
| Google Flights | the default: the market's shape, carriers, hubs, real prices, "best" vs "cheapest" | `https://www.google.com/travel/flights?q=Flights%20from%20<FROM>%20to%20<TO>%20on%20<DATE>%20oneway` (round trip: `…%20on%20<DATE>%20returning%20<RET>`) |
| Skyscanner | cheap combinations, "whole month" views | `https://www.skyscanner.net/transport/flights/<from>/<to>/<YYMMDD>/` (lowercase IATA) |
| Kayak | a second opinion on the market | `https://www.kayak.com/flights/<FROM>-<TO>/<DATE>` |
| Carrier site | the real fare | search the carrier's own booking page — no stable deep-link format |

## Reading a results page

Google Flights: the list shows each option's times, airline, duration, stops (with layover
airport and length) and price; open an option ("Select flight") to read the flight numbers
and each segment's exact times. The price shown is per traveller unless the header says
otherwise — record which. Expand "Other departing flights" for more than the top picks.

- Record the flight number, the airports (IATA), the local departure and arrival times, the
  cabin, the fare and currency, **the URL, and the time you read it** (`quoted_at`).
- A "self-transfer" or "virtual interline" label on a metasearch result means the site has
  already combined separate tickets — record each ticket as its own fare so `interline.py`
  can judge the connection itself.
- Bags: note whether the fare includes a checked bag. A self-transfer with hand luggage only
  is a much smaller risk; say so when it applies.

## Traps

- Two airports in one city (LHR/LGW, HND/NRT, CDG/ORY, ICN/GMP): a separate-ticket connection
  between them needs an airport transfer — `interline.py` adds 120 minutes and marks it high risk.
- Overnight arrivals shift the date — read the arrival date, not only the time.
- A fare shown in a currency other than `providers.md`'s: record it as shown, do not convert.
