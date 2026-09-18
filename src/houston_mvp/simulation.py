from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .models import MODES, Dataset, ResourceCandidate, Route, Scenario, Zone


ARRIVAL_WINDOW_HOURS = 2.0
STADIUM = {"name": "NRG Stadium", "lat": 29.6847, "lon": -95.4107}

MODE_LAST_MILE_FACTOR = {
    "rail": 0.36,
    "shuttle": 0.28,
    "rideshare": 0.16,
    "walk": 1.0,
    "park": 0.42,
}

MODE_HEAT_EXPOSURE_FACTOR = {
    "rail": 0.62,
    "shuttle": 0.42,
    "rideshare": 0.22,
    "walk": 1.0,
    "park": 0.58,
}

MODE_OCCUPANCY = {
    "rail": 95.0,
    "shuttle": 42.0,
    "rideshare": 2.6,
    "walk": 1.0,
    "park": 3.1,
}


def heat_index_f(temperature_f: float, humidity_pct: float) -> float:
    """NOAA-style heat index approximation in degrees Fahrenheit."""
    t = temperature_f
    rh = humidity_pct
    if t < 80:
        return t

    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * rh
        - 0.22475541 * t * rh
        - 0.00683783 * t * t
        - 0.05481717 * rh * rh
        + 0.00122874 * t * t * rh
        + 0.00085282 * t * rh * rh
        - 0.00000199 * t * t * rh * rh
    )
    return round(hi, 1)


def simulate_all(dataset: Dataset) -> dict[str, Any]:
    scenarios = [simulate_scenario(dataset, scenario) for scenario in dataset.scenarios]
    by_name = {scenario["name"]: scenario for scenario in scenarios}
    baseline = by_name.get("Baseline")
    comparisons = {}

    if baseline:
        for scenario in scenarios:
            comparisons[scenario["name"]] = compare_to_baseline(baseline, scenario)

    return {
        "metadata": {
            "prototype": "FIFA 2026 Houston + NRG Stadium Track 1 + Track 3 MVP",
            "data_status": "Public road inputs with synthetic demand and operating assumptions" if dataset.evidence.get('road_routes') else 'Synthetic sample data; public road inputs unavailable',
            'evidence': dataset.evidence,
            "stadium": STADIUM,
            "total_visitors": sum(zone.visitors for zone in dataset.zones),
        },
        "scenarios": scenarios,
        "comparisons": comparisons,
    }


def simulate_scenario(dataset: Dataset, scenario: Scenario) -> dict[str, Any]:
    routes_by_zone_mode = {
        (route.zone_id, route.mode): route for route in dataset.routes
    }
    heat_index = heat_index_f(scenario.temperature_f, scenario.humidity_pct)
    heat_multiplier = 1.0 + max(0.0, heat_index - 90.0) / 30.0

    assigned: list[dict[str, Any]] = []
    corridor_peak: dict[str, float] = defaultdict(float)
    corridor_capacity: dict[str, float] = {}
    corridor_modes: dict[str, str] = {}

    for zone in dataset.zones:
        shares = apply_mode_shifts(zone, scenario)
        peak_share = max(0.42, zone.peak_share * (1.0 - scenario.peak_smoothing))
        for mode, share in shares.items():
            if share <= 0:
                continue
            route = routes_by_zone_mode.get((zone.zone_id, mode))
            if route is None:
                continue
            visitors = zone.visitors * share
            peak_visitors_per_hour = visitors * peak_share / ARRIVAL_WINDOW_HOURS
            capacity = adjusted_capacity(route, scenario)
            corridor_peak[route.corridor_id] += peak_visitors_per_hour
            corridor_capacity[route.corridor_id] = max(
                capacity, corridor_capacity.get(route.corridor_id, 0)
            )
            corridor_modes[route.corridor_id] = route.mode
            assigned.append(
                {
                    "zone": zone,
                    "route": route,
                    "mode": mode,
                    "share": share,
                    "visitors": visitors,
                    "peak_visitors_per_hour": peak_visitors_per_hour,
                }
            )

    corridor_pressure = {
        corridor_id: corridor_peak[corridor_id] / max(1.0, capacity)
        for corridor_id, capacity in corridor_capacity.items()
    }

    route_outputs = []
    zone_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    mode_totals: dict[str, float] = defaultdict(float)
    total_weighted_minutes = 0.0
    total_weighted_pressure = 0.0
    total_weighted_gap = 0.0
    pedestrian_exposure_index = 0.0
    raw_heat_case_score = 0.0
    rideshare_trips = 0.0

    for item in assigned:
        zone: Zone = item["zone"]
        route: Route = item["route"]
        mode = item["mode"]
        visitors = item["visitors"]
        pressure = corridor_pressure[route.corridor_id]
        effective_shade = min(1.0, route.shade_index + scenario.shade_bonus)
        congestion_penalty = max(0.0, pressure - 0.82) * 0.7
        adjusted_minutes = route.base_minutes * (1.0 + congestion_penalty)

        walk_km = route.distance_km * MODE_LAST_MILE_FACTOR[mode]
        heat_exposure = (
            visitors
            * walk_km
            * MODE_HEAT_EXPOSURE_FACTOR[mode]
            * heat_multiplier
            * (1.18 - effective_shade)
            * (0.82 + zone.vulnerability)
        )
        gap_score = (
            (route.gap_m / 700.0)
            + (1.0 - route.ada_score) * 0.65
            + (1.0 - effective_shade) * 0.4 * heat_multiplier
        ) * MODE_LAST_MILE_FACTOR[mode]

        heat_case_component = heat_exposure / 2400.0
        raw_heat_case_score += heat_case_component
        pedestrian_exposure_index += heat_exposure
        total_weighted_minutes += adjusted_minutes * visitors
        total_weighted_pressure += pressure * visitors
        total_weighted_gap += gap_score * visitors
        mode_totals[mode] += visitors
        if mode == "rideshare":
            rideshare_trips += visitors / MODE_OCCUPANCY[mode]

        zone_total = zone_totals[zone.zone_id]
        zone_total["visitors"] += visitors
        zone_total["gap_weighted"] += gap_score * visitors
        zone_total["exposure"] += heat_exposure
        zone_total["weighted_minutes"] += adjusted_minutes * visitors
        zone_total[f"{mode}_visitors"] += visitors

        route_outputs.append(
            {
                "route_id": route.route_id,
                "zone_id": zone.zone_id,
                "zone_name": zone.name,
                "corridor_id": route.corridor_id,
                "name": route.name,
                "mode": mode,
                "lat1": route.lat1,
                "lon1": route.lon1,
                "lat2": route.lat2,
                "lon2": route.lon2,
                "visitors": round(visitors),
                "peak_visitors_per_hour": round(item["peak_visitors_per_hour"], 1),
                "capacity_per_hour": round(corridor_capacity[route.corridor_id], 1),
                "pressure": round(pressure, 3),
                "distance_km": route.distance_km,
                "base_minutes": route.base_minutes,
                'geometry': route.geometry,
                'route_source': route.route_source,
                'retrieved_at': route.retrieved_at,
                "adjusted_minutes": round(adjusted_minutes, 1),
                "shade_index": round(effective_shade, 3),
                "ada_score": route.ada_score,
                "gap_m": route.gap_m,
                "gap_score": round(gap_score, 3),
                "heat_exposure": round(heat_exposure, 1),
            }
        )

    total_visitors = sum(zone.visitors for zone in dataset.zones)
    resources = place_resources(
        dataset.candidates,
        route_outputs,
        scenario,
        pedestrian_exposure_index,
    )

    resource_summary = summarize_resource_coverage(
        scenario,
        total_visitors,
        pedestrian_exposure_index,
        raw_heat_case_score,
        resources,
    )
    estimated_heat_cases = resource_summary["estimated_heat_cases"]

    zone_outputs = []
    for zone in dataset.zones:
        values = zone_totals[zone.zone_id]
        visitors = max(1.0, values["visitors"])
        zone_outputs.append(
            {
                "zone_id": zone.zone_id,
                "name": zone.name,
                "kind": zone.kind,
                "lat": zone.lat,
                "lon": zone.lon,
                "visitors": round(values["visitors"]),
                "vulnerability": zone.vulnerability,
                "avg_gap_score": round(values["gap_weighted"] / visitors, 3),
                "heat_exposure": round(values["exposure"], 1),
                "avg_minutes": round(values["weighted_minutes"] / visitors, 1),
                "mode_visitors": {
                    mode: round(values.get(f"{mode}_visitors", 0.0)) for mode in MODES
                },
                "notes": zone.notes,
            }
        )

    max_pressure = max((route["pressure"] for route in route_outputs), default=0.0)
    over_capacity = sum(1 for route in route_outputs if route["pressure"] > 1.0)
    avg_minutes = total_weighted_minutes / max(1, total_visitors)
    weighted_pressure = total_weighted_pressure / max(1, total_visitors)
    avg_gap = total_weighted_gap / max(1, total_visitors)
    transit_shuttle_share = (
        mode_totals["rail"] + mode_totals["shuttle"]
    ) / max(1, total_visitors)

    return {
        "name": scenario.name,
        "description": scenario.description,
        "settings": {
            "temperature_f": scenario.temperature_f,
            "humidity_pct": scenario.humidity_pct,
            "heat_index_f": heat_index,
            "peak_smoothing": scenario.peak_smoothing,
            "shade_bonus": scenario.shade_bonus,
            "hydration_units": scenario.hydration_units,
            "cooling_units": scenario.cooling_units,
            "medical_units": scenario.medical_units,
        },
        "kpis": {
            "total_visitors": total_visitors,
            "max_route_pressure": round(max_pressure, 3),
            "weighted_route_pressure": round(weighted_pressure, 3),
            "over_capacity_route_count": over_capacity,
            "avg_first_last_mile_gap": round(avg_gap, 3),
            "avg_travel_minutes": round(avg_minutes, 1),
            "pedestrian_exposure_index": round(pedestrian_exposure_index, 1),
            "estimated_heat_cases": round(estimated_heat_cases, 1),
            "hydration_coverage_pct": resource_summary["hydration_coverage_pct"],
            "cooling_coverage_pct": resource_summary["cooling_coverage_pct"],
            "medical_coverage_pct": resource_summary["medical_coverage_pct"],
            "transit_shuttle_share_pct": round(transit_shuttle_share * 100.0, 1),
            "rideshare_vehicle_trips": round(rideshare_trips),
        },
        "mode_totals": {mode: round(mode_totals[mode]) for mode in MODES},
        "routes": sorted(route_outputs, key=lambda route: route["pressure"], reverse=True),
        "zones": sorted(zone_outputs, key=lambda zone: zone["heat_exposure"], reverse=True),
        "resources": resources,
    }


def apply_mode_shifts(zone: Zone, scenario: Scenario) -> dict[str, float]:
    shares = dict(zone.mode_shares)

    for shift in scenario.mode_shifts:
        eligible_field = shift.get("eligible_field")
        if eligible_field and not bool(getattr(zone, eligible_field)):
            continue

        target = shift["to"]
        sources = shift["from"]
        desired = float(shift["points"])
        available = sum(shares.get(source, 0.0) for source in sources)
        moved = min(desired, available)
        if moved <= 0:
            continue

        for source in sources:
            source_share = shares.get(source, 0.0)
            if source_share <= 0:
                continue
            shares[source] -= moved * (source_share / available)
        shares[target] = shares.get(target, 0.0) + moved

    total = sum(shares.values())
    if total <= 0:
        return {mode: 0.0 for mode in MODES}
    return {mode: max(0.0, shares.get(mode, 0.0) / total) for mode in MODES}


def adjusted_capacity(route: Route, scenario: Scenario) -> float:
    multiplier_by_mode = {
        "rail": scenario.rail_capacity_multiplier,
        "shuttle": scenario.shuttle_capacity_multiplier,
        "rideshare": scenario.rideshare_capacity_multiplier,
        "walk": scenario.walk_capacity_multiplier,
        "park": scenario.park_capacity_multiplier,
    }
    return route.capacity_per_hour * multiplier_by_mode.get(route.mode, 1.0)


def compare_to_baseline(baseline: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, baseline_value in baseline["kpis"].items():
        scenario_value = scenario["kpis"][key]
        delta = scenario_value - baseline_value
        pct = 0.0 if baseline_value == 0 else (delta / baseline_value) * 100.0
        result[key] = {
            "baseline": baseline_value,
            "scenario": scenario_value,
            "delta": round(delta, 3),
            "pct_change": round(pct, 1),
        }
    return result


def place_resources(
    candidates: list[ResourceCandidate],
    routes: list[dict[str, Any]],
    scenario: Scenario,
    pedestrian_exposure_index: float,
) -> list[dict[str, Any]]:
    counts = {
        "hydration": scenario.hydration_units,
        "cooling": scenario.cooling_units,
        "medical": scenario.medical_units,
    }
    placements: dict[tuple[str, str], dict[str, Any]] = {}

    for resource_type, units in counts.items():
        assigned_counts = defaultdict(int)
        for _ in range(units):
            scored = []
            for candidate in candidates:
                load_score = candidate_load_score(candidate, routes, resource_type)
                diminishing = 1.0 + assigned_counts[candidate.candidate_id] * 0.75
                scored.append((load_score / diminishing, candidate, load_score))
            scored.sort(key=lambda item: item[0], reverse=True)
            _, candidate, raw_score = scored[0]
            assigned_counts[candidate.candidate_id] += 1
            key = (candidate.candidate_id, resource_type)
            placements.setdefault(
                key,
                {
                    "candidate_id": candidate.candidate_id,
                    "name": candidate.name,
                    "lat": candidate.lat,
                    "lon": candidate.lon,
                    "category": candidate.category,
                    "resource_type": resource_type,
                    "units": 0,
                    "score": 0.0,
                },
            )
            placements[key]["units"] += 1
            placements[key]["score"] = round(raw_score, 1)

    for placement in placements.values():
        placement["rationale"] = resource_rationale(
            placement["resource_type"], placement["category"], pedestrian_exposure_index
        )

    return sorted(
        placements.values(),
        key=lambda item: (item["resource_type"], -item["units"], -item["score"]),
    )


def candidate_load_score(
    candidate: ResourceCandidate, routes: list[dict[str, Any]], resource_type: str
) -> float:
    score = candidate.base_priority * 120.0
    for route in routes:
        near_origin = haversine_km(candidate.lat, candidate.lon, route["lat1"], route["lon1"])
        near_destination = haversine_km(candidate.lat, candidate.lon, route["lat2"], route["lon2"])
        proximity = 1.0 / (1.0 + min(near_origin, near_destination) * 2.8)
        route_pressure = route["pressure"]
        heat = route["heat_exposure"] / 1000.0
        visitors = route["visitors"] / 1000.0
        gap = route["gap_score"]

        if resource_type == "hydration":
            score += proximity * (heat * 1.15 + visitors * 0.8 + gap * 18)
        elif resource_type == "cooling":
            score += proximity * (heat * 1.4 + route_pressure * 24 + gap * 16)
        else:
            score += proximity * (heat * 0.9 + route_pressure * 35 + visitors * 0.7)

    category_bonus = {
        "hydration": {
            "station": 1.1,
            "pedestrian_approach": 1.08,
            "holding_area": 1.06,
        },
        "cooling": {
            "holding_area": 1.12,
            "offsite_fan_zone": 1.08,
            "pedestrian_approach": 1.06,
        },
        "medical": {
            "venue_gate": 1.12,
            "rideshare": 1.08,
            "station": 1.06,
        },
    }
    return score * category_bonus.get(resource_type, {}).get(candidate.category, 1.0)


def resource_rationale(resource_type: str, category: str, exposure_index: float) -> str:
    if resource_type == "hydration":
        return "Prioritized for high pedestrian throughput and heat-weighted walking exposure."
    if resource_type == "cooling":
        return "Prioritized for dwell, shade gaps, and heat exposure near queues or holding areas."
    return "Prioritized for route pressure, crowd concentration, and rapid response coverage."


def summarize_resource_coverage(
    scenario: Scenario,
    total_visitors: int,
    pedestrian_exposure_index: float,
    raw_heat_case_score: float,
    resources: list[dict[str, Any]],
) -> dict[str, float]:
    hydration_units = sum(
        item["units"] for item in resources if item["resource_type"] == "hydration"
    )
    cooling_units = sum(
        item["units"] for item in resources if item["resource_type"] == "cooling"
    )
    medical_units = sum(
        item["units"] for item in resources if item["resource_type"] == "medical"
    )

    exposed_visitors_equivalent = max(1.0, pedestrian_exposure_index / 8.5)
    hydration_coverage = min(0.98, hydration_units * 3300.0 / exposed_visitors_equivalent)
    cooling_coverage = min(0.96, cooling_units * 2400.0 / exposed_visitors_equivalent)
    medical_coverage = min(0.95, medical_units * 11500.0 / max(1.0, total_visitors))

    mitigation = (
        hydration_coverage * 0.28
        + cooling_coverage * 0.3
        + medical_coverage * 0.16
        + min(0.12, scenario.peak_smoothing * 0.45)
    )
    estimated_heat_cases = max(0.0, raw_heat_case_score * (1.0 - mitigation))

    return {
        "hydration_coverage_pct": round(hydration_coverage * 100.0, 1),
        "cooling_coverage_pct": round(cooling_coverage * 100.0, 1),
        "medical_coverage_pct": round(medical_coverage * 100.0, 1),
        "estimated_heat_cases": estimated_heat_cases,
    }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    return radius * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
