# EventFlow — Houston to your next event

The product starts with the Houston / NRG Stadium demonstration. A visitor types a new event brief, then opens a prepared New York-region concert scenario. The input is a local demo interaction: it does not call an AI API, search the web, parse custom constraints or generate a new event model.

The prepared concert assumes 50,000 departures at MetLife Stadium in East Rutherford, New Jersey, with historical FIFA mode shares and throughput as reference assumptions. Its date is unspecified. Houston and NY/NJ reuse the decision workflow, not identical calibrated transport models. Houston retains its synthetic prototype data disclosure.

## Run

```sh
python3 start.py --no-browser --port 8000
```

Open http://localhost:8000. No Python dependencies are required for the saved demo or NY/NJ model. Change budget, policy priority and disruption to compare 36 independently computed scenarios. Export the English decision brief from the page. The live model endpoint is `POST /api/nynj/plan`; the interface uses reproducible saved calculations, not a live traffic feed.

## What is real, and what is modelled?

- **Observed public evidence:** NJ TRANSIT's eight-match 2026 after-action report. The final-match model covers 48,392 reported rail, shuttle and rideshare trips, not all spectators. Agency clearance windows are not individual waits.
- **Organizer data:** all 191 compressed shards scanned, plus the original dictionary. Historical transformed samples provide market context and relative heat scenarios, not a FIFA origin–destination matrix.
- **Public geometry:** current regular MTA subway GTFS, geocoded anchors and OSM/OSRM road geometry. These are not historical event schedules or measured road congestion.
- **Assumptions:** incremental service rates, intervention effects, operating costs, voluntary mode shift, accessible-seat targets and emission factors. The interface and source register disclose them.
- **Projections:** exhaustively compare 128 intervention subsets. The $500,000 balanced scenario selects $435,000 of central cost allowances and projects 180 → 132 minutes maximum clearance. Its cost range reaches $600,000, so it is not guaranteed affordable under cost escalation. No realized improvement is claimed.

## Reproduce

```sh
python3 -m unittest discover -s tests -p 'test_nynj.py' -v
python3 scripts/export_nynj_demo.py
```

For full organizer data, authenticate GitHub CLI and follow [the dataset instructions](data/rice/README.md). Aggregation needs pandas; public-source refresh is optional. Source snapshots are versioned so the demo does not require fetching them on launch.

## Competition package

- [Method and limitations](docs/NYNJ_METHODOLOGY.md)
- [Generated decision brief](docs/NYNJ_SUBMISSION.md)
- [English Devpost narrative and three-minute pitch](docs/NYNJ_PITCH.md)
- [Rubric and remaining evidence gaps](docs/SCORING.md)
- [Verification](VERIFICATION.md)
- [Private original-data release](https://github.com/jiayi61/Rice_University_Urban_Sustainability_Hackathon/releases/tag/rice-data-2026-09-14)

Earlier Houston and universal prototypes are retained for reference. Their preset percentages and synthetic readiness scores are not evidence for this NY/NJ submission. Archived documents are explicitly labelled. The Houston-first homepage and event brief are the competition entry point.
