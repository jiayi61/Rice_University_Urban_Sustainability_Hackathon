# EventFlow public-data repository

This versioned JSON database ships with the GitHub repository. `index.json`
lists actual provider snapshots; the organizer's 11-city source directory is
retained at `../reference/world_cup_source_catalog/`. A catalog link is not a
downloaded dataset and is never treated as a successful data lookup.

## Lookup order

1. Matching, fresh snapshot in `data/database/resources/`.
2. Matching, fresh response in `data/cache/resources/` (ignored by Git).
3. Configured external provider, if online requests are enabled.
4. Explicitly labelled assumptions / unavailable data when no source succeeds.

Keys include the query or coordinates; weather also includes the full event
date. Freshness uses the stored UTC retrieval time, even after cloning the repo.
Limits: places and road routes 120 days, transport facilities 30 days, survey
locations 90 days, historical weather 120 days, exchange rates 7 days.
Snapshots are checksummed; invalid, corrupted or expired entries are skipped.
These limits are cache policies, not guarantees of operational validity.

`POST /api/v3/brief` follows this order with or without an OpenAI key. OpenAI
extracts city/venue/date from free text; Python chooses and reads data sources
after resolving those inputs. Structured city/venue fields bypass AI parsing.
Offline mode still reads valid repository data and local cache.

## Refresh / publish

From the repository root:

```sh
./.venv/bin/python scripts/sync_public_database.py
# Or only Houston:
./.venv/bin/python scripts/sync_public_database.py --city houston
```

The sync fetches official Houston survey locations and publishes fresh/cached
public Nominatim, Overpass and OSRM responses for Houston and New York where
available. Valid existing responses retain their original retrieval timestamps;
expired ones are refreshed. Failed sources are recorded in `index.json`.
Review the resulting `data/database/` diff and source terms before committing.
Runtime event requests never push to GitHub or publish user briefs, reports or
keys. Public geometry retains the original provider attribution (including OSM
contributors and ODbL for OSM-derived data); linked datasets retain their own
terms, separately from the organizer catalog's CC0 metadata license.

## Limits and evidence

Houston's `Major Thoroughfare ADT` layer contains survey **locations**. It has
no measured volume or capacity field. It appears as `traffic_context` and source
evidence; it must not calibrate traffic or passenger service rates. Transport
facilities can inform proposed shuttle origins; demand shares and operating
capacity still require validated event inputs. Saved road paths influence
distance and travel times but do not establish bus access permission.

Response `data_access` identifies each resource as `repository`, `local cache`,
`external API`, or `assumption / unavailable`. The result page and PDF use the
same `data_freshness` summary. This changes the new-event `/api/v3/brief` flow;
the historical Houston demonstration is still labelled synthetic.

New cities can use the existing place/transport/routing providers and cache
their responses. Additional city-specific official services require explicit
connectors; arbitrary portal links are not automatically executed or scraped.
