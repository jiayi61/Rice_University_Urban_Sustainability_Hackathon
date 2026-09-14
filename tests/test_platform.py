from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eventflow.platform import MobilityPlatform  # noqa: E402


class MobilityPlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.platform = MobilityPlatform(ROOT)

    def test_catalog_is_reusable(self) -> None:
        catalog = self.platform.catalog()
        self.assertEqual(catalog["default_event_id"], "houston_wc26")
        self.assertGreaterEqual(len(catalog["events"]), 4)
        self.assertEqual(len(catalog["cities"]), 11)

    def test_plans_are_automatic_and_ranked(self) -> None:
        payload = self.platform.plan("houston_wc26")
        self.assertEqual(payload["generated_mode"], "automatic")
        self.assertEqual(payload["recommended_plan_id"], "balanced")
        self.assertEqual(len(payload["plans"]), 3)
        self.assertEqual(sum(zone["visitors"] for zone in payload["zones"]), 68777)
        self.assertLess(payload["plans"][1]["metrics"]["max_pressure"], payload["baseline"]["max_pressure"])

    def test_spatial_layers_are_real_network_derivatives(self) -> None:
        payload = self.platform.plan("houston_wc26")
        self.assertGreaterEqual(payload["transit"]["route_count"], 100)
        self.assertEqual(payload["transit"]["rail_route_count"], 3)
        self.assertTrue(all(len(route["geometry"]) > 2 for route in payload["plans"][1]["routes"]))
        self.assertTrue(all("OSRM" in route["geometry_source"] for route in payload["plans"][1]["routes"]))

    def test_future_event_reuses_pipeline(self) -> None:
        world_cup = self.platform.plan("houston_wc26")
        concert = self.platform.plan("houston_concert")
        self.assertNotEqual(world_cup["event"]["attendance"], concert["event"]["attendance"])
        self.assertEqual(len(world_cup["plans"]), len(concert["plans"]))
        self.assertNotEqual(world_cup["plans"][1]["cost"]["mid"], concert["plans"][1]["cost"]["mid"])

    def test_costs_expose_range_and_basis(self) -> None:
        payload = self.platform.plan("houston_wc26")
        for item in payload["plans"]:
            self.assertLess(item["cost"]["low"], item["cost"]["mid"])
            self.assertLess(item["cost"]["mid"], item["cost"]["high"])
            for action in item["actions"]:
                self.assertIn("basis", action)
                self.assertIn("dependency", action)


if __name__ == "__main__":
    unittest.main()
