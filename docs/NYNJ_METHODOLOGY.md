# NY/NJ methodology and evidence boundary

## Accounting

The reference is the reported July 19, 2026 final (Match 104). The three modelled cohorts sum to 48,392: rail 21,024; Host Committee shuttle 11,168; rideshare 16,200. Attendance is 80,663. Pedestrian counts overlap transport modes and are not added. This is a retrospective planning case, not a forecast issued before the tournament.

## Queue abstraction

For each mode, reference throughput is reported passengers / reported clearance hours. All modelled demand enters at final whistle. Clearance = passengers / throughput; queue-person-hours = passengers × clearance-hours / 2. This is an aggregate fluid queue, not a street simulation or measured individual wait.

Interventions change explicit service-rate or exposure assumptions. Mode shift is limited by additional coach seats. Accessible service is incremental planning capacity, not certified wheelchair spaces. The code records unit arithmetic, costs, proposed owners, approval dependencies and measurement criteria for all seven interventions.

## Decision search

Enumerate every subset of seven actions (128 portfolios). Keep central estimated cost within budget. Balanced score weights queue reduction 45%, clearance reduction 30%, relative heat reduction 15%, and affected-leg emissions reduction 10%. Accessibility blends 55% of that score with 45% accessible-seat target attainment; the target is an assumed 8% of the modelled cohort. Resilience blends 45% balanced score with 55% queue reduction under an assumed 85% rail service-rate loss. Weights are policy choices, not an official score.

The Pareto chart excludes points with no improvement over a cheaper portfolio. High cost estimates can exceed the selected budget; procurement must re-run the choice with quotations. This version does not solve probabilistic budget risk.

## Sensitivity and validation

81 deterministic combinations vary demand ±15%, reference service rate ±15%, intervention effectiveness 50–150%, and relative heat weight ±20%. The selected portfolio stays fixed. These ranges are not statistical confidence intervals; multiplying both baseline and plan by the same heat weight cancels in relative reductions. Absolute heat burden still changes. Other assumptions, including emissions factors and price ranges, are not probabilistically calibrated.

Leave-one-match-out validation estimates median realized throughput from seven matches and predicts the excluded match. Eight held-out cases per mode give MAE 4.1 minutes rail, 29.2 shuttle and 58.6 rideshare. This tests baseline transfer only. The final-match retrospective scenario uses its reported throughput; its fit is not an independent validation. Intervention effectiveness remains unvalidated.

## Data provenance

`data/nynj/observed_source.json` links the agency report and records extraction limitations. `observed_egress.csv` transcribes its table. Public map snapshots preserve URLs, retrieval details and source status. Organizer `data/rice/manifest.json` includes every original file checksum, while `rice_aggregate.json` records complete-shard row counts and filters. The dictionary prohibits real-world inference from its transformed educational sample. POI and UHI positions are aggregated into approximately 5 km cells; visits/spend remain historical market context. No individual-level joins are invented.

No NY/NJ weather station matched the specified station filter. ACS retrieval failed; demographic need is not inferred from an empty response. No FIFA-period NJ TRANSIT GTFS, measured roadway counts, continuous accessible-path audit or causal intervention study is included. Current regular MTA geometry is contextual only.

## Operational validation needed

Obtain a dated operator review, actual cycle and boarding measurements, vendor quotations, rail path approvals, accessible transfer audit, and intervention pilot. Hold out a later event to measure queue and throughput changes. Replace the release-time abstraction with arrival time series before claiming individual waiting-time accuracy.
