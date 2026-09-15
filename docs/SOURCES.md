> Legacy prototype documentation. See README.md and NYNJ_METHODOLOGY.md for the current competition case.

# Public Data Sources

## Rice World Cup Hack Data

The provided POI, visits, spend, weather and urban-heat datasets are anonymized and perturbed for education, research and hackathon use. EventFlow treats sampled values as planning proxies rather than precise operational forecasts.

## Houston METRO

Official sources:

- Developer portal and static GTFS: https://api-portal.ridemetro.org/
- Access by car / Park & Ride information: https://www.ridemetro.org/riding-metro/accessing-metro/by-car
- Transit facility addresses: https://www.ridemetro.org/riding-metro/transit-facility-addresses
- Accessibility: https://www.ridemetro.org/riding-metro/accessibility

`official_metro_facility_seed.csv` uses official facility locations and source links. It intentionally leaves capacity at zero unless a separately verifiable capacity field is supplied. Agency accessibility statements support system-level evidence only; route-level sidewalks, crossings, curb ramps and temporary event operations still require field review.

## CDC / ATSDR Social Vulnerability Index

- SVI data and documentation: https://www.atsdr.cdc.gov/place-health/php/svi/svi-data-documentation-download.html

SVI is suitable for area-level planning screening. EventFlow combines it with zero-vehicle, low-income and disability shares at the configured origin-zone level. Aggregation choices and data vintage must be recorded in the evidence package.

## U.S. Census ACS

- ACS data: https://www.census.gov/programs-surveys/acs/data.html
- Census API: https://api.census.gov/data.html

Potential variables include population, household vehicle availability, poverty/income and disability characteristics. A production profile should spatially aggregate census geographies to EventFlow origin zones.

## OpenStreetMap and Overpass

- OpenStreetMap: https://www.openstreetmap.org/
- Overpass API: https://wiki.openstreetmap.org/wiki/Overpass_API
- Overpass QL: https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL

OSM-derived outputs retain `© OpenStreetMap contributors` attribution.

## Houston Traffic Counts

Houston Public Works GeoHub:

- Major Thoroughfare ADT: https://geohub.houstontx.gov/datasets/traffic-counts-major-thoroughfare-adt
- Local Street ADT: https://geohub.houstontx.gov/datasets/traffic-counts-local-street-adt
- Special Counts: https://geohub.houstontx.gov/datasets/traffic-counts-special
- Turning Movement Counts: https://geohub.houstontx.gov/datasets/traffic-counts-turning-movement-1

TxDOT:

- Traffic count maps: https://www.txdot.gov/data-maps/traffic-count-maps.html
- STARS II: https://www.txdot.gov/data-maps/traffic-count-maps/stars.html

EventFlow exposes its daily-volume-to-event-hour assumptions instead of presenting them as observed match-day flow.

## GTFS Specification

- https://gtfs.org/documentation/schedule/reference/
