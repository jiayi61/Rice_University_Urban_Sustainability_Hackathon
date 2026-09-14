from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eventflow.equity_ingestion import build_equity_profile, scan_equity
from eventflow.gtfs_ingestion import build_gtfs_profile, scan_gtfs
from eventflow.model import EventFlowModel
from eventflow.osm_ingestion import build_osm_profile, scan_osm
from eventflow.traffic_ingestion import build_traffic_profile, scan_traffic_counts


def _demo_model() -> EventFlowModel:
    return EventFlowModel(
        profile_path=Path("/nonexistent/rice.json"),
        gtfs_profile_path=Path("/nonexistent/gtfs.json"),
        osm_profile_path=Path("/nonexistent/osm.json"),
        traffic_profile_path=Path("/nonexistent/traffic.json"),
    )


def test_baseline_has_pressure_metrics():
    model = _demo_model()
    result = model.baseline()
    assert result["metrics"]["max_pressure"] > 0
    assert len(result["edges"]) >= 5
    assert result["time_window"] == "ingress_peak"


def test_intervention_changes_result():
    model = _demo_model()
    baseline = model.baseline()
    scenario = model.simulate(["transit_boost", "bus_only_lane"])
    assert scenario["cost_usd"] > 0
    assert scenario["metrics"]["emissions_kg_index"] < baseline["metrics"]["emissions_kg_index"]


def test_time_windows_and_egress_direction():
    model = _demo_model()
    comparison = model.compare_time_windows(["transit_boost"])
    assert len(comparison["windows"]) == 3
    egress = next(item["scenario"] for item in comparison["windows"] if item["scenario"]["time_window"] == "egress_peak")
    assert egress["flow_direction"] == "outbound"
    assert egress["metrics"]["modeled_visitors"] > model.baseline("pre_match")["metrics"]["modeled_visitors"]


def test_stress_and_sensitivity():
    model = _demo_model()
    stress = model.stress_test(["park_ride_shuttle"], "compound_shock")
    assert stress["stressed_baseline"]["metrics"]["max_pressure"] > stress["normal_baseline"]["metrics"]["max_pressure"]
    sensitivity = model.sensitivity_analysis(["park_ride_shuttle"])
    assert sensitivity["run_count"] == 81
    assert sensitivity["distributions"]["readiness_score"]["min"] <= sensitivity["robustness_score"]


def test_optimizer_respects_budget_and_returns_robustness():
    model = _demo_model()
    result = model.optimize(250000)
    assert result["cost_usd"] <= 250000
    assert "pareto_front" in result
    assert result["robustness"]["run_count"] == 81


def test_unknown_intervention_rejected():
    model = _demo_model()
    try:
        model.simulate(["unknown"])
    except ValueError:
        return
    raise AssertionError("Expected ValueError")


def _write_gzip_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_local_rice_profile_build_and_model_reload(tmp_path):
    from eventflow.local_data import DATASET_DIRS, build_houston_profile, scan_root

    for dirname in DATASET_DIRS.values():
        (tmp_path / dirname).mkdir(parents=True, exist_ok=True)

    _write_gzip_csv(
        tmp_path / DATASET_DIRS["poi"] / "part.csv.gz",
        ["STORE_ID", "CITY", "MARKET", "LATITUDE", "LONGITUDE", "TOP_CATEGORY", "SUB_CATEGORY"],
        [
            {"STORE_ID": "s1", "CITY": "Houston", "MARKET": "Houston", "LATITUDE": "29.759", "LONGITUDE": "-95.368", "TOP_CATEGORY": "Restaurants", "SUB_CATEGORY": "Restaurant"},
            {"STORE_ID": "s2", "CITY": "Houston", "MARKET": "Houston", "LATITUDE": "29.741", "LONGITUDE": "-95.464", "TOP_CATEGORY": "Shopping", "SUB_CATEGORY": "Mall"},
        ],
    )
    _write_gzip_csv(
        tmp_path / DATASET_DIRS["visits"] / "part.csv.gz",
        ["STORE_ID", "CITY", "DAILY_VISITS"],
        [
            {"STORE_ID": "s1", "CITY": "Houston", "DAILY_VISITS": "1000"},
            {"STORE_ID": "s2", "CITY": "Houston", "DAILY_VISITS": "800"},
        ],
    )
    _write_gzip_csv(
        tmp_path / DATASET_DIRS["spend_patterns"] / "part.csv.gz",
        ["CITY", "LATITUDE", "LONGITUDE", "RAW_NUM_CUSTOMERS", "RAW_TOTAL_SPEND"],
        [{"CITY": "Houston", "LATITUDE": "29.759", "LONGITUDE": "-95.368", "RAW_NUM_CUSTOMERS": "500", "RAW_TOTAL_SPEND": "20000"}],
    )
    _write_gzip_csv(
        tmp_path / DATASET_DIRS["daily_spend"] / "part.csv.gz",
        ["CITY", "SPEND", "TRANSACTIONS"],
        [{"CITY": "Houston", "SPEND": "100000", "TRANSACTIONS": "5000"}],
    )
    _write_gzip_csv(
        tmp_path / DATASET_DIRS["weather"] / "part.csv.gz",
        ["CITY", "TEMPERATURE", "HUMIDITY"],
        [{"CITY": "Houston", "TEMPERATURE": "35", "HUMIDITY": "60"}],
    )
    _write_gzip_csv(
        tmp_path / DATASET_DIRS["uhi"] / "part.csv.gz",
        ["CITY", "LATITUDE", "LONGITUDE", "UHI"],
        [{"CITY": "Houston", "LATITUDE": "29.759", "LONGITUDE": "-95.368", "UHI": "2.4"}],
    )

    report = scan_root(tmp_path)
    assert report["ready"]
    output = tmp_path / "houston_profile.json"
    profile = build_houston_profile(tmp_path, output, max_rows_per_file=1000)
    assert profile["mode"] == "rice_sampled"
    model = EventFlowModel(output, tmp_path / "missing_gtfs.json", tmp_path / "missing_osm.json", tmp_path / "missing_traffic.json")
    assert "rice" in model.data_mode
    assert model.data_status()["rice_profile_exists"]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_gtfs_profile_build_and_model_reload(tmp_path):
    feed = tmp_path / "gtfs"
    _write_csv(feed / "agency.txt", ["agency_id", "agency_name"], [{"agency_id": "metro", "agency_name": "Metropolitan Transit Authority of Harris County"}])
    _write_csv(
        feed / "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        [
            {"stop_id": "stadium", "stop_name": "Stadium Park", "stop_lat": "29.6860", "stop_lon": "-95.4105"},
            {"stop_id": "downtown", "stop_name": "Central Station", "stop_lat": "29.7590", "stop_lon": "-95.3680"},
            {"stop_id": "medical", "stop_name": "TMC Transit Center", "stop_lat": "29.7080", "stop_lon": "-95.3970"},
        ],
    )
    _write_csv(feed / "routes.txt", ["route_id", "route_short_name", "route_long_name", "route_type"], [{"route_id": "red", "route_short_name": "Red", "route_long_name": "Red Line", "route_type": "0"}])
    _write_csv(feed / "calendar.txt", ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"], [{"service_id": "daily", "monday": "1", "tuesday": "1", "wednesday": "1", "thursday": "1", "friday": "1", "saturday": "1", "sunday": "1", "start_date": "20260101", "end_date": "20261231"}])
    _write_csv(feed / "trips.txt", ["route_id", "service_id", "trip_id"], [{"route_id": "red", "service_id": "daily", "trip_id": f"t{i}"} for i in range(4)])
    stop_times = []
    for index, minute in enumerate((810, 825, 840, 855)):
        hour, mins = divmod(minute, 60)
        clock = f"{hour:02d}:{mins:02d}:00"
        stop_times.extend([
            {"trip_id": f"t{index}", "arrival_time": clock, "departure_time": clock, "stop_id": "downtown", "stop_sequence": "1"},
            {"trip_id": f"t{index}", "arrival_time": clock, "departure_time": clock, "stop_id": "medical", "stop_sequence": "2"},
            {"trip_id": f"t{index}", "arrival_time": clock, "departure_time": clock, "stop_id": "stadium", "stop_sequence": "3"},
        ])
    _write_csv(feed / "stop_times.txt", ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"], stop_times)

    report = scan_gtfs(feed)
    assert report["ready"]
    profile_path = tmp_path / "gtfs_profile.json"
    profile = build_gtfs_profile(feed, profile_path, event_date="2026-06-14", kickoff_time="15:00")
    assert profile["access"]["stadium"]["access_score"] > 0
    assert "Metropolitan Transit Authority" in profile["attribution"]
    model = EventFlowModel(tmp_path / "missing_rice.json", profile_path, tmp_path / "missing_osm.json", tmp_path / "missing_traffic.json")
    assert "gtfs" in model.data_mode
    assert model.data_status()["transit"]["stadium_access_score"] > 0


def _write_mock_overpass(path: Path):
    nodes = {
        1: (29.7589, -95.3677),
        2: (29.7375, -95.3785),
        3: (29.7078, -95.3975),
        4: (29.6847, -95.4107),
        5: (29.7407, -95.4636),
        6: (29.7160, -95.4445),
        7: (29.9931, -95.3418),
        8: (29.8500, -95.3600),
        9: (29.6454, -95.2789),
        10: (29.6600, -95.3500),
        11: (29.7521, -95.3530),
    }
    elements = [{"type": "node", "id": node_id, "lat": lat, "lon": lon} for node_id, (lat, lon) in nodes.items()]
    elements.extend([
        {"type": "way", "id": 100, "nodes": [1, 2, 3, 4], "tags": {"highway": "primary", "name": "Main Spine", "lanes": "4", "maxspeed": "35 mph"}},
        {"type": "way", "id": 101, "nodes": [5, 6, 3], "tags": {"highway": "primary", "name": "West Spine", "lanes": "4"}},
        {"type": "way", "id": 102, "nodes": [7, 8, 1], "tags": {"highway": "motorway", "name": "Airport Spine", "lanes": "8"}},
        {"type": "way", "id": 103, "nodes": [9, 10, 4], "tags": {"highway": "trunk", "name": "South Spine", "lanes": "6"}},
        {"type": "way", "id": 104, "nodes": [11, 2], "tags": {"highway": "secondary", "name": "EaDo Connector", "lanes": "4"}},
    ])
    path.write_text(json.dumps({"elements": elements}), encoding="utf-8")


def test_osm_network_and_traffic_calibration(tmp_path):
    source = tmp_path / "overpass.json"
    _write_mock_overpass(source)
    report = scan_osm(source)
    assert report["ready"]
    osm_path = tmp_path / "osm_profile.json"
    osm = build_osm_profile(source, osm_path)
    assert osm["edge_count"] >= 10
    assert all(osm["routes"][zone] for zone in ("downtown", "galleria", "medical", "iah", "hobby", "eado"))

    counts = tmp_path / "counts.csv"
    _write_csv(
        counts,
        ["latitude", "longitude", "aadt", "street_name"],
        [
            {"latitude": "29.748", "longitude": "-95.373", "aadt": "42000", "street_name": "Main"},
            {"latitude": "29.728", "longitude": "-95.454", "aadt": "70000", "street_name": "West"},
            {"latitude": "29.920", "longitude": "-95.351", "aadt": "110000", "street_name": "Airport"},
        ],
    )
    scan = scan_traffic_counts(counts)
    assert scan["ready"]
    traffic_path = tmp_path / "traffic_profile.json"
    traffic = build_traffic_profile(counts, osm_path, traffic_path)
    assert traffic["directly_calibrated_edges"] > 0

    model = EventFlowModel(
        tmp_path / "missing_rice.json",
        tmp_path / "missing_gtfs.json",
        osm_path,
        traffic_path,
    )
    assert model.data_mode == "osm+traffic"
    result = model.baseline()
    assert result["network_summary"]["osm_connected"]
    assert result["network_summary"]["traffic_calibrated"]
    assert any(edge["geometry"] for edge in result["edges"])
    assert any("observed" in edge["calibration_source"] for edge in result["edges"])


def test_mode_assignment_sums_to_modeled_visitors():
    model = _demo_model()
    result = model.simulate(["transit_boost", "park_ride_shuttle"], operations={"shuttle_fleet": 12})
    assigned = sum(item["riders"] for item in result["mode_split"].values())
    assert abs(assigned - result["metrics"]["modeled_visitors"]) <= 4
    assert len(result["zone_assignments"]) == len(model.zones)


def test_shuttle_capacity_is_bounded_by_fleet_and_cycle_time():
    model = _demo_model()
    small = model.simulate(
        ["park_ride_shuttle"],
        operations={
            "shuttle_fleet": 1,
            "shuttle_seats": 40,
            "shuttle_cycle_minutes": 60,
            "operating_window_minutes": 60,
            "shuttle_load_factor": 0.8,
        },
    )
    large = model.simulate(
        ["park_ride_shuttle"],
        operations={"shuttle_fleet": 80, "operating_window_minutes": 180},
    )
    small_f = small["operational_feasibility"]["shuttle"]
    large_f = large["operational_feasibility"]["shuttle"]
    assert small_f["capacity_riders"] == 32
    assert small_f["served_riders"] <= small_f["capacity_riders"]
    assert small_f["unmet_riders"] > 0
    assert large_f["served_riders"] > small_f["served_riders"]


def test_validation_report_exposes_evidence_coverage():
    model = _demo_model()
    report = model.validation_report()
    assert 0 <= report["confidence_score"] <= 100
    assert report["coverage"]["origin_zone_count"] == len(model.zones)
    assert report["interpretation"].startswith("The score measures")


def test_demand_calibration_and_audit_are_auditable():
    model = _demo_model()
    calibration = model.demand_calibration()
    assert len(calibration["rows"]) == len(model.zones)
    assert calibration["totals"]["central_modeled_demand"] == round(sum(zone.demand for zone in model.zones))
    assert all(row["low_demand"] < row["central_demand"] < row["high_demand"] for row in calibration["rows"])
    audit = model.baseline_audit()
    assert audit["total"] >= 5
    assert any(check["check"] == "Mode assignment conservation" for check in audit["checks"])


def test_candidate_site_profile_and_capacity_constraint(tmp_path):
    from eventflow.candidate_ingestion import build_candidate_profile, scan_candidates

    source = tmp_path / "candidates.csv"
    _write_csv(
        source,
        ["candidate_id", "name", "candidate_type", "latitude", "longitude", "capacity_riders", "cost_usd", "accessible"],
        [
            {"candidate_id": "pr1", "name": "Small P&R", "candidate_type": "park_ride", "latitude": "29.741", "longitude": "-95.463", "capacity_riders": "120", "cost_usd": "50000", "accessible": "yes"},
            {"candidate_id": "rs1", "name": "Rideshare Site", "candidate_type": "rideshare", "latitude": "29.695", "longitude": "-95.414", "capacity_riders": "200", "cost_usd": "30000", "accessible": "yes"},
        ],
    )
    report = scan_candidates(source)
    assert report["ready"]
    profile_path = tmp_path / "candidate_profile.json"
    profile = build_candidate_profile(source, profile_path)
    assert profile["candidate_count"] == 2
    model = EventFlowModel(
        tmp_path / "missing_rice.json",
        tmp_path / "missing_gtfs.json",
        tmp_path / "missing_osm.json",
        tmp_path / "missing_traffic.json",
        profile_path,
    )
    result = model.simulate(["park_ride_shuttle"], operations={"shuttle_fleet": 80, "operating_window_minutes": 180})
    shuttle = result["operational_feasibility"]["shuttle"]
    assert shuttle["candidate_sites_connected"]
    assert shuttle["capacity_riders"] <= 120
    assert model.data_status()["candidate_profile_exists"]


def test_equity_profile_build_and_scenario_metrics(tmp_path):
    source = tmp_path / "equity.csv"
    rows = []
    for index, zone_id in enumerate(("downtown", "galleria", "medical", "iah", "hobby", "eado"), start=1):
        rows.append({
            "zone_id": zone_id,
            "zone_name": zone_id.title(),
            "population": str(10000 + index * 1000),
            "zero_vehicle_share": str(0.08 + index * 0.025),
            "low_income_share": str(0.12 + index * 0.03),
            "disability_share": str(0.05 + index * 0.012),
            "svi_percentile": str(0.30 + index * 0.08),
            "ada_path_score": str(0.75 - index * 0.045),
        })
    _write_csv(source, list(rows[0]), rows)
    scan = scan_equity(source)
    assert scan["ready"]
    profile_path = tmp_path / "equity_profile.json"
    profile = build_equity_profile(source, profile_path)
    assert profile["zone_count"] == 6
    model = EventFlowModel(
        tmp_path / "missing_rice.json",
        tmp_path / "missing_gtfs.json",
        tmp_path / "missing_osm.json",
        tmp_path / "missing_traffic.json",
        tmp_path / "missing_candidates.json",
        profile_path,
    )
    report = model.equity_report()
    assert report["profile_exists"]
    assert report["zone_count"] == 6
    baseline = model.baseline()
    scenario = model.simulate(["transit_boost", "park_ride_shuttle"])
    assert baseline["equity_metrics"]["profile_connected"]
    assert scenario["equity_metrics"]["vulnerable_noncar_coverage_pct"] > baseline["equity_metrics"]["vulnerable_noncar_coverage_pct"]
    assert "ADA compliance" in scenario["equity_metrics"]["interpretation"]


def test_equity_aware_optimizer_and_constraints(tmp_path):
    profile_path = tmp_path / "equity_profile.json"
    build_equity_profile(ROOT / "data" / "sample" / "mock_equity_profile.csv", profile_path)
    model = EventFlowModel(
        tmp_path / "missing_rice.json",
        tmp_path / "missing_gtfs.json",
        tmp_path / "missing_osm.json",
        tmp_path / "missing_traffic.json",
        tmp_path / "missing_candidates.json",
        profile_path,
    )
    result = model.optimize(
        500000,
        objective_mode="equity_first",
        minimum_equity_coverage_pct=55,
        minimum_accessibility_coverage_pct=17,
    )
    assert result["decision_policy"]["objective_mode"] == "equity_first"
    assert result["equity_metrics"]["vulnerable_noncar_coverage_pct"] >= 55
    assert result["equity_metrics"]["accessible_public_mode_coverage_pct"] >= 17


def test_equity_aware_optimizer_requires_profile():
    model = _demo_model()
    try:
        model.optimize(500000, objective_mode="equity_first")
    except ValueError as exc:
        assert "equity profile" in str(exc).lower()
        return
    raise AssertionError("Expected equity-aware optimization to require a profile")


def test_official_candidate_evidence_is_preserved(tmp_path):
    from eventflow.candidate_ingestion import build_candidate_profile, scan_candidates

    source = ROOT / "data" / "sample" / "official_metro_facility_seed.csv"
    report = scan_candidates(source)
    assert report["ready"]
    profile_path = tmp_path / "official_candidates.json"
    profile = build_candidate_profile(source, profile_path)
    assert profile["candidate_count"] == 4
    assert all(site["official_source"] for site in profile["candidates"])
    assert all(site["accessibility_verified"] for site in profile["candidates"])
    assert all(not site["capacity_verified"] for site in profile["candidates"])
    assert sum(site["capacity_riders"] for site in profile["candidates"]) == 0
    model = EventFlowModel(
        tmp_path / "missing_rice.json",
        tmp_path / "missing_gtfs.json",
        tmp_path / "missing_osm.json",
        tmp_path / "missing_traffic.json",
        profile_path,
        tmp_path / "missing_equity.json",
    )
    scenario = model.simulate(["park_ride_shuttle"], operations={"shuttle_fleet": 80})
    assert scenario["operational_feasibility"]["shuttle"]["capacity_riders"] == 0
    assert scenario["operational_feasibility"]["shuttle"]["served_riders"] == 0


def test_portfolio_explainability_returns_marginal_contributions():
    model = _demo_model()
    report = model.portfolio_explainability(["park_ride_shuttle", "bus_only_lane", "cooling_resources"])
    assert report["portfolio_cost_usd"] > 0
    assert len(report["intervention_contributions"]) == 3
    assert all("marginal_score" in row for row in report["intervention_contributions"])
    assert any(row["owner"] for row in report["intervention_contributions"])
    assert any(item["label"] == "Current portfolio" for item in report["benchmark_portfolios"])


def test_implementation_playbook_is_agency_owned_and_timed():
    model = _demo_model()
    playbook = model.implementation_playbook(["transit_boost", "rideshare_staging"])
    assert playbook["portfolio_lead_time_days"] >= 30
    assert len(playbook["implementation_rows"]) == 2
    assert all(row["owner"] and row["permit_or_approval"] for row in playbook["implementation_rows"])
    assert any(item["phase"] == "Event day" for item in playbook["timeline"])


def test_submission_package_contains_markdown_and_judging_alignment():
    from eventflow.submission import build_submission_package

    model = _demo_model()
    package = build_submission_package(model, budget_usd=350000)
    assert package["project"]["title"] == "EventFlow AI Command Center"
    assert "## Executive Summary" in package["markdown"]
    assert "Feasibility / Implementation" in package["judging_alignment"]
    assert package["recommended_portfolio"]["cost_usd"] <= 350000
