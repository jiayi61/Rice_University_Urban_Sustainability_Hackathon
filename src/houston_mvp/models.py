from dataclasses import dataclass, field
from typing import Any


MODES = ("rail", "shuttle", "rideshare", "walk", "park")


@dataclass(frozen=True)
class Zone:
    zone_id: str
    name: str
    kind: str
    lat: float
    lon: float
    visitors: int
    peak_share: float
    vulnerability: float
    mode_shares: dict[str, float]
    rail_eligible: bool
    shuttle_eligible: bool
    notes: str


@dataclass(frozen=True)
class Route:
    route_id: str
    zone_id: str
    corridor_id: str
    name: str
    mode: str
    lat1: float
    lon1: float
    lat2: float
    lon2: float
    distance_km: float
    base_minutes: float
    capacity_per_hour: float
    shade_index: float
    ada_score: float
    gap_m: float
    geometry: list | None = None
    route_source: str = 'Synthetic mode-specific planning assumption'
    retrieved_at: str | None = None


@dataclass(frozen=True)
class ResourceCandidate:
    candidate_id: str
    name: str
    lat: float
    lon: float
    category: str
    base_priority: float


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    rail_capacity_multiplier: float
    shuttle_capacity_multiplier: float
    rideshare_capacity_multiplier: float
    park_capacity_multiplier: float
    walk_capacity_multiplier: float
    peak_smoothing: float
    temperature_f: float
    humidity_pct: float
    shade_bonus: float
    hydration_units: int
    cooling_units: int
    medical_units: int
    mode_shifts: list[dict[str, Any]]


@dataclass(frozen=True)
class Dataset:
    zones: list[Zone]
    routes: list[Route]
    candidates: list[ResourceCandidate]
    scenarios: list[Scenario]
    evidence: dict = field(default_factory=dict)
