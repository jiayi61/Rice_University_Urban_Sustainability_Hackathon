# Organizer dataset — private release storage

All 192 original files (8,469,554,277 bytes), including the dictionary workbook, are stored without modification in the [private data release](https://github.com/jiayi61/Rice_University_Urban_Sustainability_Hackathon/releases/tag/rice-data-2026-09-14).

`manifest.json` maps each attachment to its original relative path, byte count and SHA-256. `upload_verification.json` records verification against GitHub's remote digest for every file. The six data families contain 191 compressed CSV shards; the remaining file is the organizer dictionary.

Authenticate GitHub CLI with repository access, then run:

```sh
python3 scripts/download_rice_data.py
python3 scripts/download_rice_data.py --verify-only
python3 scripts/build_nynj_rice.py --help
```

Downloads resume by skipping already verified files. Conflicting local files are preserved. Raw files are ignored by Git, while their reproducible manifest and derived NY/NJ package are versioned.

## Data meaning

The dictionary states that these are transformed educational samples with noise and location perturbation. They cannot establish real-world city conditions. Do not republish original records. NY/NJ aggregation scans every shard: market filters for visits and spending, a disclosed geographic window for POI/UHI, and exact local station identifiers for weather. No local weather station matched. Historical activity is context, not FIFA visitor origins. UHI is a relative index, not degrees or measured health harm.
