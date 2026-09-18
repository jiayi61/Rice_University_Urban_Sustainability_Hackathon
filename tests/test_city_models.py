from itertools import product
from dataclasses import replace
from pathlib import Path

import pytest

from eventflow.screening import simulate_event
from eventflow.site_selection import select_sites
from eventflow.data_repository import DataRepository
from houston_mvp.data import load_dataset, enrich_road_inputs
from houston_mvp.simulation import simulate_all


def scenario(inputs=None, budget=100000):
    zones = [{'zone_id': 'a', 'name': 'A', 'visitors': 10000}, {'zone_id': 'b', 'name': 'B', 'visitors': 20000}]
    routes = {'a': {'minutes': 7, 'return_minutes': 19, 'distance_km': 3, 'geometry': [], 'source': 'test'},
              'b': {'minutes': 30, 'return_minutes': 40, 'distance_km': 20, 'geometry': [], 'source': 'test'}}
    return simulate_event(zones, routes, {}, {'fleet_limit': 6, **(inputs or {})}, budget)


def test_allocation_matches_exhaustive_small_case():
    p = scenario()
    r = p['recommended']
    best = float('inf')
    for allocation in product(range(7), repeat=2):
        if sum(allocation) != r['fleet']:
            continue
        queue = 0
        for i, row in enumerate(r['routes']):
            baseline_rate = p['baseline']['routes'][i]['service_pph']
            rate = baseline_rate + allocation[i] * 45 * .85 * 60 / row['cycle_minutes']
            queue += row['people']**2 / (2*rate)
        best = min(best, queue)
    assert r['queue_person_hours'] == pytest.approx(best, abs=.06)
    assert sum(x['buses'] for x in r['routes']) == r['fleet']
    assert sum(x['people'] for x in r['routes']) == r['cohort']


def test_directional_times_delay_budget_and_fixed_plan_stress():
    p = scenario()
    assert p['recommended']['routes'][0]['cycle_minutes'] == round((7+19)*1.3+15,1)
    assert scenario(budget=0)['recommended']['fleet'] == 0
    assert scenario({'road_delay_factor':2})['recommended']['queue_person_hours'] > p['recommended']['queue_person_hours']
    assert all(x['plan_minutes'] >= p['recommended']['clearance_minutes'] for x in p['stress_tests'])
    assert all(x['plan_minutes'] <= x['baseline_minutes'] for x in p['stress_tests'])


def test_selection_deduplicates_and_rejects_private_or_wrong_city():
    place = {'lat': 40.8, 'lon': -74.0}
    rows = [{'name': 'Parking', 'mode':'parking', 'lat':40.82, 'lon':-74},
            {'name': 'Rail', 'mode':'rail', 'lat':40.8201, 'lon':-74},
            {'name': 'Private', 'mode':'bus', 'lat':40.83, 'lon':-74, 'access':'private'},
            {'name': 'Wrong city', 'mode':'rail', 'lat':29.68, 'lon':-95.4}]
    assert [s['name'] for s in select_sites(rows, place)] == ['Rail']
    assert select_sites(list(reversed(rows)), place) == select_sites(rows, place)


def test_houston_geometry_changes_travel_times_without_inventing_capacity(tmp_path):
    dataset = load_dataset()
    selected = next(r for r in dataset.routes if r.mode == 'shuttle')
    rail = next(r for r in dataset.routes if r.mode == 'rail')
    db = DataRepository(tmp_path)
    key = f'route_{selected.lat1:.4f}_{selected.lon1:.4f}_{selected.lat2:.4f}_{selected.lon2:.4f}'
    db.write(key, {'minutes': 100, 'distance_km': 30, 'geometry': [[selected.lat1,selected.lon1],[selected.lat2,selected.lon2]]}, 'https://example.org', 120, publish=True)
    updated = enrich_road_inputs(dataset,tmp_path)
    changed = next(r for r in updated.routes if r.route_id==selected.route_id)
    assert changed.base_minutes == 130
    assert changed.capacity_per_hour == selected.capacity_per_hour
    assert next(r for r in updated.routes if r.route_id==rail.route_id)==rail
    before, after = simulate_all(dataset), simulate_all(updated)
    assert after['scenarios'][0]['kpis']['avg_travel_minutes'] > before['scenarios'][0]['kpis']['avg_travel_minutes']


def test_city_database_covers_both_directions_without_external_requests():
    from unittest.mock import patch
    from datetime import datetime, timedelta
    import json
    from eventflow.universal import UniversalPlanner
    p = UniversalPlanner(Path(__file__).resolve().parents[1], None)
    index = json.loads((p.root/'data/database/index.json').read_text())
    # Freeze at publication time so a future CI run tests lookup behavior,
    # not the incidental age of these intentionally expiring snapshots.
    recorded = max(datetime.fromisoformat(r['retrieved_at']) for r in index['resources']) + timedelta(seconds=1)
    for city in ('Houston','New York'):
        with patch('eventflow.data_repository.datetime', wraps=datetime) as clock, patch.object(p, '_get_json', side_effect=AssertionError('Unexpected external lookup')) as network:
            clock.now.return_value = recorded
            result=p.plan_from_brief('Concert in '+city,False,{'city_query':city,'attendance':50000})
        network.assert_not_called()
        assert len(result['candidate_sites']) >= 4
        assert all(v['source'].startswith('OpenStreetMap') and v['return_source'].startswith('OpenStreetMap') for v in result['simulation']['recommended']['routes'])
        assert all(result['data_access'][k]['tier']=='repository' for k in result['data_access'] if k.startswith('zone_'))
