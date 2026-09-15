# EventFlow — New York / New Jersey

A Track 1 competition prototype that turns reported stadium egress into a budgeted, stress-tested action portfolio. The venue is MetLife Stadium in East Rutherford, New Jersey. New York Penn and Secaucus are transfer context.

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

Earlier Houston and universal prototypes are retained for reference. Their preset percentages and synthetic readiness scores are not evidence for this NY/NJ submission. Archived documents are explicitly labelled. The NY/NJ homepage is the competition entry point.
