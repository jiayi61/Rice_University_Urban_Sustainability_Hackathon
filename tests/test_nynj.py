import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eventflow.nynj import NYNJEngine, MODES


class NYNJTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = NYNJEngine(ROOT)
        cls.snapshots = json.loads((ROOT / 'app/static/competition-scenarios.json').read_text())

    def test_observed_reference_and_conservation(self):
        base = self.engine.simulate()
        self.assertEqual(base['cohort'], 48392)
        self.assertEqual(base['max_clearance_minutes'], 180)
        plan = self.engine.simulate(['shuttle', 'accessible', 'bus_priority'])
        self.assertAlmostEqual(sum(plan['demand'].values()), base['cohort'])
        self.assertLessEqual(plan['shifted_riders'], 20 * 50 * .85 * 2 * 60 / 48 + 8 * 24 * .8 * 2 * 60 / 48 + 1)
        for mode in MODES:
            self.assertGreaterEqual(plan['demand'][mode], 0)
            values = [row[mode] for row in plan['timeline']]
            self.assertEqual(values, sorted(values, reverse=True))

    def test_zero_budget_and_invalid_input(self):
        plan = self.engine.plan(0)
        self.assertEqual(plan['recommended']['ids'], [])
        self.assertEqual(plan['gains']['queue_pct'], 0)
        for bad in [-1, float('nan'), float('inf'), 2000001]:
            with self.assertRaises(ValueError):
                self.engine.plan(bad)

    def test_snapshots_reproduce_and_respect_budget(self):
        self.assertEqual(len(self.snapshots), 36)
        outcomes = set()
        for key, saved in self.snapshots.items():
            b, priority, stress = key.split(':')
            current = self.engine.plan(int(b), priority, stress, scale=saved['inputs']['demand_scale'])
            self.assertEqual(saved['recommended'], current['recommended'], key)
            r = current['recommended']
            self.assertLessEqual(r['cost'], int(b))
            self.assertLessEqual(r['cost_low'], r['cost'])
            self.assertLessEqual(r['cost'], r['cost_high'])
            self.assertEqual(current['sensitivity']['runs'], 81)
            for metric, bounds in current['sensitivity']['ranges'].items():
                self.assertLessEqual(bounds['min'], current['gains'][metric] + .1)
                self.assertGreaterEqual(bounds['max'], current['gains'][metric] - .1)
            outcomes.add(tuple(r['ids']))
        self.assertGreater(len(outcomes), 3)

    def test_holdout_does_not_train_on_itself(self):
        before = self.engine.rates(exclude=104)
        original = self.engine.observed[-1]['rail_passengers']
        try:
            self.engine.observed[-1]['rail_passengers'] = 99999999
            self.assertEqual(before, self.engine.rates(exclude=104))
        finally:
            self.engine.observed[-1]['rail_passengers'] = original
        self.assertEqual(len(self.engine.validate()['cases']), 24)

    def test_raw_manifest_unique_and_complete(self):
        m = json.loads((ROOT / 'data/rice/manifest.json').read_text())
        self.assertEqual(len(m['files']), 192)
        self.assertEqual(len({f['asset'] for f in m['files']}), 192)
        self.assertEqual(sum(f['bytes'] for f in m['files']), 8469554277)


if __name__ == '__main__':
    unittest.main()
