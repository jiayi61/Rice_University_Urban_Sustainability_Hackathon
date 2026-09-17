import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from eventflow.universal import UniversalPlanner
from eventflow.brief_api import extract_brief
from eventflow.screening import simulate_event


class LivePlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.planner = UniversalPlanner(Path(self.temp.name), None)
        self.env = patch.dict(os.environ, {'OPENAI_API_KEY': ''})
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_plan(self, **inputs):
        return self.planner.plan_from_brief('Concert in London June 8th 2027', False, inputs)

    def test_conservation_budget_and_queue(self):
        s = self.run_plan(attendance=50000, budget_usd=50000)['simulation']
        b, p = s['baseline'], s['recommended']
        self.assertEqual(b['cohort'], 20000)
        self.assertEqual(sum(r['people'] for r in p['routes']), 20000)
        self.assertEqual(sum(r['buses'] for r in p['routes']), p['fleet'])
        self.assertLessEqual(p['cost_usd'], 50000)
        self.assertLess(p['queue_person_hours'], b['queue_person_hours'])
        self.assertEqual(b['clearance_minutes'], 100)
        self.assertEqual(p['timeline'][-1]['remaining'], 0)

    def test_zero_budget_and_fleet(self):
        for inputs in ({'budget_usd': 0}, {'fleet_limit': 0}):
            s = self.run_plan(**inputs)['simulation']
            self.assertEqual(s['recommended'], s['baseline'])

    def test_demand_and_capacity_change_outputs(self):
        a = self.run_plan(attendance=50000)['simulation']['baseline']['clearance_minutes']
        b = self.run_plan(attendance=100000)['simulation']['baseline']['clearance_minutes']
        c = self.run_plan(attendance=50000, baseline_service_pph=24000)['simulation']['baseline']['clearance_minutes']
        self.assertEqual(b, 2 * a)
        self.assertEqual(c, a / 2)

    def test_missing_city_never_defaults_to_london(self):
        with self.assertRaises(ValueError):
            self.planner.plan_from_brief('Please plan a concert', False)

    def test_invalid_inputs(self):
        for inputs in ({'attendance': -1}, {'attendance': float('nan')}, {'budget_usd': -1}, {'baseline_service_pph': 0}, {'attendance': 'a'}, {'date': '2027-02-30'}):
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                self.run_plan(**inputs)

    def test_unresolved_explicit_venue_is_error(self):
        with patch.object(self.planner, '_nominatim', return_value=None), self.assertRaises(ValueError):
            self.planner.plan_from_brief('Concert at nonexistent stadium in London June 8th 2027', True)

    def test_new_city_uses_provider_coordinates(self):
        hit = {'lat': '41.8623', 'lon': '-87.6167', 'name': 'Soldier Field', 'address': {'country': 'USA', 'country_code': 'us'}}
        with patch.object(self.planner, '_nominatim', return_value=hit), patch.object(self.planner, '_transport', return_value={'stations': [], 'source': 'test'}), patch.object(self.planner, '_osrm', side_effect=TimeoutError):
            p = self.planner.plan_from_brief('Concert in Chicago', True, {'city_query': 'Chicago', 'venue_query': 'Soldier Field', 'attendance': 30000})
        self.assertEqual(p['venue']['lat'], 41.8623)
        self.assertEqual(p['simulation']['baseline']['cohort'], 12000)
        self.assertTrue(all('screening' in r['source'] for r in p['simulation']['recommended']['routes']))
        self.assertNotIn('plans', p)

    def test_api_extraction_is_server_only(self):
        parsed = {'title':'Concert','city_query':'Chicago','venue_query':'Soldier Field','date':None,'start_time':None,'attendance':30000,'budget_usd':100000,'event_type':'stadium_concert'}
        response = MagicMock()
        response.read.return_value = json.dumps({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(parsed)}]}]}).encode()
        response.__enter__.return_value = response
        with patch.dict(os.environ, {'OPENAI_API_KEY':'unit-test-secret'}), patch('eventflow.brief_api.urlopen', return_value=response) as call:
            self.assertEqual(extract_brief('在芝加哥举办演唱会'), parsed)
        body = json.loads(call.call_args.args[0].data)
        self.assertFalse(body['store'])
        self.assertNotIn('unit-test-secret', json.dumps(body))


if __name__ == '__main__':
    unittest.main()
