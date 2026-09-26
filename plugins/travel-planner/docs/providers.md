# Providers — honest coverage

The planner reads public travel sites through the user's own browser (the Claude in Chrome
extension). There are **no partner APIs, no affiliate agreements and no guaranteed coverage**.

| Stage | Default sites | Expect |
|---|---|---|
| Flights | Google Flights, Skyscanner, Kayak, then carrier sites | Metasearch often works; Skyscanner defends hard against automation |
| Stays | Booking.com, Agoda, Airbnb | Frequent bot checks; the pre-filled link is the common outcome |
| Ground | national rail, Sixt, Europcar, Hertz | Varies by operator |
| Food / tours | Google Maps, Tripadvisor, GetYourGuide, Viator | Usually readable |

When a site blocks: the agent stops on it, says which, and hands over a pre-filled search
link — the degraded mode, offered as such. Users choose sites in `profile/providers.md`.

Codex has no browser tooling: on that packaging every stage above is links only.
