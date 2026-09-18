from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch

from eventflow.data_repository import DataRepository, TRAFFIC_KEY, fetch_houston_sites
from eventflow.universal import UniversalPlanner


def test_repository_wins_over_runtime_and_keys_do_not_collide(tmp_path):
    db = DataRepository(tmp_path)
    db.write('geocode_St. A, Houston', {'name': 'published'}, 'https://example.org', 30, publish=True)
    db.write('geocode_St. A, Houston', {'name': 'cache'}, 'https://example.org', 30)
    result = db.read('GEOCODE_St. A, Houston', 30)
    assert result['name'] == 'published'
    assert result['_data_access']['tier'] == 'repository'
    assert db.read('geocode_St A, Houston', 30) is None
    assert db.read('geocode_St. A, Chicago', 30) is None


def test_stale_or_corrupt_snapshot_falls_through(tmp_path):
    db = DataRepository(tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    db.write('transport_a', {'stations': [1]}, 'https://example.org', 30, publish=True, retrieved_at=old)
    db.write('transport_a', {'stations': [2]}, 'https://example.org', 30)
    assert db.read('transport_a', 30)['stations'] == [2]
    path = db.published / db.filename('transport_a')
    path.write_text('{broken')
    assert db.read('transport_a', 30)['_data_access']['tier'] == 'local cache'
    db.write('transport_a', {'stations': [3]}, 'https://example.org', 30, publish=True)
    data = json.loads(path.read_text())
    data['payload']['stations'] = [999]
    path.write_text(json.dumps(data))
    assert db.read('transport_a', 30)['stations'] == [2]


def test_provider_is_only_called_on_miss_then_saved(tmp_path):
    planner = UniversalPlanner(tmp_path, None)
    place = {'lat': 41.1, 'lon': -87.1}
    response = {'elements': [{'lat': 41.12, 'lon': -87.12, 'tags': {'railway': 'station', 'name': 'Test station'}}]}
    with patch.object(planner, '_get_json', return_value=response) as provider:
        first = planner._transport(place)
        second = planner._transport(place)
    assert provider.call_count == 1
    assert first['_data_access']['tier'] == 'external API'
    assert second['_data_access']['tier'] == 'local cache'


def test_offline_plan_uses_repository_coordinates_facilities_and_routes(tmp_path):
    planner = UniversalPlanner(tmp_path, None)
    db = planner.database
    def save(key, value):
        db.write(key, value, 'https://example.org/public-data', 30, publish=True)
    save('geocode_NRG Stadium, houston', {'lat': '29.6847', 'lon': '-95.4107', 'name': 'NRG Stadium',
          'address': {'country': 'United States', 'country_code': 'us'}, 'extratags': {'capacity': '72220'}})
    save('transport_29.6847_-95.4107', {'stations': [{'name': 'Verified station', 'lat': 29.70, 'lon': -95.41, 'mode': 'rail'}], 'source': 'Public stations'})
    save('route_29.7000_-95.4100_29.6847_-95.4107', {'distance_km': 3.1, 'minutes': 11, 'geometry': [[29.7, -95.41], [29.6847, -95.4107]], 'source': 'OSRM'})
    save('route_29.6847_-95.4107_29.7000_-95.4100', {'distance_km': 3.2, 'minutes': 12, 'geometry': [[29.6847, -95.4107], [29.7, -95.41]], 'source': 'OSRM'})
    save(TRAFFIC_KEY, {'features': [{'type': 'Feature'}], 'has_traffic_volumes': False})
    with patch.object(planner, '_get_json', side_effect=AssertionError('Network must not be used')) as network:
        result = planner.plan_from_brief('Concert in Houston', online=False,
            inputs={'city_query': 'Houston, USA', 'venue_query': 'NRG Stadium', 'attendance': 30000})
    network.assert_not_called()
    assert result['zones'][0]['name'] == 'Verified station'
    assert result['simulation']['recommended']['routes'][0]['source'] == 'OSRM'
    assert result['data_access']['zone_1']['tier'] == 'repository'
    assert result['data_access']['venue']['tier'] == 'repository'
    assert result['data_access']['traffic survey sites']['tier'] == 'repository'
    assert result['simulation']['parameters']['baseline_service_pph'] == 12000
    with patch.object(planner, '_get_json', side_effect=AssertionError('Unexpected fetch')) as network:
        inferred = planner.plan_from_brief('Concert in Houston', online=True,
            inputs={'city_query': 'Houston', 'attendance': 30000})
    network.assert_not_called()
    assert inferred['data_access']['transport']['tier'] == 'repository'
    assert inferred['data_access']['zone_1']['tier'] == 'repository'


def test_weather_keys_include_year_and_stale_data_is_not_used_offline(tmp_path):
    planner = UniversalPlanner(tmp_path, None)
    planner.database.write('weather_29.685_-95.411_2027-06-08', {'temperature_c': 30}, 'https://example.org', 120, publish=True)
    place = {'lat': 29.6847, 'lon': -95.4107}
    assert planner._weather(place, '2027-06-08', online=False)['temperature_c'] == 30
    import pytest
    with pytest.raises(LookupError):
        planner._weather(place, '2028-06-08', online=False)


def test_survey_ingestion_filters_geography_and_does_not_invent_counts():
    def feature(lon, lat):
        return {'geometry': {'coordinates': [lon, lat]}, 'properties': {'StationID': 123}}
    response = {'type': 'FeatureCollection', 'features': [feature(-95.41, 29.68), feature(-74, 40.8)]}
    result = fetch_houston_sites(lambda url, timeout: response)
    assert len(result['features']) == 1
    assert result['has_traffic_volumes'] is False


def test_online_plan_repository_hit_does_not_call_external_provider(tmp_path):
    # Same guarantee with online=True; there is no requirement to contact a
    # provider merely because the user has enabled online mode.
    planner = UniversalPlanner(tmp_path, None)
    place = {'lat': 29.6847, 'lon': -95.4107}
    planner.database.write('transport_29.6847_-95.4107', {'stations': [], 'source': 'Public snapshot'},
                           'https://example.org', 30, publish=True)
    with patch.object(planner, '_get_json', side_effect=AssertionError('Unexpected fetch')) as network:
        assert planner._transport(place, online=True)['_data_access']['tier'] == 'repository'
    network.assert_not_called()
