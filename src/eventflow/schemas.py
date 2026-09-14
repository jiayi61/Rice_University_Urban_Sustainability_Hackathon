from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Zone:
    zone_id: str
    name: str
    lat: float
    lon: float
    demand: float
    car_share: float
    heat_index: float
    resource_gap: float


@dataclass(frozen=True)
class Edge:
    edge_id: str
    source: str
    target: str
    name: str
    distance_miles: float
    freeflow_minutes: float
    baseline_vehicles: float
    capacity_vehicles: float
    heat_index: float
    highway: str = ""
    geometry: Tuple[Tuple[float, float], ...] = ()
    calibration_source: str = "planning assumption"


@dataclass(frozen=True)
class Intervention:
    intervention_id: str
    name: str
    cost_usd: float
    description: str
    effects: Dict[str, float]
    target_edges: List[str]
    target_zones: List[str]
    owner: str = "City mobility lead"
    lead_time_days: int = 30
    implementation_difficulty: int = 3
    permit_or_approval: str = "Event operations approval"
    reversible: bool = True
    dependencies: Tuple[str, ...] = ()
    verification_metric: str = "Operational performance"
