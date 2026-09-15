# Verification — 2026-09-14

- All 192 private release assets match manifest byte sizes and GitHub SHA-256 digests; total 8,469,554,277 bytes. See data/rice/upload_verification.json.
- Complete organizer scan: 191 compressed CSV shards across six data families. No row cap. NY/NJ weather matching returned zero rows and is disclosed.
- Five NY/NJ regression tests passed: cohort conservation; zero/invalid budgets; all 36 snapshots reproduce and stay within central-cost budgets; holdout exclusion; raw manifest completeness. Each saved scenario has 81 sensitivity runs.
- Browser check: homepage loads evidence, map, portfolio and charts. Changing $500,000/normal to $250,000/rail disruption changes projected maximum clearance from 180→132 to 400→354 minutes. No browser console errors observed in this interaction.
- JavaScript syntax checked. Additional existing regression results are recorded below when run.

These are implementation checks, not external validation of intervention effectiveness. Hosted production deployment and a recorded pitch are separate deliverables and must not be inferred from a local preview.

Existing unittest discovery: 15 tests passed, including the five NY/NJ checks. Python syntax compilation passed for the changed server, model and download script.
