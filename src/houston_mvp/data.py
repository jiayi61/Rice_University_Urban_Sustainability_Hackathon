from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import MODES, Dataset, ResourceCandidate, Route, Scenario, Zone


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "houston_nrg"
CONFIG_DIR = ROOT / "configs"


def _float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def _int(row: dict[str, str], key: str) -> int:
    return int(float(row[key]))


def _bool(row: dict[str, str], key: str) -> bool:
    return row[key].strip().lower() in {"1", "true", "yes", "y"}


def load_zones(path: Path = DATA_DIR / "zones.csv") -> list[Zone]:
    zones: list[Zone] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            shares = {mode: _float(row, f"{mode}_share") for mode in MODES}
            total = sum(shares.values())
            if not 0.98 <= total <= 1.02:
                raise ValueError(f"Mode shares for {row['zone_id']} sum to {total:.3f}")
            zones.append(
                Zone(
                    zone_id=row["zone_id"],
                    name=row["name"],
                    kind=row["kind"],
                    lat=_float(row, "lat"),
                    lon=_float(row, "lon"),
                    visitors=_int(row, "visitors"),
                    peak_share=_float(row, "peak_share"),
                    vulnerability=_float(row, "vulnerability"),
                    mode_shares=shares,
                    rail_eligible=_bool(row, "rail_eligible"),
                    shuttle_eligible=_bool(row, "shuttle_eligible"),
                    notes=row.get("notes", ""),
                )
            )
    return zones


def load_routes(path: Path = DATA_DIR / "routes.csv") -> list[Route]:
    routes: list[Route] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            routes.append(
                Route(
                    route_id=row["route_id"],
                    zone_id=row["zone_id"],
                    corridor_id=row["corridor_id"],
                    name=row["name"],
                    mode=row["mode"],
                    lat1=_float(row, "lat1"),
                    lon1=_float(row, "lon1"),
                    lat2=_float(row, "lat2"),
                    lon2=_float(row, "lon2"),
                    distance_km=_float(row, "distance_km"),
                    base_minutes=_float(row, "base_minutes"),
                    capacity_per_hour=_float(row, "capacity_per_hour"),
                    shade_index=_float(row, "shade_index"),
                    ada_score=_float(row, "ada_score"),
                    gap_m=_float(row, "gap_m"),
                )
            )
    return routes


def load_resource_candidates(
    path: Path = DATA_DIR / "resource_candidates.csv",
) -> list[ResourceCandidate]:
    candidates: list[ResourceCandidate] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            candidates.append(
                ResourceCandidate(
                    candidate_id=row["candidate_id"],
                    name=row["name"],
                    lat=_float(row, "lat"),
                    lon=_float(row, "lon"),
                    category=row["category"],
                    base_priority=_float(row, "base_priority"),
                )
            )
    return candidates


def load_scenarios(path: Path = CONFIG_DIR / "scenarios.json") -> list[Scenario]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    scenarios: list[Scenario] = []
    for item in raw["scenarios"]:
        values: dict[str, Any] = dict(item)
        scenarios.append(Scenario(**values))
    return scenarios


def load_dataset() -> Dataset:
    dataset = Dataset(
        zones=load_zones(),
        routes=load_routes(),
        candidates=load_resource_candidates(),
        scenarios=load_scenarios(),
    )
    _validate_routes(dataset)
    return dataset


def _validate_routes(dataset: Dataset) -> None:
    routes_by_zone_mode = {(route.zone_id, route.mode) for route in dataset.routes}
    for zone in dataset.zones:
        for mode, share in zone.mode_shares.items():
            if share > 0 and (zone.zone_id, mode) not in routes_by_zone_mode:
                raise ValueError(f"Missing {mode} route for zone {zone.zone_id}")
