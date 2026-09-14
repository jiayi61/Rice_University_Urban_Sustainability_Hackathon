from __future__ import annotations


def generate_action_plan(result: dict, budget_usd: float) -> dict:
    improvement = result.get("improvement", {})
    metrics = result["metrics"]
    names = result.get("selected_names", [])
    robustness = result.get("robustness", {})
    feasibility = result.get("operational_feasibility", {})
    equity = result.get("equity_metrics", {})
    policy = result.get("decision_policy", {})

    priorities = [
        {"priority": index, "action": name}
        for index, name in enumerate(names, start=1)
    ]
    if not priorities:
        priorities.append(
            {
                "priority": 1,
                "action": "Collect additional traffic, transit and event-demand data before committing capital.",
            }
        )

    time_label = result.get("time_window_label", "Ingress peak")
    robustness_score = robustness.get("robustness_score")
    robustness_text = (
        f" The 10th-percentile readiness score across 81 sensitivity runs is {robustness_score:.1f}."
        if isinstance(robustness_score, (int, float))
        else ""
    )
    rationale = (
        f"For the {time_label.lower()} window, the recommended portfolio uses "
        f"${result['cost_usd']:,.0f} of the ${budget_usd:,.0f} budget. "
        f"It improves readiness by {improvement.get('readiness_gain', 0):.1f} points, "
        f"reduces modeled travel time by {improvement.get('travel_time_reduction_pct', 0):.1f}%, "
        f"reduces emissions by {improvement.get('emissions_reduction_pct', 0):.1f}%, "
        f"and reduces heat exposure by {improvement.get('heat_reduction_pct', 0):.1f}%."
        + (
            f" It improves non-car coverage for vulnerability-weighted demand by {improvement.get('vulnerable_noncar_coverage_gain', 0):.1f} points "
            f"and the accessibility-support proxy by {improvement.get('accessibility_coverage_gain', 0):.1f} points."
            if equity.get("profile_connected") else ""
        )
        + f"{robustness_text}"
    )

    remaining_risk = []
    if metrics["critical_segments"] > 0:
        remaining_risk.append(
            f"{metrics['critical_segments']} modeled road segment(s) remain above capacity."
        )
    if metrics["max_pressure"] >= 0.95:
        remaining_risk.append(
            "The stadium core remains sensitive to late arrivals, incidents and compressed post-match departures."
        )
    if robustness_score is not None and robustness_score < 60:
        remaining_risk.append(
            "The portfolio is sensitive to uncertainty in attendance, car share and road capacity; retain operational contingencies."
        )
    unmet_shift = float(feasibility.get("total_unmet_shift_demand", 0) or 0)
    if unmet_shift > 0:
        remaining_risk.append(
            f"Operational capacity leaves approximately {unmet_shift:,.0f} intended mode-shift riders unserved; increase fleet or transit capacity before deployment."
        )
    shuttle = feasibility.get("shuttle", {})
    if shuttle.get("active") and shuttle.get("candidate_sites_connected"):
        fleet_cap = float(shuttle.get("fleet_capacity_riders", 0) or 0)
        site_cap = float(shuttle.get("candidate_site_capacity_riders", 0) or 0)
        if site_cap <= 0:
            remaining_risk.append(
                "Connected Park-and-Ride locations do not yet contain a usable capacity value; Shuttle service remains unserved until throughput is verified or entered as an explicit planning assumption."
            )
        elif site_cap < fleet_cap:
            remaining_risk.append(
                f"Park-and-Ride site throughput ({site_cap:,.0f} riders) constrains the modeled fleet capacity ({fleet_cap:,.0f} riders)."
            )
        configured_cycle = float(shuttle.get("configured_cycle_minutes", 0) or 0)
        effective_cycle = float(shuttle.get("effective_cycle_minutes", 0) or 0)
        if effective_cycle > configured_cycle + 1:
            remaining_risk.append(
                f"Road-network routing raises the Shuttle cycle from {configured_cycle:.0f} to {effective_cycle:.0f} minutes; fleet planning should use the longer cycle."
            )
    if policy.get("objective_mode") in {"equity_first", "accessibility_first"}:
        remaining_risk.append(
            f"The optimizer used the {policy.get('objective_mode').replace('_', '-')} policy; verify distributional impacts with community and accessibility stakeholders before implementation."
        )
    if equity.get("profile_connected"):
        access_cov = float(equity.get("accessible_public_mode_coverage_pct") or 0.0)
        if access_cov < 35:
            remaining_risk.append(
                f"The accessibility-support coverage proxy remains {access_cov:.1f}%; route-level sidewalks, curb ramps, boarding paths and accessible vehicle availability require additional validation."
            )
    else:
        remaining_risk.append(
            "No zone-level equity profile is connected; distributional impacts are not included in the recommendation."
        )

    if not remaining_risk:
        remaining_risk.append(
            "No critical modeled segment remains, but real-time monitoring and manual override remain necessary."
        )

    return {
        "title": f"Houston {time_label} Action Plan",
        "priorities": priorities,
        "rationale": rationale,
        "expected_impact": improvement,
        "remaining_risk": remaining_risk,
        "robustness": robustness,
        "operational_feasibility": feasibility,
        "disclaimer": (
            "Generated only from deterministic scenario outputs and bounded sensitivity tests. "
            "It is a planning prototype, not an operational traffic forecast."
        ),
    }
