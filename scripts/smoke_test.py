#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    def request(path: str, payload: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(base + path, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())

    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "start.py"), "--port", str(port), "--no-browser"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(60):
            try:
                if request("/api/health")["status"] == "ok":
                    break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("Server did not become ready.")

        with urlopen(base + "/", timeout=30) as response:
            index_html = response.read().decode()
        with urlopen(base + "/app.js", timeout=30) as response:
            app_js = response.read().decode()
        with urlopen(base + "/styles.css", timeout=30) as response:
            styles_css = response.read().decode()
        platform_catalog = request("/api/v2/catalog")
        platform_plan = request("/api/v2/plan", {"event_id": "houston_wc26"})
        future_plan = request("/api/v2/plan", {"event_id": "houston_concert"})
        universal_plan = request("/api/v3/brief", {"prompt": "Give me projections for a Shakira concert in London June 8th 2027", "online": False})

        osm_source = str((ROOT / "data" / "sample" / "mock_overpass_houston.json").resolve())
        traffic_source = str((ROOT / "data" / "sample" / "mock_houston_traffic_counts.csv").resolve())
        candidate_source = str((ROOT / "data" / "sample" / "mock_candidate_sites.csv").resolve())
        equity_source = str((ROOT / "data" / "sample" / "mock_equity_profile.csv").resolve())
        osm_scan = request("/api/osm/scan", {"source": osm_source})
        osm_build = request("/api/osm/build", {"source": osm_source})
        traffic_scan = request("/api/traffic/scan", {"source": traffic_source})
        traffic_build = request(
            "/api/traffic/build",
            {"source": traffic_source, "peak_hour_factor": 0.09, "directional_factor": 0.55, "max_snap_miles": 1.25},
        )
        candidate_scan = request("/api/candidates/scan", {"source": candidate_source})
        candidate_build = request("/api/candidates/build", {"source": candidate_source})
        equity_scan = request("/api/equity/scan", {"source": equity_source})
        equity_build = request("/api/equity/build", {"source": equity_source})

        catalog = request("/api/catalog")
        operations = request("/api/operations")
        validation = request("/api/validation")
        demand_calibration = request("/api/demand-calibration")
        audit = request("/api/audit")
        candidates = request("/api/candidates/status")
        equity = request("/api/equity/status")
        data_status = request("/api/data/status")
        baseline = request("/api/baseline")
        scenario = request("/api/simulate", {"interventions": ["transit_boost", "park_ride_shuttle", "bus_only_lane"], "time_window": "egress_peak", "operations": {"shuttle_fleet": 12, "transit_extra_capacity": 5000}})
        windows = request("/api/time-windows", {"interventions": ["transit_boost"]})
        stress = request("/api/stress", {"interventions": ["park_ride_shuttle"], "time_window": "ingress_peak", "stressor_id": "attendance_surge"})
        sensitivity = request("/api/sensitivity", {"interventions": ["park_ride_shuttle"], "time_window": "ingress_peak"})
        optimized = request("/api/advisor", {"budget_usd": 500000, "required": [], "excluded": [], "time_window": "ingress_peak", "objective_mode": "equity_first", "minimum_equity_coverage_pct": 55, "minimum_accessibility_coverage_pct": 17})
        selected = optimized["optimization"]["selected_interventions"]
        explanation = request("/api/explain", {"interventions": selected, "time_window": "ingress_peak", "objective_mode": "equity_first"})
        implementation = request("/api/implementation", {"interventions": selected})
        submission = request("/api/submission", {"budget_usd": 500000, "required": [], "excluded": [], "time_window": "ingress_peak", "objective_mode": "equity_first", "minimum_equity_coverage_pct": 55, "minimum_accessibility_coverage_pct": 17})

        assert osm_scan["ready"]
        assert "EventFlow — Mobility Readiness" in index_html
        assert "buildMapLayers" in app_js
        assert "PLAN ANY EVENT, ANY CITY" in index_html
        assert "/api/v3/brief" in app_js
        assert ".planner-grid" in styles_css
        assert len(platform_catalog["events"]) >= 4
        assert len(platform_catalog["cities"]) == 11
        assert platform_plan["recommended_plan_id"] == "balanced"
        assert platform_plan["transit"]["route_count"] >= 100
        assert all("OSRM" in row["geometry_source"] for row in platform_plan["plans"][1]["routes"])
        assert future_plan["event"]["attendance"] != platform_plan["event"]["attendance"]
        assert universal_plan["venue"]["name"] == "Wembley Stadium"
        assert universal_plan["currency"]["code"] == "GBP"
        assert universal_plan["event"]["date"] == "2027-06-08"
        assert len(universal_plan["plans"]) == 3
        assert osm_build["status"]["osm_profile_exists"]
        assert traffic_scan["ready"]
        assert traffic_build["status"]["traffic_profile_exists"]
        assert candidate_scan["ready"]
        assert candidate_build["status"]["candidate_profile_exists"]
        assert equity_scan["ready"]
        assert equity_build["status"]["equity_profile_exists"]
        assert len(catalog["time_windows"]) == 3
        assert operations["defaults"]["shuttle_fleet"] > 0
        assert validation["confidence_score"] >= 0
        assert len(demand_calibration["rows"]) == 6
        assert audit["total"] >= 5
        assert candidates["profile_exists"]
        assert equity["profile_exists"] and equity["zone_count"] == 6
        assert "osm" in data_status["mode"] and "traffic" in data_status["mode"]
        assert baseline["metrics"]["max_pressure"] > 0
        assert baseline["network_summary"]["osm_connected"]
        assert scenario["flow_direction"] == "outbound"
        assert "mode_split" in scenario
        assert scenario["operational_feasibility"]["shuttle"]["capacity_riders"] > 0
        assert len(windows["windows"]) == 3
        assert stress["stressor_id"] == "attendance_surge"
        assert sensitivity["run_count"] == 81
        assert "pareto_front" in optimized["optimization"]
        assert optimized["action_plan"]["title"]
        assert optimized["optimization"]["decision_policy"]["objective_mode"] == "equity_first"
        assert optimized["optimization"]["equity_metrics"]["vulnerable_noncar_coverage_pct"] >= 55
        assert len(explanation["intervention_contributions"]) == len(selected)
        assert implementation["portfolio_lead_time_days"] > 0
        assert "## Executive Summary" in submission["markdown"]
        assert submission["implementation_playbook"]["implementation_rows"]
        print("PASS: v3 natural-language planner, v2 catalog planner and all legacy v0.9 analytics are working.")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
