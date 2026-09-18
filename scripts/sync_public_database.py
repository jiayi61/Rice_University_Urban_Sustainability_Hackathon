#!/usr/bin/env python3
"""Publish bounded public provider responses as reviewable Git snapshots.

No briefs, API keys or generated event plans are published. This command does
not commit or push; runtime API requests only write the ignored local cache.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eventflow.data_repository import TRAFFIC_KEY, TRAFFIC_LAYER, fetch_houston_sites
from eventflow.universal import UniversalPlanner, CITY_SEEDS
from eventflow.site_selection import select_sites, site_origins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--city', action='append', choices=['houston', 'new york'])
    parser.add_argument('--houston-baseline', action='store_true', help='Also fetch road routes for the Houston introduction.')
    args = parser.parse_args()
    planner = UniversalPlanner(ROOT, None)
    outcomes = []

    def publish(payload):
        access = payload.get('_data_access')
        if not access:
            raise ValueError('Cannot publish data without provider provenance.')
        planner.database.write(access['key'], payload, access['source_url'], access['max_age_days'],
                               publish=True, retrieved_at=access['retrieved_at'])
        outcomes.append({'key': access['key'], 'status': 'stored', 'source_url': access['source_url']})

    cities = args.city or ['houston', 'new york']
    if 'houston' in cities:
        try:
            sites = fetch_houston_sites(planner._get_json)
            planner._write_cache(TRAFFIC_KEY, sites, TRAFFIC_LAYER, 90)
            publish(sites)
            print(f"Official Houston survey locations: {len(sites['features'])}")
        except Exception as exc:
            outcomes.append({'key': TRAFFIC_KEY, 'status': 'unavailable', 'reason': type(exc).__name__})

    for city in cities:
        place = deepcopy(CITY_SEEDS[city])
        try:
            hit = planner._nominatim(f"{place['venue']}, {city}")
            if hit:
                publish(hit)
                place.update(lat=float(hit['lat']), lon=float(hit['lon']))
        except Exception as exc:
            outcomes.append({'key': f'geocode_{city}', 'status': 'unavailable', 'reason': type(exc).__name__})
        try:
            transport = planner._transport(place)
            publish(transport)
            facilities = select_sites(transport['stations'], place)
            if facilities:
                place['origins'] = site_origins(facilities)
            print(f"{city}: {len(transport['stations'])} transport facilities")
        except Exception as exc:
            outcomes.append({'key': f'transport_{city}', 'status': 'unavailable', 'reason': type(exc).__name__})
        def fetch_route(row):
            return [planner._osrm((row[2], row[3]), (place['lat'], place['lon'])),
                    planner._osrm((place['lat'], place['lon']), (row[2], row[3]))]
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(fetch_route, row) for row in planner._fallback_origins(place)]
            for future in futures:
                try:
                    for result in future.result():
                        publish(result)
                except Exception as exc:
                    outcomes.append({'key': f'route_{city}', 'status': 'unavailable', 'reason': type(exc).__name__})

    if args.houston_baseline:
        from houston_mvp.data import load_dataset
        dataset = load_dataset()
        endpoints = sorted({(r.lat1, r.lon1, r.lat2, r.lon2) for r in dataset.routes if r.mode in ('shuttle', 'rideshare', 'park')})
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(planner._osrm, (a,b), (c,d)) for a,b,c,d in endpoints]
            for future in futures:
                try:
                    publish(future.result())
                except Exception as exc:
                    outcomes.append({'key': 'houston_baseline_route', 'status': 'unavailable', 'reason': type(exc).__name__})
    directory = ROOT / 'data/database'
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted(planner.database.published.glob('*.json')):
        record = json.loads(path.read_text())
        records.append({k: record[k] for k in ('key', 'source_url', 'retrieved_at', 'max_age_days', 'sha256')} | {'file': 'resources/' + path.name})
    index = {'schema_version': 1, 'catalog_url': 'https://github.com/HoustonSI/WorldCupUSSpatialData101',
             'catalog_path': '../reference/world_cup_source_catalog', 'resources': records, 'last_sync': outcomes}
    (directory / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'stored': len(records), 'unavailable': [r for r in outcomes if r['status'] != 'stored']}, indent=2))
    if not records:
        raise SystemExit('No public resources were saved.')


if __name__ == '__main__':
    main()
