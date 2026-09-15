> Legacy prototype documentation. See README.md and NYNJ_METHODOLOGY.md for the current competition case.

# EventFlow v3 universal event methodology

## Event brief pipeline

1. **Interpret** — Extract event name/type, city, venue if supplied, calendar date, time and any explicit attendance.
2. **Resolve** — Select or geocode a plausible venue. A curated global seed makes common cities fast and provides continuity during a public-API outage.
3. **Enrich** — Discover nearby rail stations, bus stations and parking through OpenStreetMap; retrieve historical weather around the event's calendar date; retrieve a reference currency conversion.
4. **Forecast** — Estimate attendance from venue planning capacity and event type, allocate it across visitor catchments and create an ingress/egress time curve.
5. **Route** — Request street-following geometry and free-flow time for each origin-to-venue corridor from OSRM. Cache successful responses.
6. **Plan** — Scale, localize and rank lean, balanced and maximum-resilience intervention portfolios.
7. **Explain** — Return assumptions, confidence, public-source freshness and model limits with the plans.

## No-key operation

The brief parser is algorithmic and does not require an LLM. This is intentional: the application remains runnable in a classroom, judging room or municipal environment without sending the event brief to a paid model. A future LLM adapter can improve ambiguous-language interpretation while retaining the same validated event schema.

## Online sources and fallbacks

| Need | Primary source | Fallback |
|---|---|---|
| Venue/city | OSM Nominatim | Curated major-city venue seed |
| Transit/parking | OSM Overpass | Seed transport lines or labeled empty discovery |
| Road geometry | OSRM | Labeled screening geometry |
| Climate context | Open-Meteo archive | Seasonal planning scenario |
| Currency | Frankfurter reference rate | Labeled static planning-rate assumption |
| Local costs | Transferable 2026 action benchmarks × event scale × city cost factor × FX | Same range, explicitly requiring local quotes |

Public endpoints are queried only after the user submits a brief; successful results are cached. This is not an autocomplete service.

## Interpretation boundaries

- An inferred venue is a recommendation, not confirmation that the artist/team has booked it.
- Attendance is a planning scenario until ticketing or organizer data replaces it.
- OSM infrastructure discovery shows physical facilities; it is not an agency schedule.
- Historical weather describes climate risk, not a forecast for a date more than a few days away.
- Traffic and intervention effects are scenario projections, not live sensor observations.
- Cost outputs are low/mid/high planning ranges, not vendor quotes.
