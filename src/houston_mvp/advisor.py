from __future__ import annotations

from typing import Any


LOWER_IS_BETTER = {
    "max_route_pressure",
    "weighted_route_pressure",
    "over_capacity_route_count",
    "avg_first_last_mile_gap",
    "avg_travel_minutes",
    "pedestrian_exposure_index",
    "estimated_heat_cases",
    "rideshare_vehicle_trips",
}


def attach_advice(payload: dict[str, Any]) -> dict[str, Any]:
    scenarios = payload["scenarios"]
    by_name = {scenario["name"]: scenario for scenario in scenarios}
    baseline = by_name.get("Baseline", scenarios[0])

    scores = []
    for scenario in scenarios:
        scenario["advisor"] = scenario_advice(baseline, scenario)
        if scenario["name"] != "Baseline":
            scores.append((scenario_score(baseline, scenario), scenario["name"]))

    scores.sort(reverse=True)
    best_name = scores[0][1] if scores else baseline["name"]
    best = by_name[best_name]

    payload["advisor"] = {
        "recommended_scenario": best_name,
        "summary": recommendation_summary(baseline, best),
        "ranking": [
            {"scenario": name, "score": round(score, 2)} for score, name in scores
        ],
        "method": "Deterministic rule layer using KPI deltas, route pressure hotspots, exposure hotspots, and resource coverage.",
    }
    return payload


def scenario_score(baseline: dict[str, Any], scenario: dict[str, Any]) -> float:
    weights = {
        "estimated_heat_cases": 2.0,
        "max_route_pressure": 1.7,
        "weighted_route_pressure": 1.2,
        "avg_first_last_mile_gap": 1.1,
        "avg_travel_minutes": 0.7,
        "rideshare_vehicle_trips": 0.8,
        "transit_shuttle_share_pct": 0.7,
    }
    score = 0.0
    for key, weight in weights.items():
        base = baseline["kpis"][key]
        value = scenario["kpis"][key]
        if base == 0:
            continue
        if key in LOWER_IS_BETTER:
            improvement = (base - value) / base
        else:
            improvement = (value - base) / base
        score += improvement * weight * 100.0
    return score


def scenario_advice(baseline: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    kpis = scenario["kpis"]
    baseline_kpis = baseline["kpis"]
    top_routes = scenario["routes"][:3]
    top_zones = scenario["zones"][:3]

    actions = []
    max_pressure_route = top_routes[0] if top_routes else None
    heat_zone = top_zones[0] if top_zones else None

    if max_pressure_route and max_pressure_route["pressure"] > 1.0:
        actions.append(
            {
                "priority": "high",
                "title": f"Relieve {max_pressure_route['name']}",
                "explanation": (
                    f"{max_pressure_route['zone_name']} sends about "
                    f"{max_pressure_route['visitors']:,} visitors through a corridor at "
                    f"{max_pressure_route['pressure']:.2f} pressure. Add capacity, spread arrivals, "
                    "or redirect demand to rail or shuttle alternatives."
                ),
            }
        )
    elif max_pressure_route:
        actions.append(
            {
                "priority": "medium",
                "title": "Keep route pressure monitoring active",
                "explanation": (
                    f"The highest modeled pressure is {max_pressure_route['pressure']:.2f} on "
                    f"{max_pressure_route['name']}. This is below the hard capacity threshold but still "
                    "sensitive to late arrivals."
                ),
            }
        )

    if heat_zone:
        actions.append(
            {
                "priority": "high",
                "title": f"Protect pedestrians from {heat_zone['name']}",
                "explanation": (
                    f"{heat_zone['name']} has the largest heat exposure index in this scenario "
                    f"({heat_zone['heat_exposure']:,.0f}). Place hydration, shade, cooling, and medical "
                    "coverage along the relevant approach segments."
                ),
            }
        )

    heat_delta = baseline_kpis["estimated_heat_cases"] - kpis["estimated_heat_cases"]
    pressure_delta = baseline_kpis["max_route_pressure"] - kpis["max_route_pressure"]
    if scenario["name"] != "Baseline":
        actions.append(
            {
                "priority": "medium",
                "title": "Use KPI deltas in the operations briefing",
                "explanation": (
                    f"Compared with Baseline, this scenario changes estimated heat cases by "
                    f"{heat_delta:+.1f} and max route pressure by {pressure_delta:+.2f}. "
                    "These are deterministic model outputs, not AI guesses."
                ),
            }
        )

    return {
        "headline": scenario_headline(baseline, scenario),
        "actions": actions,
    }


def scenario_headline(baseline: dict[str, Any], scenario: dict[str, Any]) -> str:
    if scenario["name"] == "Baseline":
        return "Baseline shows the unmitigated pressure and heat-exposure reference case."

    heat_change = pct_change(
        baseline["kpis"]["estimated_heat_cases"], scenario["kpis"]["estimated_heat_cases"]
    )
    pressure_change = pct_change(
        baseline["kpis"]["max_route_pressure"], scenario["kpis"]["max_route_pressure"]
    )
    transit_change = scenario["kpis"]["transit_shuttle_share_pct"] - baseline["kpis"][
        "transit_shuttle_share_pct"
    ]

    return (
        f"{scenario['name']} changes heat cases by {heat_change:+.1f}%, "
        f"max pressure by {pressure_change:+.1f}%, and transit/shuttle share by "
        f"{transit_change:+.1f} points versus Baseline."
    )


def recommendation_summary(baseline: dict[str, Any], best: dict[str, Any]) -> str:
    heat_change = pct_change(
        baseline["kpis"]["estimated_heat_cases"], best["kpis"]["estimated_heat_cases"]
    )
    pressure_change = pct_change(
        baseline["kpis"]["max_route_pressure"], best["kpis"]["max_route_pressure"]
    )
    gap_change = pct_change(
        baseline["kpis"]["avg_first_last_mile_gap"],
        best["kpis"]["avg_first_last_mile_gap"],
    )
    return (
        f"Recommend {best['name']} for the prototype briefing: it reduces estimated heat cases "
        f"by {abs(heat_change):.1f}%, max route pressure by {abs(pressure_change):.1f}%, "
        f"and first/last-mile gap score by {abs(gap_change):.1f}% versus Baseline."
    )


def pct_change(baseline_value: float, scenario_value: float) -> float:
    if baseline_value == 0:
        return 0.0
    return ((scenario_value - baseline_value) / baseline_value) * 100.0
