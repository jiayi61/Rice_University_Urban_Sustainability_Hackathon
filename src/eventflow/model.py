from __future__ import annotations

import itertools
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .candidate_ingestion import load_candidate_profile
from .equity_ingestion import load_equity_profile
from .local_data import load_profile
from .osm_ingestion import load_osm_profile
from .traffic_ingestion import load_traffic_profile
from .sample_data import load_demo_edges, load_demo_zones, load_interventions, load_routes
from .schemas import Edge, Intervention, Zone


TIME_WINDOWS = {
    "pre_match": {
        "label": "Pre-match build-up",
        "description": "Distributed arrivals 1–3 hours before kickoff.",
        "demand_multiplier": 0.58,
        "baseline_multiplier": 0.95,
        "car_share_multiplier": 1.00,
        "heat_multiplier": 0.98,
        "direction": "inbound",
    },
    "ingress_peak": {
        "label": "Ingress peak",
        "description": "Highest arrival pressure in the final hour before kickoff.",
        "demand_multiplier": 1.00,
        "baseline_multiplier": 1.00,
        "car_share_multiplier": 1.00,
        "heat_multiplier": 1.00,
        "direction": "inbound",
    },
    "egress_peak": {
        "label": "Post-match egress",
        "description": "Compressed outbound demand after the match ends.",
        "demand_multiplier": 1.14,
        "baseline_multiplier": 0.88,
        "car_share_multiplier": 1.06,
        "heat_multiplier": 0.94,
        "direction": "outbound",
    },
}

STRESSORS = {
    "attendance_surge": {
        "label": "+25% attendance / fan-zone surge",
        "demand_multiplier": 1.25,
        "capacity_multiplier": 1.0,
        "car_share_multiplier": 1.0,
        "heat_multiplier": 1.0,
        "edge_capacity_multipliers": {},
    },
    "transit_disruption": {
        "label": "Rail disruption and mode shift to cars",
        "demand_multiplier": 1.0,
        "capacity_multiplier": 1.0,
        "car_share_multiplier": 1.18,
        "heat_multiplier": 1.0,
        "edge_capacity_multipliers": {"d2": 0.55, "d3": 0.78},
    },
    "corridor_incident": {
        "label": "Critical road corridor incident",
        "demand_multiplier": 1.0,
        "capacity_multiplier": 1.0,
        "car_share_multiplier": 1.0,
        "heat_multiplier": 1.0,
        "edge_capacity_multipliers": {"g2": 0.28},
    },
    "heat_wave": {
        "label": "Extreme heat day",
        "demand_multiplier": 1.0,
        "capacity_multiplier": 1.0,
        "car_share_multiplier": 1.0,
        "heat_multiplier": 1.10,
        "edge_capacity_multipliers": {},
    },
    "compound_shock": {
        "label": "Compound surge + disruption + heat",
        "demand_multiplier": 1.20,
        "capacity_multiplier": 0.92,
        "car_share_multiplier": 1.12,
        "heat_multiplier": 1.08,
        "edge_capacity_multipliers": {"d2": 0.72, "g2": 0.70},
    },
}

PRESETS = {
    "transit_first": ["park_ride_shuttle", "transit_boost", "bus_only_lane"],
    "traffic_control": ["vehicle_restriction", "rideshare_staging", "pedestrian_guidance"],
    "heat_safe": ["cooling_resources", "pedestrian_guidance", "transit_boost"],
    "balanced": ["park_ride_shuttle", "bus_only_lane", "rideshare_staging", "cooling_resources"],
}


DEFAULT_OPERATIONS = {
    "shuttle_fleet": 24.0,
    "shuttle_seats": 42.0,
    "shuttle_cycle_minutes": 55.0,
    "operating_window_minutes": 150.0,
    "shuttle_load_factor": 0.85,
    "transit_extra_capacity": 7000.0,
    "rideshare_staging_capacity": 3500.0,
}

OPERATION_LIMITS = {
    "shuttle_fleet": (0.0, 100.0),
    "shuttle_seats": (10.0, 100.0),
    "shuttle_cycle_minutes": (15.0, 180.0),
    "operating_window_minutes": (30.0, 360.0),
    "shuttle_load_factor": (0.40, 1.00),
    "transit_extra_capacity": (0.0, 30000.0),
    "rideshare_staging_capacity": (0.0, 20000.0),
}

OPERATION_LABELS = {
    "shuttle_fleet": "Shuttle fleet",
    "shuttle_seats": "Seats per shuttle",
    "shuttle_cycle_minutes": "Round-trip cycle time",
    "operating_window_minutes": "Operating window",
    "shuttle_load_factor": "Target load factor",
    "transit_extra_capacity": "Extra transit passenger capacity",
    "rideshare_staging_capacity": "Managed rideshare passenger capacity",
}


class EventFlowModel:
    """Transparent mobility stress-test model with time windows and robustness analysis."""

    def __init__(
        self,
        profile_path: str | Path | None = None,
        gtfs_profile_path: str | Path | None = None,
        osm_profile_path: str | Path | None = None,
        traffic_profile_path: str | Path | None = None,
        candidate_profile_path: str | Path | None = None,
        equity_profile_path: str | Path | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        self.profile_path = Path(profile_path) if profile_path else root / "data" / "local" / "houston_profile.json"
        self.gtfs_profile_path = (
            Path(gtfs_profile_path) if gtfs_profile_path else root / "data" / "local" / "gtfs_profile.json"
        )
        self.osm_profile_path = (
            Path(osm_profile_path) if osm_profile_path else root / "data" / "local" / "osm_profile.json"
        )
        self.traffic_profile_path = (
            Path(traffic_profile_path) if traffic_profile_path else root / "data" / "local" / "traffic_profile.json"
        )
        if candidate_profile_path is not None:
            self.candidate_profile_path = Path(candidate_profile_path)
        elif any(value is not None for value in (profile_path, gtfs_profile_path, osm_profile_path, traffic_profile_path)):
            anchor = Path(traffic_profile_path or osm_profile_path or gtfs_profile_path or profile_path)  # type: ignore[arg-type]
            self.candidate_profile_path = anchor.with_name("candidate_profile.json")
        else:
            self.candidate_profile_path = root / "data" / "local" / "candidate_profile.json"
        if equity_profile_path is not None:
            self.equity_profile_path = Path(equity_profile_path)
        elif any(value is not None for value in (profile_path, gtfs_profile_path, osm_profile_path, traffic_profile_path, candidate_profile_path)):
            anchor = Path(candidate_profile_path or traffic_profile_path or osm_profile_path or gtfs_profile_path or profile_path)  # type: ignore[arg-type]
            self.equity_profile_path = anchor.with_name("equity_profile.json")
        else:
            self.equity_profile_path = root / "data" / "local" / "equity_profile.json"
        self.routes = load_routes()
        self.interventions: list[Intervention] = load_interventions()
        self.intervention_map = {item.intervention_id: item for item in self.interventions}
        self.data_mode = "synthetic_demo"
        self.data_metadata: dict = {}
        self.zones: list[Zone] = []
        self.edges: list[Edge] = []
        self.gtfs_profile: dict | None = None
        self.osm_profile: dict | None = None
        self.traffic_profile: dict | None = None
        self.candidate_profile: dict | None = None
        self.candidate_sites: list[dict] = []
        self.equity_profile: dict | None = None
        self.equity_by_zone: dict[str, dict] = {}
        self.rice_profile: dict | None = None
        self.network_nodes: dict[str, dict[str, float]] = {}
        self.target_groups: dict[str, list[str]] = {}
        self.zone_transit_scores: dict[str, float] = {}
        self.stadium_transit_score = 0.0
        self.reload_data()

    @staticmethod
    def _load_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def reload_data(self) -> None:
        demo_zones = load_demo_zones()
        demo_edges = load_demo_edges()
        rice_profile = load_profile(self.profile_path)
        gtfs_profile = self._load_json(self.gtfs_profile_path)
        osm_profile = load_osm_profile(self.osm_profile_path)
        traffic_profile = load_traffic_profile(self.traffic_profile_path)
        candidate_profile = load_candidate_profile(self.candidate_profile_path)
        equity_profile = load_equity_profile(self.equity_profile_path)

        profile_zones = {
            row.get("zone_id"): row
            for row in (rice_profile or {}).get("zones", [])
            if row.get("zone_id")
        }
        zones: list[Zone] = []
        for zone in demo_zones:
            row = profile_zones.get(zone.zone_id, {})
            zones.append(
                Zone(
                    zone.zone_id,
                    zone.name,
                    float(row.get("lat", zone.lat)),
                    float(row.get("lon", zone.lon)),
                    float(row.get("demand", zone.demand)),
                    zone.car_share,
                    float(row.get("heat_index", zone.heat_index)),
                    float(row.get("resource_gap", zone.resource_gap)),
                )
            )

        zone_heat = {zone.zone_id: zone.heat_index for zone in zones}
        overall_heat = sum(zone_heat.values()) / max(1, len(zone_heat))
        traffic_calibration = (traffic_profile or {}).get("edge_calibration", {})
        edges: list[Edge] = []

        if osm_profile:
            for row in osm_profile.get("edges", []):
                edge_id = str(row.get("edge_id"))
                calibration = traffic_calibration.get(edge_id, {})
                geometry = tuple(
                    (float(point[0]), float(point[1]))
                    for point in (row.get("geometry") or [])
                    if isinstance(point, (list, tuple)) and len(point) >= 2
                )
                if geometry:
                    midpoint_lat = sum(point[0] for point in geometry) / len(geometry)
                    midpoint_lon = sum(point[1] for point in geometry) / len(geometry)
                    nearest_zone = min(
                        zones,
                        key=lambda zone: (zone.lat - midpoint_lat) ** 2 + (zone.lon - midpoint_lon) ** 2,
                    )
                    heat_index = nearest_zone.heat_index
                else:
                    heat_index = overall_heat
                edges.append(
                    Edge(
                        edge_id=edge_id,
                        source=str(row.get("source")),
                        target=str(row.get("target")),
                        name=str(row.get("name") or edge_id),
                        distance_miles=float(row.get("distance_miles", 0.1)),
                        freeflow_minutes=float(row.get("freeflow_minutes", 1.0)),
                        baseline_vehicles=float(calibration.get("baseline_vehicles", row.get("baseline_vehicles", 0.0))),
                        capacity_vehicles=float(row.get("capacity_vehicles", 1.0)),
                        heat_index=float(heat_index),
                        highway=str(row.get("highway", "")),
                        geometry=geometry,
                        calibration_source=str(calibration.get("calibration_source", row.get("calibration_source", "highway-class assumption"))),
                    )
                )
            self.routes = {
                str(zone_id): {str(edge_id): float(share) for edge_id, share in route.items()}
                for zone_id, route in (osm_profile.get("routes") or {}).items()
            }
            for zone in zones:
                self.routes.setdefault(zone.zone_id, {})
            self.network_nodes = {
                str(node_id): {"lat": float(node["lat"]), "lon": float(node["lon"])}
                for node_id, node in (osm_profile.get("nodes") or {}).items()
                if isinstance(node, dict) and "lat" in node and "lon" in node
            }
            self.target_groups = {
                str(group): [str(edge_id) for edge_id in edge_ids]
                for group, edge_ids in (osm_profile.get("target_groups") or {}).items()
            }
        else:
            self.routes = load_routes()
            self.network_nodes = {}
            self.target_groups = {}
            for edge in demo_edges:
                source_heat = zone_heat.get(edge.source, overall_heat)
                target_heat = zone_heat.get(
                    edge.target,
                    overall_heat + (2.0 if "stadium" in edge.target else 0.0),
                )
                edges.append(
                    Edge(
                        edge.edge_id,
                        edge.source,
                        edge.target,
                        edge.name,
                        edge.distance_miles,
                        edge.freeflow_minutes,
                        edge.baseline_vehicles,
                        edge.capacity_vehicles,
                        round((source_heat + target_heat) / 2, 1),
                    )
                )

        self.zones = zones
        self.edges = edges
        self.gtfs_profile = gtfs_profile
        self.osm_profile = osm_profile
        self.traffic_profile = traffic_profile
        self.candidate_profile = candidate_profile
        self.candidate_sites = list((candidate_profile or {}).get("candidates", []))
        self.equity_profile = equity_profile
        self.equity_by_zone = {str(row.get("zone_id")): row for row in (equity_profile or {}).get("zones", []) if row.get("zone_id")}
        self.rice_profile = rice_profile
        access = (gtfs_profile or {}).get("access", {})
        self.zone_transit_scores = {
            zone.zone_id: float(access.get(zone.zone_id, {}).get("access_score", 0.0))
            for zone in zones
        }
        self.stadium_transit_score = float(access.get("stadium", {}).get("access_score", 0.0))

        modes: list[str] = []
        if rice_profile:
            modes.append("rice")
        if gtfs_profile:
            modes.append("gtfs")
        if osm_profile:
            modes.append("osm")
        if traffic_profile:
            modes.append("traffic")
        if candidate_profile:
            modes.append("sites")
        if equity_profile:
            modes.append("equity")
        self.data_mode = "+".join(modes) if modes else "synthetic_demo"
        self.data_metadata = {
            "rice": {
                "profile_path": str(self.profile_path),
                "profile_exists": self.profile_path.exists(),
                "built_at": (rice_profile or {}).get("built_at"),
                "root": (rice_profile or {}).get("root"),
                "settings": (rice_profile or {}).get("settings", {}),
                "warnings": (rice_profile or {}).get("warnings", []),
                "disclaimer": (rice_profile or {}).get("disclaimer"),
            },
            "gtfs": {
                "profile_path": str(self.gtfs_profile_path),
                "profile_exists": self.gtfs_profile_path.exists(),
                "built_at": (gtfs_profile or {}).get("built_at"),
                "source": (gtfs_profile or {}).get("source"),
                "agency_names": (gtfs_profile or {}).get("agency_names", []),
                "event_date": (gtfs_profile or {}).get("event_date"),
                "kickoff_time": (gtfs_profile or {}).get("kickoff_time"),
                "attribution": (gtfs_profile or {}).get("attribution"),
                "disclaimer": (gtfs_profile or {}).get("disclaimer"),
            },
            "osm": {
                "profile_path": str(self.osm_profile_path),
                "profile_exists": self.osm_profile_path.exists(),
                "built_at": (osm_profile or {}).get("built_at"),
                "source": (osm_profile or {}).get("source"),
                "node_count": (osm_profile or {}).get("node_count", 0),
                "edge_count": (osm_profile or {}).get("edge_count", 0),
                "warnings": (osm_profile or {}).get("warnings", []),
                "attribution": (osm_profile or {}).get("attribution"),
                "disclaimer": (osm_profile or {}).get("disclaimer"),
            },
            "traffic": {
                "profile_path": str(self.traffic_profile_path),
                "profile_exists": self.traffic_profile_path.exists(),
                "built_at": (traffic_profile or {}).get("built_at"),
                "source": (traffic_profile or {}).get("source"),
                "directly_calibrated_edges": (traffic_profile or {}).get("directly_calibrated_edges", 0),
                "class_inferred_edges": (traffic_profile or {}).get("class_inferred_edges", 0),
                "settings": (traffic_profile or {}).get("settings", {}),
                "disclaimer": (traffic_profile or {}).get("disclaimer"),
            },
            "candidates": {
                "profile_path": str(self.candidate_profile_path),
                "profile_exists": self.candidate_profile_path.exists(),
                "built_at": (candidate_profile or {}).get("built_at"),
                "source": (candidate_profile or {}).get("source"),
                "candidate_count": (candidate_profile or {}).get("candidate_count", 0),
                "type_summary": (candidate_profile or {}).get("type_summary", {}),
                "official_source_count": sum(bool(site.get("official_source")) for site in (candidate_profile or {}).get("candidates", [])),
                "verified_capacity_count": sum(bool(site.get("capacity_verified")) for site in (candidate_profile or {}).get("candidates", [])),
                "verified_accessibility_count": sum(bool(site.get("accessibility_verified")) for site in (candidate_profile or {}).get("candidates", [])),
                "warnings": (candidate_profile or {}).get("warnings", []),
                "disclaimer": (candidate_profile or {}).get("disclaimer"),
            },
            "equity": {
                "profile_path": str(self.equity_profile_path),
                "profile_exists": self.equity_profile_path.exists(),
                "built_at": (equity_profile or {}).get("built_at"),
                "source": (equity_profile or {}).get("source"),
                "zone_count": (equity_profile or {}).get("zone_count", 0),
                "warnings": (equity_profile or {}).get("warnings", []),
                "method": (equity_profile or {}).get("method", {}),
                "disclaimer": (equity_profile or {}).get("disclaimer"),
            },
        }

    def data_status(self) -> dict:
        return {
            "mode": self.data_mode,
            "rice_profile_path": str(self.profile_path),
            "rice_profile_exists": self.profile_path.exists(),
            "gtfs_profile_path": str(self.gtfs_profile_path),
            "gtfs_profile_exists": self.gtfs_profile_path.exists(),
            "osm_profile_path": str(self.osm_profile_path),
            "osm_profile_exists": self.osm_profile_path.exists(),
            "traffic_profile_path": str(self.traffic_profile_path),
            "traffic_profile_exists": self.traffic_profile_path.exists(),
            "candidate_profile_path": str(self.candidate_profile_path),
            "candidate_profile_exists": self.candidate_profile_path.exists(),
            "equity_profile_path": str(self.equity_profile_path),
            "equity_profile_exists": self.equity_profile_path.exists(),
            "metadata": self.data_metadata,
            "network": {
                "node_count": len(self.network_nodes),
                "edge_count": len(self.edges),
                "route_count": sum(bool(route) for route in self.routes.values()),
            },
            "transit": {
                "stadium_access_score": round(self.stadium_transit_score, 1),
                "zone_access_scores": self.zone_transit_scores,
            },
            "candidates": {
                "candidate_count": len(self.candidate_sites),
                "type_summary": (self.candidate_profile or {}).get("type_summary", {}),
            },
            "equity": {
                "zone_count": len(self.equity_by_zone),
                "covered_zones": sorted(self.equity_by_zone),
            },
        }

    def demand_calibration(self) -> dict:
        """Return an auditable zone-level OD demand table with uncertainty bands."""
        profile_rows = {
            str(row.get("zone_id")): row
            for row in (self.rice_profile or {}).get("zones", [])
            if row.get("zone_id")
        }
        signal_weights = {
            "poi_count": 0.30,
            "sampled_visits": 0.40,
            "sampled_customers": 0.20,
            "sampled_spend": 0.10,
        }
        signal_values: dict[str, dict[str, float]] = {key: {} for key in signal_weights}
        for zone in self.zones:
            signals = dict(profile_rows.get(zone.zone_id, {}).get("signals", {}))
            for signal in signal_weights:
                try:
                    signal_values[signal][zone.zone_id] = max(0.0, float(signals.get(signal, 0.0) or 0.0))
                except (TypeError, ValueError):
                    signal_values[signal][zone.zone_id] = 0.0
        normalized: dict[str, dict[str, float]] = {}
        for signal, values in signal_values.items():
            total = sum(values.values())
            normalized[signal] = {
                zone.zone_id: (values.get(zone.zone_id, 0.0) / total if total > 0 else 1.0 / max(1, len(self.zones)))
                for zone in self.zones
            }

        rows: list[dict] = []
        real_profile = bool(self.rice_profile)
        for zone in self.zones:
            row = profile_rows.get(zone.zone_id, {})
            signals = dict(row.get("signals", {}))
            available = sum(float(signals.get(key, 0.0) or 0.0) > 0 for key in signal_weights)
            uncertainty_pct = (8.0 + (4 - available) * 3.0) if real_profile else 18.0
            uncertainty_pct = max(8.0, min(24.0, uncertainty_pct))
            contributions_raw = {
                key: signal_weights[key] * normalized[key][zone.zone_id]
                for key in signal_weights
            }
            contribution_total = sum(contributions_raw.values()) or 1.0
            central = float(zone.demand)
            rows.append({
                "zone_id": zone.zone_id,
                "zone_name": zone.name,
                "central_demand": round(central),
                "low_demand": round(central * (1.0 - uncertainty_pct / 100.0)),
                "high_demand": round(central * (1.0 + uncertainty_pct / 100.0)),
                "uncertainty_pct": round(uncertainty_pct, 1),
                "evidence_fields": available,
                "confidence_score": round(max(25.0, 100.0 - uncertainty_pct * 2.5), 1),
                "signals": {
                    key: round(float(signals.get(key, 0.0) or 0.0), 2)
                    for key in signal_weights
                },
                "contribution_pct": {
                    key: round(100.0 * value / contribution_total, 1)
                    for key, value in contributions_raw.items()
                },
                "heat_index": round(zone.heat_index, 1),
                "resource_gap": round(zone.resource_gap, 3),
                "transit_access_score": round(self.zone_transit_scores.get(zone.zone_id, 0.0), 1),
            })

        central_total = sum(row["central_demand"] for row in rows)
        low_total = sum(row["low_demand"] for row in rows)
        high_total = sum(row["high_demand"] for row in rows)
        settings = (self.rice_profile or {}).get("settings", {})
        configured_attendance = int(settings.get("event_attendance", 72000))
        modeled_share = central_total / max(1, configured_attendance)
        return {
            "data_mode": self.data_mode,
            "formula": "30% POI share + 40% visit share + 20% customer share + 10% spend share",
            "weights": signal_weights,
            "rows": rows,
            "totals": {
                "configured_event_attendance": configured_attendance,
                "central_modeled_demand": central_total,
                "low_modeled_demand": low_total,
                "high_modeled_demand": high_total,
                "modeled_share_of_attendance_pct": round(modeled_share * 100.0, 1),
            },
            "reconciliation": {
                "status": "pass" if abs(central_total - sum(zone.demand for zone in self.zones)) <= len(self.zones) else "warning",
                "planning_assumption": "The origin-zone model represents the share of event attendance expected to generate city-network trips in the modeled window.",
            },
            "disclaimer": "Demand bands express scenario uncertainty from data coverage; they are not statistical confidence intervals.",
        }

    def candidate_recommendations(self) -> dict:
        profile = self.candidate_profile or {}
        sites = list(profile.get("candidates", []))
        recommendations: dict[str, list[dict]] = {}
        for candidate_type in ("park_ride", "rideshare", "fan_zone", "cooling_medical"):
            subset = sorted(
                (site for site in sites if site.get("candidate_type") == candidate_type),
                key=lambda site: (float(site.get("readiness_score", 0.0)), -float(site.get("cost_usd", 0.0))),
                reverse=True,
            )
            recommendations[candidate_type] = subset[:3]
        park_sites = recommendations.get("park_ride", [])
        rideshare_sites = recommendations.get("rideshare", [])
        return {
            "profile_exists": bool(self.candidate_profile),
            "candidate_count": len(sites),
            "recommendations": recommendations,
            "operational_summary": {
                "park_ride_capacity_riders": round(sum(float(site.get("capacity_riders", 0.0)) for site in park_sites)),
                "verified_park_ride_capacity_riders": round(sum(float(site.get("capacity_riders", 0.0)) for site in park_sites if site.get("capacity_verified"))),
                "accessible_park_ride_capacity_riders": round(sum(float(site.get("capacity_riders", 0.0)) for site in park_sites if site.get("accessible"))),
                "recommended_shuttle_cycle_minutes": round(
                    max((float(site.get("estimated_cycle_minutes", 0.0)) for site in park_sites), default=0.0), 1
                ),
                "rideshare_capacity_riders": round(sum(float(site.get("capacity_riders", 0.0)) for site in rideshare_sites)),
                "accessible_recommended_sites": sum(bool(site.get("accessible")) for group in recommendations.values() for site in group),
                "verified_accessible_recommended_sites": sum(bool(site.get("accessible")) and bool(site.get("accessibility_verified")) for group in recommendations.values() for site in group),
                "official_recommended_sites": sum(bool(site.get("official_source")) for group in recommendations.values() for site in group),
            },
            "warnings": profile.get("warnings", []),
            "disclaimer": profile.get("disclaimer") or "No candidate-site profile is connected; operational locations remain assumptions.",
        }

    def equity_report(self) -> dict:
        profile = self.equity_profile or {}
        rows: list[dict] = []
        demand_by_zone = {zone.zone_id: float(zone.demand) for zone in self.zones}
        for zone in self.zones:
            evidence = dict(self.equity_by_zone.get(zone.zone_id, {}))
            if not evidence:
                rows.append({
                    "zone_id": zone.zone_id,
                    "zone_name": zone.name,
                    "demand": round(zone.demand),
                    "evidence_connected": False,
                    "vulnerability_index": None,
                    "zero_vehicle_share": None,
                    "low_income_share": None,
                    "disability_share": None,
                    "svi_percentile": None,
                    "ada_path_score": None,
                })
                continue
            rows.append({
                "zone_id": zone.zone_id,
                "zone_name": zone.name,
                "demand": round(zone.demand),
                "evidence_connected": True,
                "vulnerability_index": round(float(evidence.get("vulnerability_index", 0.0)) * 100.0, 1),
                "zero_vehicle_share": round(float(evidence.get("zero_vehicle_share", 0.0)) * 100.0, 1),
                "low_income_share": round(float(evidence.get("low_income_share", 0.0)) * 100.0, 1),
                "disability_share": round(float(evidence.get("disability_share", 0.0)) * 100.0, 1),
                "svi_percentile": round(float(evidence.get("svi_percentile", 0.0)) * 100.0, 1),
                "ada_path_score": round(float(evidence.get("ada_path_score", 0.0)) * 100.0, 1),
                "source_name": evidence.get("source_name"),
                "source_url": evidence.get("source_url"),
                "evidence_year": evidence.get("evidence_year"),
            })
        connected = [row for row in rows if row["evidence_connected"]]
        weighted_vulnerability = 0.0
        total_demand = sum(demand_by_zone.values())
        if connected and total_demand > 0:
            weighted_vulnerability = sum(
                demand_by_zone[row["zone_id"]] * float(self.equity_by_zone[row["zone_id"]].get("vulnerability_index", 0.0))
                for row in connected
            ) / total_demand
        return {
            "profile_exists": bool(self.equity_profile),
            "zone_count": len(self.equity_by_zone),
            "rows": rows,
            "demand_weighted_vulnerability_index": round(weighted_vulnerability * 100.0, 1),
            "method": profile.get("method", {}),
            "warnings": profile.get("warnings", []),
            "disclaimer": profile.get("disclaimer") or "No equity profile is connected; equity-aware optimization is disabled.",
        }

    def baseline_audit(self) -> dict:
        baseline = self.baseline()
        calibration = self.demand_calibration()
        validation = self.validation_report()
        assigned = sum(float(item.get("riders", 0.0)) for item in baseline.get("mode_split", {}).values())
        modeled = float(baseline["metrics"]["modeled_visitors"])
        route_count = sum(bool(self.routes.get(zone.zone_id)) for zone in self.zones)
        direct = int(self.data_metadata.get("traffic", {}).get("directly_calibrated_edges", 0) or 0)
        edge_count = max(1, len(self.edges))
        checks = [
            {
                "check": "OD demand reconciliation",
                "status": calibration["reconciliation"]["status"],
                "value": calibration["totals"]["central_modeled_demand"],
                "target": round(sum(zone.demand for zone in self.zones)),
            },
            {
                "check": "Mode assignment conservation",
                "status": "pass" if abs(assigned - modeled) <= max(5.0, modeled * 0.001) else "warning",
                "value": round(assigned),
                "target": round(modeled),
            },
            {
                "check": "Origin route coverage",
                "status": "pass" if route_count == len(self.zones) else "warning",
                "value": route_count,
                "target": len(self.zones),
            },
            {
                "check": "Observed traffic calibration",
                "status": "pass" if direct / edge_count >= 0.35 else "warning",
                "value": round(100.0 * direct / edge_count, 1),
                "target": ">= 35% of modeled edges",
            },
            {
                "check": "Candidate infrastructure evidence",
                "status": "pass" if self.candidate_profile else "warning",
                "value": len(self.candidate_sites),
                "target": "> 0 candidate sites",
            },
            {
                "check": "Equity and accessibility evidence",
                "status": "pass" if len(self.equity_by_zone) == len(self.zones) else "warning",
                "value": len(self.equity_by_zone),
                "target": len(self.zones),
            },
        ]
        return {
            "checks": checks,
            "passed": sum(item["status"] == "pass" for item in checks),
            "total": len(checks),
            "validation": validation,
            "demand_totals": calibration["totals"],
            "interpretation": "The audit checks internal consistency and evidence coverage; it does not establish predictive accuracy.",
        }

    @staticmethod
    def time_window_catalog() -> list[dict]:
        return [{"window_id": key, **value} for key, value in TIME_WINDOWS.items()]

    @staticmethod
    def stressor_catalog() -> list[dict]:
        return [{"stressor_id": key, **value} for key, value in STRESSORS.items()]

    @staticmethod
    def preset_catalog() -> list[dict]:
        return [
            {"preset_id": key, "interventions": value}
            for key, value in PRESETS.items()
        ]

    @staticmethod
    def operations_catalog() -> dict:
        return {
            "defaults": dict(DEFAULT_OPERATIONS),
            "parameters": [
                {
                    "operation_id": key,
                    "label": OPERATION_LABELS[key],
                    "minimum": OPERATION_LIMITS[key][0],
                    "maximum": OPERATION_LIMITS[key][1],
                    "default": DEFAULT_OPERATIONS[key],
                }
                for key in DEFAULT_OPERATIONS
            ],
        }

    @staticmethod
    def normalize_operations(overrides: dict | None = None) -> dict[str, float]:
        values = dict(DEFAULT_OPERATIONS)
        for key, raw in (overrides or {}).items():
            if key not in values:
                raise ValueError(f"Unknown operational parameter: {key}")
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Operational parameter {key} must be numeric.") from exc
            lower, upper = OPERATION_LIMITS[key]
            if value < lower or value > upper:
                raise ValueError(f"Operational parameter {key} must be between {lower} and {upper}.")
            values[key] = value
        return values

    def validation_report(self) -> dict:
        total_edges = max(1, len(self.edges))
        traffic_meta = self.data_metadata.get("traffic", {})
        direct = int(traffic_meta.get("directly_calibrated_edges", 0) or 0)
        inferred = int(traffic_meta.get("class_inferred_edges", 0) or 0)
        route_coverage = sum(bool(self.routes.get(zone.zone_id)) for zone in self.zones) / max(1, len(self.zones))
        transit_coverage = sum(self.zone_transit_scores.get(zone.zone_id, 0) > 0 for zone in self.zones) / max(1, len(self.zones))
        components = {
            "visitor_demand": 1.0 if self.profile_path.exists() else 0.35,
            "transit_schedule": 1.0 if self.gtfs_profile_path.exists() else 0.20,
            "road_topology": 1.0 if self.osm_profile_path.exists() else 0.25,
            "traffic_baseline": min(1.0, (direct + 0.45 * inferred) / total_edges) if self.traffic_profile_path.exists() else 0.10,
            "route_coverage": route_coverage,
            "transit_zone_coverage": transit_coverage,
            "candidate_infrastructure": 1.0 if self.candidate_profile_path.exists() else 0.15,
            "equity_accessibility": len(self.equity_by_zone) / max(1, len(self.zones)),
        }
        weights = {
            "visitor_demand": 16,
            "transit_schedule": 13,
            "road_topology": 17,
            "traffic_baseline": 20,
            "route_coverage": 9,
            "transit_zone_coverage": 8,
            "candidate_infrastructure": 9,
            "equity_accessibility": 8,
        }
        confidence = sum(components[key] * weights[key] for key in weights)
        if confidence >= 82:
            band = "decision-demo ready"
        elif confidence >= 58:
            band = "partially calibrated"
        else:
            band = "methodology prototype"
        assumptions = [
            "Match-day OD demand is inferred from sampled activity and venue-capacity signals unless an official OD table is connected.",
            "Road capacities rely on highway-class defaults wherever observed counts or lane tags are unavailable.",
            "Shuttle, transit and rideshare shifts are capped by explicit operational and candidate-site capacity assumptions in v0.9.",
            "Equity metrics use zone-level screening indicators and do not establish legal ADA compliance.",
            "Intervention costs and behavioral response coefficients remain planning estimates for scenario comparison.",
        ]
        return {
            "data_mode": self.data_mode,
            "confidence_score": round(confidence, 1),
            "confidence_band": band,
            "components": {key: round(value * 100, 1) for key, value in components.items()},
            "coverage": {
                "origin_zones_with_routes": sum(bool(self.routes.get(zone.zone_id)) for zone in self.zones),
                "origin_zone_count": len(self.zones),
                "road_edges": len(self.edges),
                "directly_calibrated_edges": direct,
                "class_inferred_edges": inferred,
            },
            "assumptions": assumptions,
            "interpretation": "The score measures model-evidence coverage, not predictive accuracy.",
        }

    def _validate_window(self, time_window: str) -> dict:
        if time_window not in TIME_WINDOWS:
            raise ValueError(f"Unknown time window: {time_window}")
        return TIME_WINDOWS[time_window]

    def _validate_interventions(self, selected_ids: Iterable[str]) -> list[str]:
        selected = list(dict.fromkeys(selected_ids))
        unknown = set(selected) - set(self.intervention_map)
        if unknown:
            raise ValueError(f"Unknown interventions: {sorted(unknown)}")
        return selected

    def _resolved_target_edges(self, intervention: Intervention) -> list[str]:
        available = {edge.edge_id for edge in self.edges}
        explicit = [edge_id for edge_id in intervention.target_edges if edge_id in available]
        if explicit:
            return explicit
        if not self.osm_profile:
            return []
        if intervention.intervention_id in {"vehicle_restriction", "rideshare_staging"}:
            group = "stadium_core"
        else:
            group = "critical_corridors"
        candidates = [edge_id for edge_id in self.target_groups.get(group, []) if edge_id in available]
        limits = {
            "vehicle_restriction": 16,
            "rideshare_staging": 12,
            "bus_only_lane": 18,
            "pedestrian_guidance": 20,
            "cooling_resources": 20,
        }
        return candidates[: limits.get(intervention.intervention_id, 16)]

    def _stress_edge_multipliers(self, stressor_id: str) -> dict[str, float]:
        configured = dict(STRESSORS[stressor_id]["edge_capacity_multipliers"])
        available = {edge.edge_id for edge in self.edges}
        filtered = {edge_id: value for edge_id, value in configured.items() if edge_id in available}
        if filtered or not self.osm_profile:
            return filtered
        critical = [edge_id for edge_id in self.target_groups.get("critical_corridors", []) if edge_id in available]
        core = [edge_id for edge_id in self.target_groups.get("stadium_core", []) if edge_id in available]
        if stressor_id == "corridor_incident" and critical:
            return {critical[0]: 0.28}
        if stressor_id == "transit_disruption":
            return {edge_id: 0.72 for edge_id in (critical[:3] or core[:3])}
        if stressor_id == "compound_shock":
            targets = (critical[:2] + core[:1])[:3]
            return {edge_id: 0.70 for edge_id in targets}
        return {}

    def _calculate(
        self,
        selected_ids: Iterable[str],
        *,
        time_window: str = "ingress_peak",
        demand_multiplier: float = 1.0,
        capacity_multiplier: float = 1.0,
        car_share_multiplier: float = 1.0,
        heat_multiplier: float = 1.0,
        baseline_multiplier: float = 1.0,
        edge_capacity_multipliers: dict[str, float] | None = None,
        operations: dict | None = None,
    ) -> dict:
        selected_ids = self._validate_interventions(selected_ids)
        selected = [self.intervention_map[item] for item in selected_ids]
        selected_set = set(selected_ids)
        window = self._validate_window(time_window)
        operations = self.normalize_operations(operations)
        edge_capacity_multipliers = edge_capacity_multipliers or {}

        effective_demand_multiplier = demand_multiplier * float(window["demand_multiplier"])
        effective_car_multiplier = car_share_multiplier * float(window["car_share_multiplier"])
        effective_heat_multiplier = heat_multiplier * float(window["heat_multiplier"])
        effective_baseline_multiplier = baseline_multiplier * float(window["baseline_multiplier"])

        edge_state = {
            edge.edge_id: {
                "edge": edge,
                "capacity": edge.capacity_vehicles
                * capacity_multiplier
                * edge_capacity_multipliers.get(edge.edge_id, 1.0),
                "flow_multiplier": 1.0,
                "travel_time_multiplier": 1.0,
                "heat_multiplier": effective_heat_multiplier,
                "added_flow": 0.0,
            }
            for edge in self.edges
        }

        stadium_access_factor = max(0.90, 1.0 - 0.08 * self.stadium_transit_score / 100.0)
        initial_car_share: dict[str, float] = {}
        zone_demand: dict[str, float] = {}
        for zone in self.zones:
            access_score = self.zone_transit_scores.get(zone.zone_id, 0.0)
            zone_access_factor = max(0.76, 1.0 - 0.18 * access_score / 100.0)
            initial_car_share[zone.zone_id] = min(0.95, max(0.05,
                zone.car_share * effective_car_multiplier * zone_access_factor * stadium_access_factor
            ))
            zone_demand[zone.zone_id] = zone.demand * effective_demand_multiplier

        non_transit_global_multiplier = 1.0
        transit_multiplier = 1.0
        smoothing = 0.0
        target_zone_multipliers: dict[str, float] = {zone.zone_id: 1.0 for zone in self.zones}
        for intervention in selected:
            effects = intervention.effects
            if intervention.intervention_id == "transit_boost":
                transit_multiplier *= effects.get("global_car_share_multiplier", 1.0)
            else:
                non_transit_global_multiplier *= effects.get("global_car_share_multiplier", 1.0)
            smoothing += effects.get("pressure_smoothing", 0.0)
            if intervention.intervention_id != "park_ride_shuttle":
                for zone_id in intervention.target_zones:
                    if zone_id in target_zone_multipliers:
                        target_zone_multipliers[zone_id] *= effects.get("target_zone_car_share_multiplier", 1.0)
            for edge_id in self._resolved_target_edges(intervention):
                if edge_id not in edge_state:
                    continue
                state = edge_state[edge_id]
                state["capacity"] *= effects.get("target_capacity_multiplier", 1.0)
                state["flow_multiplier"] *= effects.get("target_flow_multiplier", 1.0)
                state["travel_time_multiplier"] *= effects.get("travel_time_multiplier", 1.0)
                state["heat_multiplier"] *= effects.get("heat_exposure_multiplier", 1.0)

        pre_transit_share = {
            zone_id: min(0.95, max(0.05, share * non_transit_global_multiplier * target_zone_multipliers[zone_id]))
            for zone_id, share in initial_car_share.items()
        }
        desired_transit_shift = {zone_id: 0.0 for zone_id in pre_transit_share}
        if "transit_boost" in selected_set:
            for zone_id, share in pre_transit_share.items():
                desired_share = min(0.95, max(0.05, share * transit_multiplier))
                desired_transit_shift[zone_id] = max(0.0, zone_demand[zone_id] * (share - desired_share))
        total_desired_transit = sum(desired_transit_shift.values())
        transit_capacity = operations["transit_extra_capacity"] if "transit_boost" in selected_set else 0.0
        transit_service_ratio = min(1.0, transit_capacity / max(1.0, total_desired_transit)) if total_desired_transit else 1.0
        transit_shift = {zone_id: value * transit_service_ratio for zone_id, value in desired_transit_shift.items()}

        after_transit_share = {
            zone_id: max(0.05, pre_transit_share[zone_id] - transit_shift[zone_id] / max(1.0, zone_demand[zone_id]))
            for zone_id in pre_transit_share
        }

        desired_shuttle_shift = {zone_id: 0.0 for zone_id in after_transit_share}
        shuttle_targets: list[str] = []
        if "park_ride_shuttle" in selected_set:
            shuttle_intervention = self.intervention_map["park_ride_shuttle"]
            shuttle_targets = [zone_id for zone_id in shuttle_intervention.target_zones if zone_id in after_transit_share]
            target_multiplier = shuttle_intervention.effects.get("target_zone_car_share_multiplier", 1.0)
            for zone_id in shuttle_targets:
                desired_share = max(0.05, after_transit_share[zone_id] * target_multiplier)
                desired_shuttle_shift[zone_id] = max(0.0, zone_demand[zone_id] * (after_transit_share[zone_id] - desired_share))
        candidate_plan = self.candidate_recommendations()
        candidate_summary = candidate_plan["operational_summary"]
        route_cycle_floor = float(candidate_summary.get("recommended_shuttle_cycle_minutes", 0.0) or 0.0)
        effective_shuttle_cycle = max(operations["shuttle_cycle_minutes"], route_cycle_floor) if route_cycle_floor else operations["shuttle_cycle_minutes"]
        trips_per_vehicle = max(1, math.floor(operations["operating_window_minutes"] / effective_shuttle_cycle))
        fleet_shuttle_capacity = (
            operations["shuttle_fleet"]
            * operations["shuttle_seats"]
            * operations["shuttle_load_factor"]
            * trips_per_vehicle
            if "park_ride_shuttle" in selected_set else 0.0
        )
        candidate_shuttle_capacity = float(candidate_summary.get("park_ride_capacity_riders", 0.0) or 0.0)
        shuttle_capacity = (
            min(fleet_shuttle_capacity, candidate_shuttle_capacity)
            if "park_ride_shuttle" in selected_set and self.candidate_profile
            else fleet_shuttle_capacity
        )
        total_desired_shuttle = sum(desired_shuttle_shift.values())
        shuttle_service_ratio = min(1.0, shuttle_capacity / max(1.0, total_desired_shuttle)) if total_desired_shuttle else 1.0
        shuttle_shift = {zone_id: value * shuttle_service_ratio for zone_id, value in desired_shuttle_shift.items()}
        final_car_share = {
            zone_id: max(0.05, after_transit_share[zone_id] - shuttle_shift[zone_id] / max(1.0, zone_demand[zone_id]))
            for zone_id in after_transit_share
        }

        total_visitors = 0.0
        total_modeled_vehicles = 0.0
        aggregate_modes = {"road_vehicle_passengers": 0.0, "shuttle_riders": 0.0, "transit_riders": 0.0, "walk_bike_riders": 0.0}
        zone_assignments: list[dict] = []
        equity_connected = bool(self.equity_profile)
        vulnerability_weighted_demand = 0.0
        vulnerability_noncar_service = 0.0
        zero_vehicle_weighted_demand = 0.0
        zero_vehicle_mobility_service = 0.0
        disability_weighted_demand = 0.0
        accessibility_public_service = 0.0
        accessible_park_capacity = float(candidate_summary.get("accessible_park_ride_capacity_riders", 0.0) or 0.0)
        total_park_capacity = float(candidate_summary.get("park_ride_capacity_riders", 0.0) or 0.0)
        shuttle_accessibility_factor = min(1.0, accessible_park_capacity / total_park_capacity) if total_park_capacity > 0 else 0.35
        for zone in self.zones:
            demand = zone_demand[zone.zone_id]
            total_visitors += demand
            car_passengers = demand * final_car_share[zone.zone_id]
            car_vehicles = car_passengers / 2.1
            shuttle_riders = shuttle_shift[zone.zone_id]
            shuttle_vehicles = shuttle_riders / max(1.0, operations["shuttle_seats"] * operations["shuttle_load_factor"])
            total_modeled_vehicles += car_vehicles + shuttle_vehicles
            for edge_id, route_share in self.routes.get(zone.zone_id, {}).items():
                if edge_id in edge_state:
                    edge_state[edge_id]["added_flow"] += (car_vehicles + shuttle_vehicles) * route_share

            nonroad_remaining = max(0.0, demand - car_passengers - shuttle_riders)
            access_score = self.zone_transit_scores.get(zone.zone_id, 0.0)
            route_distance = sum(
                edge.distance_miles * self.routes.get(zone.zone_id, {}).get(edge.edge_id, 0.0)
                for edge in self.edges
            )
            transit_weight = min(0.94, 0.36 + 0.56 * access_score / 100.0 + (0.10 if route_distance > 4 else 0.0))
            transit_riders = nonroad_remaining * transit_weight
            walk_bike_riders = nonroad_remaining - transit_riders
            aggregate_modes["road_vehicle_passengers"] += car_passengers
            aggregate_modes["shuttle_riders"] += shuttle_riders
            aggregate_modes["transit_riders"] += transit_riders
            aggregate_modes["walk_bike_riders"] += walk_bike_riders
            equity = self.equity_by_zone.get(zone.zone_id, {})
            vulnerability = float(equity.get("vulnerability_index", 0.0) or 0.0)
            zero_vehicle_share = float(equity.get("zero_vehicle_share", 0.0) or 0.0)
            disability_share = float(equity.get("disability_share", 0.0) or 0.0)
            ada_path_score = float(equity.get("ada_path_score", 0.0) or 0.0)
            noncar_share = (shuttle_riders + transit_riders + walk_bike_riders) / max(1.0, demand)
            accessible_public_share = (transit_riders * ada_path_score + shuttle_riders * ada_path_score * shuttle_accessibility_factor) / max(1.0, demand)
            vulnerability_demand = demand * vulnerability
            zero_vehicle_demand = demand * zero_vehicle_share
            disability_demand = demand * disability_share
            vulnerability_weighted_demand += vulnerability_demand
            vulnerability_noncar_service += vulnerability_demand * noncar_share
            zero_vehicle_weighted_demand += zero_vehicle_demand
            zero_vehicle_mobility_service += zero_vehicle_demand * noncar_share
            disability_weighted_demand += disability_demand
            accessibility_public_service += disability_demand * min(1.0, accessible_public_share)
            zone_assignments.append({
                "zone_id": zone.zone_id,
                "zone_name": zone.name,
                "visitors": round(demand),
                "road_vehicle_passengers": round(car_passengers),
                "shuttle_riders": round(shuttle_riders),
                "transit_riders": round(transit_riders),
                "walk_bike_riders": round(walk_bike_riders),
                "private_vehicles": round(car_vehicles),
                "transit_access_score": round(access_score, 1),
                "route_distance_miles": round(route_distance, 1),
                "equity_evidence_connected": bool(equity),
                "vulnerability_index": round(vulnerability * 100.0, 1) if equity else None,
                "zero_vehicle_share": round(zero_vehicle_share * 100.0, 1) if equity else None,
                "disability_share": round(disability_share * 100.0, 1) if equity else None,
                "ada_path_score": round(ada_path_score * 100.0, 1) if equity else None,
                "noncar_coverage_pct": round(noncar_share * 100.0, 1),
                "accessible_public_mode_proxy_pct": round(min(1.0, accessible_public_share) * 100.0, 1) if equity else None,
            })

        raw_pressures: list[float] = []
        edge_results: list[dict] = []
        weighted_time = 0.0
        weighted_heat = 0.0
        total_edge_flow = 0.0
        vehicle_miles = 0.0
        direction = str(window["direction"])

        for edge_id, state in edge_state.items():
            edge: Edge = state["edge"]
            added_flow = state["added_flow"] * state["flow_multiplier"]
            baseline = edge.baseline_vehicles * effective_baseline_multiplier
            capacity = max(1.0, state["capacity"])
            pressure = (baseline + added_flow) / capacity
            raw_pressures.append(pressure)
            source, target = edge.source, edge.target
            if direction == "outbound":
                source, target = target, source
            edge_results.append({
                "edge_id": edge.edge_id,
                "name": edge.name,
                "source": source,
                "target": target,
                "baseline": round(baseline, 1),
                "added_flow": round(added_flow, 1),
                "capacity": round(capacity, 1),
                "pressure": pressure,
                "heat_index": edge.heat_index * state["heat_multiplier"],
                "distance_miles": edge.distance_miles,
                "direction": direction,
                "highway": edge.highway,
                "geometry": [list(point) for point in edge.geometry],
                "calibration_source": edge.calibration_source,
            })

        mean_pressure = sum(raw_pressures) / max(1, len(raw_pressures))
        for row in edge_results:
            if smoothing > 0:
                row["pressure"] = (1 - smoothing) * row["pressure"] + smoothing * mean_pressure
            congestion_multiplier = 1.0 + max(0.0, row["pressure"] - 0.65) * 1.9
            edge = edge_state[row["edge_id"]]["edge"]
            travel_time = edge.freeflow_minutes * congestion_multiplier * edge_state[row["edge_id"]]["travel_time_multiplier"]
            row["travel_time_minutes"] = round(travel_time, 1)
            flow_weight = row["baseline"] + row["added_flow"]
            weighted_time += travel_time * flow_weight
            weighted_heat += row["heat_index"] * row["added_flow"] * edge.distance_miles
            total_edge_flow += flow_weight
            vehicle_miles += row["added_flow"] * edge.distance_miles
            row["pressure"] = round(row["pressure"], 4)
            row["heat_index"] = round(row["heat_index"], 1)

        estimated_rideshare_demand = aggregate_modes["road_vehicle_passengers"] * 0.22 if "rideshare_staging" in selected_set else 0.0
        configured_rideshare_capacity = operations["rideshare_staging_capacity"] if "rideshare_staging" in selected_set else 0.0
        candidate_rideshare_capacity = float(candidate_summary.get("rideshare_capacity_riders", 0.0) or 0.0)
        rideshare_capacity = (
            min(configured_rideshare_capacity, candidate_rideshare_capacity)
            if "rideshare_staging" in selected_set and self.candidate_profile
            else configured_rideshare_capacity
        )
        served_rideshare = min(estimated_rideshare_demand, rideshare_capacity)
        unmet_transit = max(0.0, total_desired_transit - sum(transit_shift.values()))
        unmet_shuttle = max(0.0, total_desired_shuttle - sum(shuttle_shift.values()))
        unmet_rideshare = max(0.0, estimated_rideshare_demand - served_rideshare)
        unmet_shift = unmet_transit + unmet_shuttle + unmet_rideshare

        cost = sum(item.cost_usd for item in selected)
        if "park_ride_shuttle" in selected_set:
            cost += (operations["shuttle_fleet"] - DEFAULT_OPERATIONS["shuttle_fleet"]) * 4000.0
        if "transit_boost" in selected_set:
            cost += (operations["transit_extra_capacity"] - DEFAULT_OPERATIONS["transit_extra_capacity"]) * 14.0
        if "rideshare_staging" in selected_set:
            cost += (operations["rideshare_staging_capacity"] - DEFAULT_OPERATIONS["rideshare_staging_capacity"]) * 13.0
        cost = max(0.0, cost)

        high_pressure = sum(row["pressure"] >= 0.90 for row in edge_results)
        critical_pressure = sum(row["pressure"] >= 1.00 for row in edge_results)
        avg_time = weighted_time / max(total_edge_flow, 1.0)
        heat_exposure = weighted_heat / 100000.0
        emissions_kg = vehicle_miles * 0.40
        max_pressure = max(row["pressure"] for row in edge_results)
        transit_bonus = 0.045 * self.stadium_transit_score
        readiness = max(0.0, min(100.0,
            100
            - 35 * max(0, max_pressure - 0.75)
            - 2.5 * high_pressure
            - 0.10 * heat_exposure
            - 0.0015 * unmet_shift
            + transit_bonus
        ))

        mode_total = max(1.0, sum(aggregate_modes.values()))
        mode_split = {
            key: {"riders": round(value), "share_pct": round(value / mode_total * 100, 1)}
            for key, value in aggregate_modes.items()
        }
        equity_metrics = {
            "profile_connected": equity_connected,
            "vulnerable_noncar_coverage_pct": round(100.0 * vulnerability_noncar_service / max(1.0, vulnerability_weighted_demand), 1) if equity_connected else None,
            "zero_vehicle_mobility_coverage_pct": round(100.0 * zero_vehicle_mobility_service / max(1.0, zero_vehicle_weighted_demand), 1) if equity_connected else None,
            "accessible_public_mode_coverage_pct": round(100.0 * accessibility_public_service / max(1.0, disability_weighted_demand), 1) if equity_connected else None,
            "vulnerability_weighted_demand": round(vulnerability_weighted_demand) if equity_connected else None,
            "zero_vehicle_weighted_demand": round(zero_vehicle_weighted_demand) if equity_connected else None,
            "disability_weighted_demand": round(disability_weighted_demand) if equity_connected else None,
            "shuttle_accessibility_factor_pct": round(shuttle_accessibility_factor * 100.0, 1),
            "interpretation": "Coverage metrics are demand-weighted planning proxies; they do not certify route-level ADA compliance.",
        }

        feasibility = {
            "shuttle": {
                "active": "park_ride_shuttle" in selected_set,
                "desired_riders": round(total_desired_shuttle),
                "capacity_riders": round(shuttle_capacity),
                "fleet_capacity_riders": round(fleet_shuttle_capacity),
                "candidate_site_capacity_riders": round(candidate_shuttle_capacity),
                "served_riders": round(sum(shuttle_shift.values())),
                "unmet_riders": round(unmet_shuttle),
                "utilization_pct": round(100 * sum(shuttle_shift.values()) / max(1.0, shuttle_capacity), 1) if shuttle_capacity else 0.0,
                "fleet": round(operations["shuttle_fleet"]),
                "trips_per_vehicle": trips_per_vehicle,
                "configured_cycle_minutes": round(operations["shuttle_cycle_minutes"], 1),
                "effective_cycle_minutes": round(effective_shuttle_cycle, 1),
                "candidate_sites_connected": bool(self.candidate_profile),
            },
            "transit": {
                "active": "transit_boost" in selected_set,
                "desired_riders": round(total_desired_transit),
                "capacity_riders": round(transit_capacity),
                "served_riders": round(sum(transit_shift.values())),
                "unmet_riders": round(unmet_transit),
                "utilization_pct": round(100 * sum(transit_shift.values()) / max(1.0, transit_capacity), 1) if transit_capacity else 0.0,
            },
            "rideshare": {
                "active": "rideshare_staging" in selected_set,
                "estimated_riders": round(estimated_rideshare_demand),
                "capacity_riders": round(rideshare_capacity),
                "configured_capacity_riders": round(configured_rideshare_capacity),
                "candidate_site_capacity_riders": round(candidate_rideshare_capacity),
                "served_riders": round(served_rideshare),
                "unmet_riders": round(unmet_rideshare),
                "utilization_pct": round(100 * served_rideshare / max(1.0, rideshare_capacity), 1) if rideshare_capacity else 0.0,
            },
            "total_unmet_shift_demand": round(unmet_shift),
        }

        return {
            "data_mode": self.data_mode,
            "data_metadata": self.data_metadata,
            "time_window": time_window,
            "time_window_label": window["label"],
            "flow_direction": direction,
            "selected_interventions": selected_ids,
            "selected_names": [item.name for item in selected],
            "cost_usd": round(cost, 2),
            "operations": operations,
            "operational_feasibility": feasibility,
            "mode_split": mode_split,
            "zone_assignments": zone_assignments,
            "equity_metrics": equity_metrics,
            "assumptions": {
                "demand_multiplier": round(effective_demand_multiplier, 4),
                "capacity_multiplier": round(capacity_multiplier, 4),
                "car_share_multiplier": round(effective_car_multiplier, 4),
                "heat_multiplier": round(effective_heat_multiplier, 4),
                "baseline_multiplier": round(effective_baseline_multiplier, 4),
                "stadium_transit_access_score": round(self.stadium_transit_score, 1),
                "shuttle_capacity_riders": round(shuttle_capacity),
                "shuttle_effective_cycle_minutes": round(effective_shuttle_cycle, 1),
                "candidate_site_profile_connected": bool(self.candidate_profile),
                "transit_extra_capacity": round(transit_capacity),
            },
            "metrics": {
                "modeled_visitors": round(total_visitors),
                "modeled_private_vehicles": round(total_modeled_vehicles),
                "road_vehicle_passengers": round(aggregate_modes["road_vehicle_passengers"]),
                "shuttle_riders": round(aggregate_modes["shuttle_riders"]),
                "transit_riders": round(aggregate_modes["transit_riders"]),
                "walk_bike_riders": round(aggregate_modes["walk_bike_riders"]),
                "unmet_shift_demand": round(unmet_shift),
                "high_pressure_segments": high_pressure,
                "critical_segments": critical_pressure,
                "max_pressure": round(max_pressure, 3),
                "average_network_travel_minutes": round(avg_time, 1),
                "emissions_kg_index": round(emissions_kg, 1),
                "heat_exposure_index": round(heat_exposure, 1),
                "readiness_score": round(readiness, 1),
                "vulnerable_noncar_coverage_pct": equity_metrics["vulnerable_noncar_coverage_pct"],
                "zero_vehicle_mobility_coverage_pct": equity_metrics["zero_vehicle_mobility_coverage_pct"],
                "accessible_public_mode_coverage_pct": equity_metrics["accessible_public_mode_coverage_pct"],
            },
            "network_summary": {
                "total_edges": len(edge_results),
                "displayed_edges": min(len(edge_results), 600),
                "osm_connected": bool(self.osm_profile),
                "traffic_calibrated": bool(self.traffic_profile),
            },
            "edges": self._display_edges(edge_results),
        }

    def _display_edges(self, edge_results: list[dict]) -> list[dict]:
        if len(edge_results) <= 600:
            return edge_results
        target_ids = set(self.target_groups.get("stadium_core", [])) | set(self.target_groups.get("critical_corridors", []))
        relevant = [
            row for row in edge_results
            if row["added_flow"] > 0.01 or row["edge_id"] in target_ids or row["pressure"] >= 0.90
        ]
        relevant.sort(key=lambda row: (row["added_flow"] > 0, row["pressure"], row["added_flow"]), reverse=True)
        return relevant[:600]

    def baseline(self, time_window: str = "ingress_peak", operations: dict | None = None) -> dict:
        return self._calculate([], time_window=time_window, operations=operations)

    def simulate(self, selected_ids: Iterable[str], time_window: str = "ingress_peak", operations: dict | None = None) -> dict:
        selected = self._validate_interventions(selected_ids)
        result = self._calculate(selected, time_window=time_window, operations=operations)
        result["improvement"] = self.compare(self.baseline(time_window, operations), result)
        return result

    def compare_time_windows(self, selected_ids: Iterable[str], operations: dict | None = None) -> dict:
        selected = self._validate_interventions(selected_ids)
        windows: list[dict] = []
        for window_id in TIME_WINDOWS:
            baseline = self.baseline(window_id, operations)
            scenario = self._calculate(selected, time_window=window_id, operations=operations)
            scenario["improvement"] = self.compare(baseline, scenario)
            windows.append({"baseline": baseline, "scenario": scenario})
        return {"selected_interventions": selected, "windows": windows}

    def stress_test(
        self,
        selected_ids: Iterable[str],
        stressor_id: str,
        time_window: str = "ingress_peak",
        operations: dict | None = None,
    ) -> dict:
        selected = self._validate_interventions(selected_ids)
        if stressor_id not in STRESSORS:
            raise ValueError(f"Unknown stressor: {stressor_id}")
        stress = STRESSORS[stressor_id]
        normal_baseline = self.baseline(time_window, operations)
        stressed_baseline = self._calculate(
            [],
            time_window=time_window,
            demand_multiplier=float(stress["demand_multiplier"]),
            capacity_multiplier=float(stress["capacity_multiplier"]),
            car_share_multiplier=float(stress["car_share_multiplier"]),
            heat_multiplier=float(stress["heat_multiplier"]),
            edge_capacity_multipliers=self._stress_edge_multipliers(stressor_id),
            operations=operations,
        )
        stressed_scenario = self._calculate(
            selected,
            time_window=time_window,
            demand_multiplier=float(stress["demand_multiplier"]),
            capacity_multiplier=float(stress["capacity_multiplier"]),
            car_share_multiplier=float(stress["car_share_multiplier"]),
            heat_multiplier=float(stress["heat_multiplier"]),
            edge_capacity_multipliers=self._stress_edge_multipliers(stressor_id),
            operations=operations,
        )
        stressed_scenario["improvement"] = self.compare(stressed_baseline, stressed_scenario)
        return {
            "stressor_id": stressor_id,
            "stressor_label": stress["label"],
            "time_window": time_window,
            "normal_baseline": normal_baseline,
            "stressed_baseline": stressed_baseline,
            "stressed_scenario": stressed_scenario,
            "shock_impact": self.compare(normal_baseline, stressed_baseline),
        }

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        position = (len(ordered) - 1) * percentile
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return ordered[lower]
        weight = position - lower
        return ordered[lower] * (1 - weight) + ordered[upper] * weight

    def sensitivity_analysis(
        self,
        selected_ids: Iterable[str],
        time_window: str = "ingress_peak",
        operations: dict | None = None,
    ) -> dict:
        selected = self._validate_interventions(selected_ids)
        runs: list[dict] = []
        for demand, capacity, car_share, heat in itertools.product(
            (0.85, 1.00, 1.15),
            (0.90, 1.00, 1.10),
            (0.90, 1.00, 1.10),
            (0.95, 1.00, 1.08),
        ):
            result = self._calculate(
                selected,
                time_window=time_window,
                demand_multiplier=demand,
                capacity_multiplier=capacity,
                car_share_multiplier=car_share,
                heat_multiplier=heat,
                operations=operations,
            )
            runs.append(
                {
                    "parameters": {
                        "demand": demand,
                        "capacity": capacity,
                        "car_share": car_share,
                        "heat": heat,
                    },
                    "metrics": result["metrics"],
                }
            )

        metric_names = (
            "readiness_score",
            "max_pressure",
            "average_network_travel_minutes",
            "emissions_kg_index",
            "heat_exposure_index",
        )
        distributions: dict[str, dict[str, float]] = {}
        for metric in metric_names:
            values = [float(run["metrics"][metric]) for run in runs]
            distributions[metric] = {
                "min": round(min(values), 2),
                "p10": round(self._percentile(values, 0.10), 2),
                "median": round(self._percentile(values, 0.50), 2),
                "p90": round(self._percentile(values, 0.90), 2),
                "max": round(max(values), 2),
            }

        worst = min(runs, key=lambda row: row["metrics"]["readiness_score"])
        best = max(runs, key=lambda row: row["metrics"]["readiness_score"])
        return {
            "time_window": time_window,
            "selected_interventions": selected,
            "run_count": len(runs),
            "distributions": distributions,
            "robustness_score": distributions["readiness_score"]["p10"],
            "worst_case": worst,
            "best_case": best,
        }

    @staticmethod
    def compare(baseline: dict, scenario: dict) -> dict:
        before = baseline["metrics"]
        after = scenario["metrics"]

        def pct_reduction(first: float, second: float) -> float:
            if first == 0:
                return 0.0
            return 100.0 * (first - second) / first

        equity_before = baseline.get("equity_metrics", {})
        equity_after = scenario.get("equity_metrics", {})
        def equity_gain(key: str) -> float:
            first = equity_before.get(key)
            second = equity_after.get(key)
            if first is None or second is None:
                return 0.0
            return float(second) - float(first)

        return {
            "high_pressure_reduction_pct": round(
                pct_reduction(before["high_pressure_segments"], after["high_pressure_segments"]), 1
            ),
            "critical_reduction_pct": round(
                pct_reduction(before["critical_segments"], after["critical_segments"]), 1
            ),
            "travel_time_reduction_pct": round(
                pct_reduction(
                    before["average_network_travel_minutes"],
                    after["average_network_travel_minutes"],
                ),
                1,
            ),
            "emissions_reduction_pct": round(
                pct_reduction(before["emissions_kg_index"], after["emissions_kg_index"]), 1
            ),
            "heat_reduction_pct": round(
                pct_reduction(before["heat_exposure_index"], after["heat_exposure_index"]), 1
            ),
            "readiness_gain": round(after["readiness_score"] - before["readiness_score"], 1),
            "vulnerable_noncar_coverage_gain": round(equity_gain("vulnerable_noncar_coverage_pct"), 1),
            "zero_vehicle_coverage_gain": round(equity_gain("zero_vehicle_mobility_coverage_pct"), 1),
            "accessibility_coverage_gain": round(equity_gain("accessible_public_mode_coverage_pct"), 1),
        }

    @staticmethod
    def score_improvement(improvement: dict, objective_mode: str = "balanced") -> float:
        """Convert multi-metric improvement into the same transparent score used by the optimizer."""
        if objective_mode == "equity_first":
            score = (
                0.22 * improvement.get("high_pressure_reduction_pct", 0.0)
                + 0.15 * improvement.get("travel_time_reduction_pct", 0.0)
                + 0.12 * improvement.get("emissions_reduction_pct", 0.0)
                + 0.12 * improvement.get("heat_reduction_pct", 0.0)
                + 0.10 * max(0.0, improvement.get("readiness_gain", 0.0))
                + 0.18 * max(0.0, improvement.get("vulnerable_noncar_coverage_gain", 0.0))
                + 0.11 * max(0.0, improvement.get("accessibility_coverage_gain", 0.0))
            )
        elif objective_mode == "accessibility_first":
            score = (
                0.20 * improvement.get("high_pressure_reduction_pct", 0.0)
                + 0.14 * improvement.get("travel_time_reduction_pct", 0.0)
                + 0.10 * improvement.get("emissions_reduction_pct", 0.0)
                + 0.10 * improvement.get("heat_reduction_pct", 0.0)
                + 0.10 * max(0.0, improvement.get("readiness_gain", 0.0))
                + 0.14 * max(0.0, improvement.get("vulnerable_noncar_coverage_gain", 0.0))
                + 0.22 * max(0.0, improvement.get("accessibility_coverage_gain", 0.0))
            )
        else:
            score = (
                0.28 * improvement.get("high_pressure_reduction_pct", 0.0)
                + 0.20 * improvement.get("travel_time_reduction_pct", 0.0)
                + 0.18 * improvement.get("emissions_reduction_pct", 0.0)
                + 0.18 * improvement.get("heat_reduction_pct", 0.0)
                + 0.16 * max(0.0, improvement.get("readiness_gain", 0.0))
            )
        return round(float(score), 3)

    def portfolio_explainability(
        self,
        selected_ids: Iterable[str],
        time_window: str = "ingress_peak",
        operations: dict | None = None,
        objective_mode: str = "balanced",
    ) -> dict:
        """Explain portfolio value using standalone and leave-one-out counterfactuals."""
        selected = self._validate_interventions(selected_ids)
        baseline = self.baseline(time_window, operations)
        full = self._calculate(selected, time_window=time_window, operations=operations)
        full_improvement = self.compare(baseline, full)
        full_score = self.score_improvement(full_improvement, objective_mode)
        rows: list[dict] = []
        standalone_total = 0.0
        for intervention_id in selected:
            intervention = self.intervention_map[intervention_id]
            standalone = self._calculate([intervention_id], time_window=time_window, operations=operations)
            standalone_improvement = self.compare(baseline, standalone)
            standalone_score = self.score_improvement(standalone_improvement, objective_mode)
            standalone_total += standalone_score
            without_ids = [item for item in selected if item != intervention_id]
            without = self._calculate(without_ids, time_window=time_window, operations=operations)
            marginal = self.compare(without, full)
            marginal_score = self.score_improvement(marginal, objective_mode)
            rows.append({
                "intervention_id": intervention_id,
                "name": intervention.name,
                "cost_usd": intervention.cost_usd,
                "standalone_improvement": standalone_improvement,
                "standalone_score": standalone_score,
                "marginal_improvement": marginal,
                "marginal_score": marginal_score,
                "marginal_score_per_10000_usd": round(marginal_score / max(1.0, intervention.cost_usd / 10000.0), 3),
                "owner": intervention.owner,
                "lead_time_days": intervention.lead_time_days,
                "implementation_difficulty": intervention.implementation_difficulty,
                "verification_metric": intervention.verification_metric,
            })
        rows.sort(key=lambda item: (item["marginal_score"], -item["cost_usd"]), reverse=True)

        benchmarks: list[dict] = []
        benchmark_sets = {"No intervention": [], **{key.replace("_", " ").title(): value for key, value in PRESETS.items()}}
        for label, intervention_ids in benchmark_sets.items():
            result = self._calculate(intervention_ids, time_window=time_window, operations=operations)
            improvement = self.compare(baseline, result)
            benchmarks.append({
                "label": label,
                "selected_interventions": list(intervention_ids),
                "cost_usd": result["cost_usd"],
                "objective_score": self.score_improvement(improvement, objective_mode),
                "improvement": improvement,
            })
        benchmarks.append({
            "label": "Current portfolio",
            "selected_interventions": selected,
            "cost_usd": full["cost_usd"],
            "objective_score": full_score,
            "improvement": full_improvement,
        })
        benchmarks.sort(key=lambda item: item["objective_score"], reverse=True)
        return {
            "time_window": time_window,
            "objective_mode": objective_mode,
            "selected_interventions": selected,
            "portfolio_cost_usd": full["cost_usd"],
            "portfolio_improvement": full_improvement,
            "portfolio_score": full_score,
            "intervention_contributions": rows,
            "interaction_effect": round(full_score - standalone_total, 3),
            "interaction_interpretation": (
                "Positive values indicate complementary effects; negative values indicate overlap or diminishing returns."
            ),
            "benchmark_portfolios": benchmarks,
            "disclaimer": "Marginal contributions are model counterfactuals, not causal estimates from observed operations.",
        }

    def implementation_playbook(self, selected_ids: Iterable[str]) -> dict:
        """Translate a portfolio into an agency-owned, auditable deployment plan."""
        selected = self._validate_interventions(selected_ids)
        rows: list[dict] = []
        for intervention_id in selected:
            item = self.intervention_map[intervention_id]
            rows.append({
                "intervention_id": item.intervention_id,
                "name": item.name,
                "owner": item.owner,
                "lead_time_days": item.lead_time_days,
                "implementation_difficulty": item.implementation_difficulty,
                "permit_or_approval": item.permit_or_approval,
                "reversible": item.reversible,
                "dependencies": list(item.dependencies),
                "verification_metric": item.verification_metric,
                "cost_usd": item.cost_usd,
                "evidence_gate": (
                    "Verify candidate-site capacity and control before procurement."
                    if item.intervention_id in {"park_ride_shuttle", "rideshare_staging", "cooling_resources"}
                    else "Complete agency engineering and operations review before activation."
                ),
            })
        rows.sort(key=lambda item: item["lead_time_days"], reverse=True)
        longest = max((row["lead_time_days"] for row in rows), default=0)
        timeline = [
            {"phase": f"T-{max(90, longest)} to T-61 days", "action": "Confirm portfolio, executive sponsor, budget ceiling and agency owners.", "gate": "Written scope and data-evidence review."},
            {"phase": "T-60 to T-31 days", "action": "Complete engineering, permits, site agreements, procurement and staffing plans.", "gate": "Signed operating plans and verified site capacities."},
            {"phase": "T-30 to T-8 days", "action": "Configure services, publish traveler guidance, train field teams and finalize incident contingencies.", "gate": "Public communication package and command-center runbook."},
            {"phase": "T-7 to T-1 days", "action": "Run tabletop exercise, field inspection and full data/communications test.", "gate": "Go/no-go review with unresolved risks logged."},
            {"phase": "Event day", "action": "Activate interventions, monitor pressure and queues, and apply manual override thresholds.", "gate": "15-minute operational dashboard and incident log."},
            {"phase": "T+1 to T+14 days", "action": "Reconcile observed outcomes, costs, complaints and safety events; update model parameters.", "gate": "After-action report and reusable event template."},
        ]
        return {
            "selected_interventions": selected,
            "portfolio_lead_time_days": longest,
            "implementation_rows": rows,
            "timeline": timeline,
            "readiness_gates": [
                "All candidate-site capacities and site-control rights verified",
                "Emergency access and ADA route review completed",
                "Transit, Shuttle and rideshare capacities reconciled with modeled demand",
                "Public communication and multilingual wayfinding approved",
                "Real-time monitoring owner and manual override thresholds assigned",
            ],
            "disclaimer": "Owners, lead times and approvals are planning templates and require confirmation by the responsible agencies.",
        }

    def optimize(
        self,
        budget_usd: float,
        required: Iterable[str] | None = None,
        excluded: Iterable[str] | None = None,
        *,
        time_window: str = "ingress_peak",
        operations: dict | None = None,
        objective_mode: str = "balanced",
        minimum_equity_coverage_pct: float = 0.0,
        minimum_accessibility_coverage_pct: float = 0.0,
    ) -> dict:
        if budget_usd < 0:
            raise ValueError("budget_usd must be non-negative")
        self._validate_window(time_window)
        objective_modes = {"balanced", "equity_first", "accessibility_first"}
        if objective_mode not in objective_modes:
            raise ValueError(f"Unknown objective_mode: {objective_mode}")
        if objective_mode != "balanced" and not self.equity_profile:
            raise ValueError("Connect an equity profile before using an equity-aware objective.")
        for label, value in (("minimum_equity_coverage_pct", minimum_equity_coverage_pct), ("minimum_accessibility_coverage_pct", minimum_accessibility_coverage_pct)):
            if value < 0 or value > 100:
                raise ValueError(f"{label} must be between 0 and 100.")
        if (minimum_equity_coverage_pct > 0 or minimum_accessibility_coverage_pct > 0) and not self.equity_profile:
            raise ValueError("Connect an equity profile before applying equity or accessibility constraints.")

        required_set = set(required or [])
        excluded_set = set(excluded or [])
        known = set(self.intervention_map)
        unknown = (required_set | excluded_set) - known
        if unknown:
            raise ValueError(f"Unknown interventions: {sorted(unknown)}")
        overlap = required_set & excluded_set
        if overlap:
            raise ValueError(f"Interventions cannot be both required and excluded: {sorted(overlap)}")

        candidates = [item.intervention_id for item in self.interventions if item.intervention_id not in excluded_set]
        baseline = self.baseline(time_window, operations)
        feasible: list[dict] = []

        for count in range(len(candidates) + 1):
            for combo in itertools.combinations(candidates, count):
                combo_set = set(combo)
                if not required_set.issubset(combo_set):
                    continue
                result = self._calculate(combo, time_window=time_window, operations=operations)
                if result["cost_usd"] > budget_usd:
                    continue
                equity = result.get("equity_metrics", {})
                if minimum_equity_coverage_pct > 0 and float(equity.get("vulnerable_noncar_coverage_pct") or 0.0) < minimum_equity_coverage_pct:
                    continue
                if minimum_accessibility_coverage_pct > 0 and float(equity.get("accessible_public_mode_coverage_pct") or 0.0) < minimum_accessibility_coverage_pct:
                    continue
                improvement = self.compare(baseline, result)
                score = self.score_improvement(improvement, objective_mode)
                result["improvement"] = improvement
                result["objective_score"] = score
                feasible.append(result)

        feasible.sort(key=lambda item: (item["objective_score"], -item["cost_usd"]), reverse=True)
        if feasible:
            best = feasible[0]
        else:
            best = self._calculate([], time_window=time_window, operations=operations)
            best["improvement"] = self.compare(baseline, best)
            best["objective_score"] = 0.0
            best["warning"] = "No intervention portfolio satisfies the current budget and constraints."

        pareto: list[dict] = []
        best_score_so_far = -1e9
        for result in sorted(feasible, key=lambda item: item["cost_usd"]):
            if result["objective_score"] > best_score_so_far:
                pareto.append(
                    {
                        "cost_usd": result["cost_usd"],
                        "objective_score": result["objective_score"],
                        "selected_interventions": result["selected_interventions"],
                    }
                )
                best_score_so_far = result["objective_score"]

        best["pareto_front"] = pareto
        best["robustness"] = self.sensitivity_analysis(best["selected_interventions"], time_window, operations)
        best["decision_policy"] = {
            "objective_mode": objective_mode,
            "minimum_equity_coverage_pct": minimum_equity_coverage_pct,
            "minimum_accessibility_coverage_pct": minimum_accessibility_coverage_pct,
            "equity_profile_connected": bool(self.equity_profile),
        }
        return best

    def intervention_catalog(self) -> list[dict]:
        return [asdict(item) for item in self.interventions]
