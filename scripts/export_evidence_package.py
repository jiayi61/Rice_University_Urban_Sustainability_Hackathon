#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eventflow.model import EventFlowModel


def main() -> None:
    output_dir = ROOT / "data" / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    model = EventFlowModel(
        ROOT / "data" / "local" / "houston_profile.json",
        ROOT / "data" / "local" / "gtfs_profile.json",
        ROOT / "data" / "local" / "osm_profile.json",
        ROOT / "data" / "local" / "traffic_profile.json",
        ROOT / "data" / "local" / "candidate_profile.json",
        ROOT / "data" / "local" / "equity_profile.json",
    )
    demand = model.demand_calibration()
    audit = model.baseline_audit()
    candidates = model.candidate_recommendations()
    equity = model.equity_report()
    validation = model.validation_report()

    package = {
        "demand_calibration": demand,
        "baseline_audit": audit,
        "candidate_sites": candidates,
        "equity_accessibility": equity,
        "validation": validation,
        "data_status": model.data_status(),
    }
    (output_dir / "eventflow_evidence_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    demand_rows = demand.get("rows", [])
    if demand_rows:
        with (output_dir / "od_demand_calibration.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "zone_id", "zone_name", "low_demand", "central_demand", "high_demand",
                    "uncertainty_pct", "confidence_score", "heat_index", "resource_gap", "transit_access_score",
                ],
            )
            writer.writeheader()
            for row in demand_rows:
                writer.writerow({key: row.get(key) for key in writer.fieldnames})

    site_rows = [site for sites in candidates.get("recommendations", {}).values() for site in sites]
    if site_rows:
        with (output_dir / "candidate_site_rankings.csv").open("w", encoding="utf-8", newline="") as handle:
            fields = [
                "candidate_id", "name", "candidate_type", "readiness_score", "capacity_riders",
                "cost_usd", "accessible", "accessibility_verified", "capacity_verified",
                "official_source", "evidence_level", "source_name", "source_url",
                "nearest_zone_name", "route_distance_miles", "one_way_minutes",
                "estimated_cycle_minutes", "route_source",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in site_rows:
                writer.writerow({key: row.get(key) for key in fields})

    equity_rows = equity.get("rows", [])
    if equity_rows:
        with (output_dir / "equity_zone_screening.csv").open("w", encoding="utf-8", newline="") as handle:
            fields = [
                "zone_id", "zone_name", "demand", "vulnerability_index", "zero_vehicle_share",
                "low_income_share", "disability_share", "svi_percentile", "ada_path_score",
                "source_name", "source_url", "evidence_year",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in equity_rows:
                writer.writerow({key: row.get(key) for key in fields})

    print(f"Evidence package exported to {output_dir}")


if __name__ == "__main__":
    main()
