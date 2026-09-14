from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from houston_mvp.advisor import attach_advice
from houston_mvp.data import load_dataset
from houston_mvp.simulation import MODES, simulate_all


class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = load_dataset()
        cls.payload = attach_advice(simulate_all(cls.dataset))
        cls.by_name = {
            scenario["name"]: scenario for scenario in cls.payload["scenarios"]
        }

    def test_scenarios_present(self):
        self.assertEqual(
            set(self.by_name),
            {
                "Baseline",
                "Shuttle",
                "Transit Boost",
                "Heat Safety",
                "Mixed Optimized",
            },
        )

    def test_mode_totals_match_total_visitors(self):
        for scenario in self.payload["scenarios"]:
            modeled_visitors = sum(scenario["mode_totals"][mode] for mode in MODES)
            self.assertAlmostEqual(
                modeled_visitors,
                scenario["kpis"]["total_visitors"],
                delta=len(MODES),
                msg=scenario["name"],
            )

    def test_mixed_optimized_improves_core_risks(self):
        baseline = self.by_name["Baseline"]["kpis"]
        mixed = self.by_name["Mixed Optimized"]["kpis"]

        self.assertLess(mixed["estimated_heat_cases"], baseline["estimated_heat_cases"])
        self.assertLess(mixed["max_route_pressure"], baseline["max_route_pressure"])
        self.assertLess(
            mixed["avg_first_last_mile_gap"], baseline["avg_first_last_mile_gap"]
        )
        self.assertGreater(
            mixed["transit_shuttle_share_pct"],
            baseline["transit_shuttle_share_pct"],
        )

    def test_resource_counts_match_scenario_settings(self):
        for scenario in self.payload["scenarios"]:
            resources_by_type = {"hydration": 0, "cooling": 0, "medical": 0}
            for item in scenario["resources"]:
                resources_by_type[item["resource_type"]] += item["units"]

            settings = scenario["settings"]
            self.assertEqual(resources_by_type["hydration"], settings["hydration_units"])
            self.assertEqual(resources_by_type["cooling"], settings["cooling_units"])
            self.assertEqual(resources_by_type["medical"], settings["medical_units"])

    def test_advisor_is_deterministic_and_actionable(self):
        self.assertIn("recommended_scenario", self.payload["advisor"])
        self.assertEqual(
            self.payload["advisor"]["recommended_scenario"], "Mixed Optimized"
        )
        for scenario in self.payload["scenarios"]:
            self.assertIn("headline", scenario["advisor"])
            self.assertTrue(scenario["advisor"]["actions"])


if __name__ == "__main__":
    unittest.main()

