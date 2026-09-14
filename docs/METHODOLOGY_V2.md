# EventFlow v2 methodology

## Product objective

EventFlow moves a city from baseline conditions to a small set of implementable mobility plans. It predicts where event visitors originate, how demand changes through time, which roads and modes carry that demand, where first/last-mile access fails, and which coordinated investments best improve access, resilience, emissions, traffic and heat safety.

The primary design rule is **minimum user work**. EventFlow resolves the event and venue from a reusable catalog, loads the relevant spatial layers, applies cost anchors, generates portfolios and opens on a recommended plan. The user compares decisions rather than assembling inputs.

## Reusable event pipeline

1. **Event resolution** — city, venue, event type, date/time, attendance and weather scenario.
2. **Automatic source selection** — local portal registry, OpenStreetMap, road router, agency GTFS/GTFS-RT, traffic feeds, counts, Census/ACS and weather.
3. **Demand forecast** — total attendance is distributed across hotel, fan-zone, airport, employment/visitor and intercept-parking origins.
4. **Temporal profile** — each zone and route receives an ingress/egress projection from T−180 through T+120.
5. **Network assignment** — origin demand is tied to street-routed corridors and eligible rail, bus, shuttle, rideshare, park-and-ride and walk access.
6. **Gap detection** — first-mile and last-mile distance, mode eligibility, capacity and heat exposure are tracked by origin.
7. **Portfolio generation** — three portfolios are generated automatically: lowest cost, recommended balance, and maximum resilience.
8. **Stress and ranking** — congestion, travel time, coverage, private vehicle avoidance, emissions, heat exposure, equity and robustness are reported together.

## Projection-time map

“Projection time” is a model clock, not a live sensor claim. At each time step:

- visitor-circle radius changes with the number of people currently in motion;
- traffic-line width and color change with modeled flow/capacity pressure;
- route tooltips update travel time, pressure and speed as a percentage of free flow;
- heat-radius overlays change with exposed demand;
- dashboard KPIs and the moving chart cursor remain synchronized.

A production connector can replace or blend the projected route state with TranStar minute-level speeds, incidents, closures and flood-risk points. The v2 interface reports that connector as documented but unauthenticated.

## Map layers

- OpenStreetMap basemap
- projected road pressure
- visitor-demand origins
- full METRORail system
- 106 representative METRO bus route shapes
- recommended event shuttles
- park-and-ride intercepts
- first/last-mile gap buffers
- heat exposure

The transit derivative retains one representative GTFS shape for each route to control browser payload and rendering cost. It is a comprehensive route-level overview, not a stop-by-stop trip planner.

## Cost model

Public FTA vehicle-revenue-hour values anchor bus, commuter-bus and light-rail operations. Temporary infrastructure, staffing, enforcement and program delivery remain planning allowances. Each action therefore reports:

- quantity and operating unit;
- capex and event opex;
- low, midpoint and high range;
- added passenger capacity;
- implementation owner and timeline;
- dependencies; and
- the exact basis used.

The portfolio adds an explicit 18% program-delivery and contingency allowance. The system deliberately avoids false dollar-level precision where procurement quotes do not exist.

## Cross-city resilience

The same screening formula is applied to all 11 U.S. host cities:

- 29% transit access
- 19% road redundancy
- 19% last-mile access
- 14% climate resilience
- 19% data maturity

These are policy weights and screening inputs, not an official FIFA ranking. Houston is the deep case. A defensible production comparison requires the same agency-level acquisition and calibration pipeline for every city.

## Current limitations

- Projected traffic is not live traffic.
- Intervention effects are scenario elasticities, not outputs of a calibrated regional travel-demand model.
- Cost ranges are planning estimates, not procurement bids.
- Only Houston has bundled detailed GTFS and street-routed event corridors.
- The source catalog indicates where to acquire comparable data; catalog inclusion does not mean every linked dataset has already been ingested.
