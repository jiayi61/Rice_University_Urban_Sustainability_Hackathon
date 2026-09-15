> Archived pre-NY/NJ prototype document. Not current evidence.

# EventFlow Universal Mobility Planner v3

EventFlow is a reusable decision-support platform for mega-event transportation planning. A user can describe a future event in ordinary language and receive a mapped, costed and ranked mobility plan without uploading data or setting a budget.

Example:

> Give me projections for a Shakira concert in London June 8th 2027

The universal planner interprets the brief, selects a likely venue, estimates attendance, discovers transport infrastructure, routes demand corridors, builds a historical weather normal, converts cost ranges to local currency and generates three intervention portfolios. Every inferred input is exposed in an assumptions panel.

## What changed in v3

- A prominent **Plan any event, any city** brief bar is the primary workflow.
- The deterministic parser works without a paid AI key; an LLM is not required for normal briefs.
- Global connectors use Nominatim for place resolution, Overpass for nearby rail/bus/parking discovery, OSRM for street routes, Open-Meteo for historical climate context and Frankfurter for reference FX.
- Online results are cached under `data/cache/universal/` and every connector has a labeled fallback.
- Venue, city, crowd, routes, map extent, weather, transit points, currency, costs and labels now change with the generated event.
- The example London plan resolves to Wembley Stadium, 74,500 estimated attendees, eight origin catchments and GBP cost ranges.
- Existing Houston templates and the full legacy analytical interface remain available.

## What v2 already added

- A clean, decision-first interface replaces the 13-tab command center. The original interface remains at `/legacy.html`.
- The system generates and ranks **Lean operations**, **Network balance**, and **Maximum resilience** plans automatically. The normal user does not enter a budget or upload a map.
- The map uses OpenStreetMap tiles, 10 cached OSRM street-routed demand corridors, and a compact derivative of the full METRO Houston GTFS feed.
- The GTFS map layer contains 109 representative system routes: 106 bus routes and all three METRORail lines. Direct venue-access routes are emphasized.
- Visitor circles, road pressure, route travel times, heat exposure and headline KPIs change across projection time from T−180 to T+120.
- Each intervention exposes its corridor, units, added capacity, owner, delivery time, dependency, capex, opex, low/mid/high estimate and cost basis.
- All 11 U.S. host cities are compared with the same five-dimension screening formula.
- The Rice University source catalog is bundled under `data/reference/world_cup_source_catalog/` and drives the documented city acquisition strategy.

## Run

No package installation is required for the standalone mode.

```bash
python3 start.py --no-browser
```

Open the local URL printed by the launcher. The primary experience is at `/`; the previous advanced interface is at `/legacy.html`.

FastAPI remains supported:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## New reusable API

- `GET /api/v2/catalog` returns reusable event templates, host-city screening profiles, data policy and sources.
- `POST /api/v2/plan` with `{ "event_id": "houston_wc26" }` generates the full event payload: demand zones, projection timelines, three portfolios, routes, infrastructure, costs, coverage and map layers.
- `POST /api/v3/brief` with `{ "prompt": "Shakira concert in London June 8th 2027", "online": true }` discovers and generates a complete event-specific plan. Set `online` to `false` for deterministic testing or offline fallback mode.

Bundled event templates:

- `houston_wc26`
- `houston_texans`
- `houston_rodeo`
- `houston_concert`

The v3 natural-language endpoint does not require adding a catalog record. Saved catalog templates remain useful for repeatable baselines.

## Data and modeling boundaries

The street map and transit route geometry are real public spatial data. Traffic, demand response and intervention impacts are projections. Cost outputs are 2026-USD planning ranges, not bids. The interface labels this distinction directly.

The Houston spatial snapshot includes:

- OpenStreetMap basemap attribution;
- OSRM street-routed origin-to-venue paths;
- METRO Houston GTFS snapshot dated 2026-09-01;
- official venue-access bus/rail/fare facts;
- FTA vehicle-revenue-hour operating-cost anchors;
- documented production connector targets for TranStar, TxDOT, Census/ACS and weather.

The Rice Box share supplied with the project returned 404 during this build, so no data from that share is represented as ingested.

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 scripts/smoke_test.py
node --check app/static/app.js
```

See `docs/METHODOLOGY_V3.md` for the universal discovery pipeline and `docs/METHODOLOGY_V2.md` for the simulation, score and cost foundations.
