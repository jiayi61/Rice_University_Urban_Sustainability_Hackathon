# Houston and New York: public-data model integration

The new-event planner uses the same calculation for both cities. There is no
prepared New York result on the landing page. Results are calculated after the
event form is submitted.

## What the public data changes

- Venue geocodes select the correct local facility search and road endpoints.
- Candidate transfer sites come from repository-cached public facilities within
  0.5–6.5 km of the venue. Rail and bus facilities take priority over parking;
  points within 250 m are merged and explicitly private facilities are excluded.
  Unknown access is not approval. These are local transfer candidates, not an
  observed distribution of attendees across the metropolitan region.
- Separate venue-to-site and site-to-venue road paths feed each bus cycle. A
  missing direction is identified as a fallback, not silently verified.
- Cycle minutes = (outbound + return minutes) × event road-time multiplier +
  dwell. The default multiplier 1.30 is an editable assumption.
- Each additional equal-cost bus is assigned to the largest marginal reduction
  in queue-person-hours. For fixed demands and independent fluid queues, the
  queue objective is separable with diminishing gains, so this allocation is
  optimal for each tested fleet size. This does not imply global multimodal or
  traffic-network optimality.
- Demand +25%, service -30%, road time +50%, and combined disruptions hold the
  selected allocation fixed. The original nine sensitivity scenarios remain.
  The road-delay stress affects added shuttle cycles only; existing shared
  service is a separately specified capacity assumption. Use the combined
  scenario to stress that baseline capacity as well.

## Houston introduction

`houston_mvp.data.load_dataset()` overlays valid road snapshots on the original
scenario inputs for shuttle, rideshare and park-and-ride approaches. It changes
road geometry, distance and travel time before scenario calculations. The
homepage and `/api/houston-mvp` use this model. Rail and walking times remain
mode-specific assumptions: driving data is never substituted for transit or
walking data. The `Official survey sites` map layer displays locations only.

The 105 Houston survey points contain no traffic volumes. Demand, passenger
service capacities, shade, accessibility scores, intervention effects and
existing heat-health outputs in the legacy scenario remain unvalidated
assumptions; public road geometry does not validate those outputs.

## Reproduce

```sh
./.venv/bin/python scripts/sync_public_database.py --houston-baseline
./.venv/bin/python scripts/export_houston_model.py
PYTHONPATH=src .venv/bin/python -m pytest -q
./.venv/bin/python scripts/verify_city_models.py
```

The last command forbids external lookup, generates both example PDFs under
`output/pdf/`, and writes `docs/city_model_validation.json`. These are explicit
50,000-attendee / $100,000 test scenarios, not default prepared event results.
Refresh snapshots when they expire. The tests compare small fleet allocations
with exhaustive enumeration, check passenger/fleet conservation, distinguish
outbound and return times, verify budget/delay behavior, reject duplicate or
private sites, and check that road updates affect Houston travel time without
inventing measured capacity. No real-world prediction accuracy is asserted.
