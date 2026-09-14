from __future__ import annotations

from datetime import datetime, timezone

from .advisor import generate_action_plan


def build_submission_package(
    model,
    *,
    budget_usd: float,
    required: list[str] | None = None,
    excluded: list[str] | None = None,
    time_window: str = "ingress_peak",
    operations: dict | None = None,
    objective_mode: str = "balanced",
    minimum_equity_coverage_pct: float = 0.0,
    minimum_accessibility_coverage_pct: float = 0.0,
) -> dict:
    optimization = model.optimize(
        budget_usd,
        required or [],
        excluded or [],
        time_window=time_window,
        operations=operations,
        objective_mode=objective_mode,
        minimum_equity_coverage_pct=minimum_equity_coverage_pct,
        minimum_accessibility_coverage_pct=minimum_accessibility_coverage_pct,
    )
    selected = optimization.get("selected_interventions", [])
    explainability = model.portfolio_explainability(selected, time_window, operations, objective_mode)
    implementation = model.implementation_playbook(selected)
    validation = model.validation_report()
    audit = model.baseline_audit()
    action_plan = generate_action_plan(optimization, budget_usd)
    improvement = optimization.get("improvement", {})
    metrics = optimization.get("metrics", {})

    executive_summary = (
        "EventFlow AI Command Center treats FIFA 2026 as a reproducible urban-mobility stress test. "
        "The platform estimates visitor-origin demand, assigns flows to road and transit networks, identifies "
        "first/last-mile bottlenecks, and evaluates bounded intervention portfolios under budget, operational, "
        "equity and accessibility constraints. For the Houston / NRG Stadium case, the recommended portfolio "
        f"uses ${optimization.get('cost_usd', 0):,.0f} of a ${budget_usd:,.0f} budget and improves the modeled "
        f"readiness score by {improvement.get('readiness_gain', 0):.1f} points."
    )

    methodology = [
        "Estimate zone-level event demand from POI, store-visit, spending, venue-capacity and event-window signals.",
        "Assign multimodal visitor flows to road, transit, Shuttle, rideshare and walk/bike options with explicit capacity limits.",
        "Calculate link pressure as baseline flow plus event-added flow divided by modeled road capacity.",
        "Simulate traffic-management, transit, curb, pedestrian and heat-mitigation interventions with transparent effect parameters.",
        "Search feasible intervention combinations under budget and policy constraints, then test robustness across 81 uncertainty cases.",
        "Generate an agency-owned implementation playbook and grounded action plan from deterministic model outputs.",
    ]

    key_findings = [
        f"Modeled high-pressure segments fall by {improvement.get('high_pressure_reduction_pct', 0):.1f}% under the recommended portfolio.",
        f"Average network travel time falls by {improvement.get('travel_time_reduction_pct', 0):.1f}%.",
        f"The emissions index falls by {improvement.get('emissions_reduction_pct', 0):.1f}% and heat exposure falls by {improvement.get('heat_reduction_pct', 0):.1f}%.",
        f"The recommended portfolio retains {metrics.get('critical_segments', 0)} modeled segment(s) above capacity and a worst modeled pressure of {metrics.get('max_pressure', 0):.2f}.",
        f"The 10th-percentile readiness score across sensitivity runs is {optimization.get('robustness', {}).get('robustness_score', 0):.1f}.",
    ]
    equity = optimization.get("equity_metrics", {})
    if equity.get("profile_connected"):
        key_findings.append(
            f"Vulnerability-weighted non-car coverage reaches {equity.get('vulnerable_noncar_coverage_pct', 0):.1f}% and the accessibility-support proxy reaches {equity.get('accessible_public_mode_coverage_pct', 0):.1f}%."
        )

    judging_alignment = {
        "Impact": "Quantifies congestion, travel-time, emissions, heat and distributional outcomes before and after intervention.",
        "Data Analytics": "Combines multi-source spatial data, OD demand calibration, route assignment, capacity-constrained mode shift, sensitivity analysis and counterfactual evaluation.",
        "Innovation": "Moves from static mapping to an explainable scenario optimizer, marginal-contribution analysis and grounded AI action plan.",
        "Feasibility / Implementation": "Assigns agency owners, lead times, approvals, dependencies, verification metrics and go/no-go gates to every selected intervention.",
        "Legacy": "Uses reusable city, venue, event-window, intervention and evidence profiles for future sports, concerts, marathons and conventions.",
        "Visualization": "Supports network pressure maps, before/after metrics, Pareto frontiers, equity screening and implementation timelines.",
        "Presentation / Pitch": "Provides a concise executive summary, evidence package, implementation playbook and demo-ready decision story.",
    }

    limitations = [
        "Hackathon activity data is anonymized and perturbed; demand estimates are planning proxies.",
        "Intervention effect sizes, costs, owners and lead times remain editable planning assumptions until agency validation.",
        "Zone-level accessibility screening does not establish route-level or legal ADA compliance.",
        "Cross-city readiness values remain illustrative until each city receives the same reproducible evidence pipeline.",
        "The prototype supports pre-event planning and does not replace real-time traffic control or emergency command authority.",
    ]

    package = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "title": "EventFlow AI Command Center",
            "subtitle": "AI-assisted mobility scenario planning for mega-event host cities",
            "case_study": "Houston / NRG Stadium — FIFA World Cup 2026",
            "track": "Track 1: Transportation & Access, with Track 3 heat and public-health integration",
        },
        "executive_summary": executive_summary,
        "methodology": methodology,
        "key_findings": key_findings,
        "recommended_portfolio": optimization,
        "portfolio_explainability": explainability,
        "implementation_playbook": implementation,
        "action_plan": action_plan,
        "validation": validation,
        "audit": audit,
        "judging_alignment": judging_alignment,
        "limitations": limitations,
    }
    package["markdown"] = render_submission_markdown(package)
    return package


def render_submission_markdown(package: dict) -> str:
    project = package["project"]
    optimization = package["recommended_portfolio"]
    implementation = package["implementation_playbook"]
    explainability = package["portfolio_explainability"]
    lines = [
        f"# {project['title']}",
        f"## {project['subtitle']}",
        "",
        f"**Case study:** {project['case_study']}  ",
        f"**Competition alignment:** {project['track']}",
        "",
        "## Executive Summary",
        package["executive_summary"],
        "",
        "## Methodology",
    ]
    lines.extend(f"{index}. {item}" for index, item in enumerate(package["methodology"], start=1))
    lines.extend(["", "## Key Findings"])
    lines.extend(f"- {item}" for item in package["key_findings"])
    lines.extend(["", "## Recommended Portfolio"])
    for name in optimization.get("selected_names", []):
        lines.append(f"- {name}")
    lines.extend([
        "",
        f"**Modeled cost:** ${optimization.get('cost_usd', 0):,.0f}",
        f"**Portfolio score:** {explainability.get('portfolio_score', 0):.2f}",
        f"**Robustness P10:** {optimization.get('robustness', {}).get('robustness_score', 0):.1f}",
        "",
        "## Marginal Contribution",
        "| Intervention | Cost | Marginal score | Score / $10k | Lead time | Owner |",
        "|---|---:|---:|---:|---:|---|",
    ])
    for row in explainability.get("intervention_contributions", []):
        lines.append(
            f"| {row['name']} | ${row['cost_usd']:,.0f} | {row['marginal_score']:.2f} | {row['marginal_score_per_10000_usd']:.2f} | {row['lead_time_days']} days | {row['owner']} |"
        )
    lines.extend(["", "## Implementation Playbook"])
    for row in implementation.get("implementation_rows", []):
        deps = "; ".join(row.get("dependencies", []))
        lines.append(
            f"- **{row['name']}** — Owner: {row['owner']}; lead time: {row['lead_time_days']} days; approval: {row['permit_or_approval']}; dependencies: {deps}; verification: {row['verification_metric']}."
        )
    lines.extend(["", "## Competition Criteria Alignment"])
    for criterion, description in package["judging_alignment"].items():
        lines.append(f"- **{criterion}:** {description}")
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {item}" for item in package["limitations"])
    lines.extend(["", "## Legacy"])
    lines.append(
        "The same data, network, intervention and evidence framework can be configured for the Super Bowl, concerts, marathons, conventions, festivals, university game days and heat-emergency planning."
    )
    return "\n".join(lines) + "\n"
