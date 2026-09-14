from __future__ import annotations

from .schemas import Edge, Intervention, Zone


def load_demo_zones() -> list[Zone]:
    return [
        Zone("downtown", "Downtown / Fan Zone", 29.7589, -95.3677, 12500, 0.42, 92, 0.28),
        Zone("galleria", "Galleria / Uptown", 29.7407, -95.4636, 10800, 0.58, 96, 0.34),
        Zone("medical", "Texas Medical Center", 29.7078, -95.3975, 6800, 0.38, 95, 0.15),
        Zone("iah", "IAH Airport Area", 29.9931, -95.3418, 5200, 0.67, 91, 0.46),
        Zone("hobby", "Hobby Airport Area", 29.6454, -95.2789, 3900, 0.65, 94, 0.43),
        Zone("eado", "EaDo / East Downtown", 29.7521, -95.3530, 7600, 0.47, 93, 0.26),
    ]


def load_demo_edges() -> list[Edge]:
    return [
        Edge("d1", "downtown", "midtown", "Downtown–Midtown Corridor", 2.1, 9, 1450, 2300, 92),
        Edge("d2", "midtown", "medical", "Main Street / Rail Spine", 2.7, 11, 1550, 2400, 95),
        Edge("d3", "medical", "stadium", "Medical Center–Stadium", 1.8, 8, 1700, 2350, 98),
        Edge("g1", "galleria", "west_loop", "Galleria–West Loop", 3.1, 12, 1950, 2600, 96),
        Edge("g2", "west_loop", "stadium", "West Loop–Stadium", 4.4, 15, 2300, 2800, 99),
        Edge("i1", "iah", "north_corridor", "IAH–North Corridor", 13.0, 24, 2400, 3600, 91),
        Edge("i2", "north_corridor", "downtown", "North Corridor–Downtown", 9.0, 18, 2750, 3900, 93),
        Edge("h1", "hobby", "south_corridor", "Hobby–South Corridor", 5.8, 16, 1850, 2700, 94),
        Edge("h2", "south_corridor", "stadium", "South Corridor–Stadium", 4.5, 14, 2200, 2850, 98),
        Edge("e1", "eado", "midtown", "EaDo–Midtown", 2.4, 10, 1350, 2200, 93),
        Edge("s1", "stadium", "stadium_core", "Stadium Core Access", 0.9, 7, 1850, 2000, 101),
    ]


def load_routes() -> dict[str, dict[str, float]]:
    """Route shares by origin zone. Shares sum to one within each zone."""
    return {
        "downtown": {"d1": 1.0, "d2": 1.0, "d3": 1.0, "s1": 1.0},
        "galleria": {"g1": 1.0, "g2": 1.0, "s1": 1.0},
        "medical": {"d3": 1.0, "s1": 1.0},
        "iah": {"i1": 1.0, "i2": 1.0, "d1": 0.75, "d2": 0.75, "d3": 0.75, "g1": 0.25, "g2": 0.25, "s1": 1.0},
        "hobby": {"h1": 1.0, "h2": 1.0, "s1": 1.0},
        "eado": {"e1": 1.0, "d2": 1.0, "d3": 1.0, "s1": 1.0},
    }


def load_interventions() -> list[Intervention]:
    """Planning interventions with explicit implementation metadata.

    Owners, lead times and approvals are reusable planning templates. They are
    intentionally exposed in the UI so agencies can replace them with local,
    verified operating assumptions.
    """
    return [
        Intervention(
            "vehicle_restriction",
            "2-mile Vehicle Restriction Zone",
            120000,
            "Restrict private-car access near the stadium core and redirect vehicles to managed entry points.",
            {"global_car_share_multiplier": 0.94, "target_flow_multiplier": 0.72},
            ["s1"],
            [],
            owner="Houston Public Works + HPD + venue operations",
            lead_time_days=45,
            implementation_difficulty=4,
            permit_or_approval="Temporary traffic-control plan, enforcement order and emergency-access review",
            dependencies=("signed diversion plan", "managed access points", "public communication campaign"),
            verification_metric="Core-zone private-vehicle entries per 15 minutes",
        ),
        Intervention(
            "park_ride_shuttle",
            "Park-and-Ride Shuttle",
            180000,
            "Shift selected visitor origins from private cars to high-capacity shuttles.",
            {"target_zone_car_share_multiplier": 0.62, "shuttle_vehicle_equivalent": 0.18},
            [],
            ["galleria", "downtown", "iah"],
            owner="METRO + event operator + parking-site operators",
            lead_time_days=60,
            implementation_difficulty=4,
            permit_or_approval="Temporary service plan, site-use agreements and vehicle procurement",
            dependencies=("verified site capacity", "fleet and driver roster", "signed curb/loading plan"),
            verification_metric="Shuttle passengers served and queue wait time",
        ),
        Intervention(
            "bus_only_lane",
            "Temporary Bus-Only Lane",
            140000,
            "Increase effective capacity and reliability on the highest-pressure access corridor.",
            {"target_capacity_multiplier": 1.28},
            ["g2", "d3", "s1"],
            [],
            owner="Houston Public Works + METRO + HPD",
            lead_time_days=60,
            implementation_difficulty=5,
            permit_or_approval="Lane-control plan, traffic engineering review and enforcement staffing",
            dependencies=("corridor feasibility study", "temporary signs and barriers", "incident-response plan"),
            verification_metric="Bus travel-time reliability and lane throughput",
        ),
        Intervention(
            "transit_boost",
            "Transit Frequency Boost",
            160000,
            "Add rail and bus capacity before and after the event window.",
            {"global_car_share_multiplier": 0.84},
            [],
            [],
            owner="METRO service planning and operations",
            lead_time_days=90,
            implementation_difficulty=4,
            permit_or_approval="Special-event service plan, labor schedule and operating budget",
            dependencies=("vehicle availability", "operator staffing", "event-day service calendar"),
            verification_metric="Additional passenger capacity and load factor by trip",
        ),
        Intervention(
            "rideshare_staging",
            "Rideshare Staging Zones",
            80000,
            "Move pick-up and drop-off activity outside the stadium core.",
            {"target_flow_multiplier": 0.86},
            ["s1"],
            [],
            owner="City curb-management team + venue + TNC partners",
            lead_time_days=30,
            implementation_difficulty=3,
            permit_or_approval="Temporary curb-use permit and geofenced pick-up/drop-off agreement",
            dependencies=("verified staging capacity", "driver geofence configuration", "wayfinding and lighting"),
            verification_metric="Pick-up/drop-off throughput and average dwell time",
        ),
        Intervention(
            "pedestrian_guidance",
            "Pedestrian Routing and Wayfinding",
            45000,
            "Distribute pedestrian demand and reduce dwell time at critical crossings.",
            {"travel_time_multiplier": 0.96, "pressure_smoothing": 0.05},
            ["d3", "g2", "h2", "s1"],
            [],
            owner="Venue operations + Public Works + event volunteers",
            lead_time_days=21,
            implementation_difficulty=2,
            permit_or_approval="Temporary wayfinding and pedestrian-management plan",
            dependencies=("accessible route review", "signage production", "staff briefing"),
            verification_metric="Pedestrian queue length and crossing clearance time",
        ),
        Intervention(
            "cooling_resources",
            "Cooling, Water and Medical Points",
            65000,
            "Deploy temporary cooling, hydration and medical resources along exposed corridors.",
            {"heat_exposure_multiplier": 0.72},
            ["d3", "g2", "h2", "s1"],
            [],
            owner="Houston Health Department + fire/EMS + venue medical operations",
            lead_time_days=21,
            implementation_difficulty=2,
            permit_or_approval="Public-health operating plan, site approval and utility/logistics check",
            dependencies=("verified candidate locations", "water and power logistics", "medical escalation protocol"),
            verification_metric="Visitors served, heat-related calls and response time",
        ),
    ]


def demo_city_readiness() -> list[dict]:
    """Synthetic profile for UI demonstration; not a real city ranking."""
    rows = [
        ("Atlanta", 78), ("Boston", 82), ("Dallas", 66), ("Houston", 70),
        ("Kansas City", 61), ("Los Angeles", 68), ("Miami", 65),
        ("New York / New Jersey", 84), ("Philadelphia", 79),
        ("San Francisco Bay Area", 81), ("Seattle", 86),
    ]
    return [
        {
            "city": city,
            "readiness": score,
            "transit_access": min(95, score + 5),
            "last_mile": max(45, score - 3),
            "resilience": max(42, score - 6),
            "heat_risk": max(20, 100 - score + 8),
        }
        for city, score in rows
    ]
