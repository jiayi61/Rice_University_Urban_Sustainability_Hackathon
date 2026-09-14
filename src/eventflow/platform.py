"""Reusable planning engine for the EventFlow v2 decision surface.

This module intentionally separates event configuration, data provenance,
cost assumptions, simulation, and presentation payloads. A new event can be
added through the catalog without rebuilding the Houston-specific UI.
"""
from __future__ import annotations

import csv
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any


TIME_POINTS = [-180, -150, -120, -90, -60, -30, 0, 30, 60, 90, 120]

SOURCES = [
    {
        "id": "rice_catalog",
        "name": "Rice University World Cup U.S. Cities Spatial Data",
        "kind": "source catalog",
        "url": "https://github.com/HoustonSI/WorldCupUSSpatialData101",
        "use": "City, county, regional, state, transit and national acquisition registry for all 11 U.S. host cities.",
    },
    {
        "id": "metro_gtfs",
        "name": "METRO Houston GTFS",
        "kind": "transit network snapshot",
        "url": "https://mobilitydatabase.org/feeds/gtfs/mdb-2060",
        "use": "109 representative bus and rail route shapes, nearby stops and route metadata; snapshot 2026-09-01.",
    },
    {
        "id": "metro_nrg",
        "name": "METRO service to Reliant Park",
        "kind": "official service and fare data",
        "url": "https://www.ridemetro.org/riding-metro/houston-attractions/reliant-park",
        "use": "Red Line, Routes 14/60/84, service frequencies, $1.25 fare and Fannin South event parking range.",
    },
    {
        "id": "transtar",
        "name": "Houston TranStar feeds",
        "kind": "live/historical traffic",
        "url": "https://traffic.houstontranstar.org/api/api_doc.aspx",
        "use": "Production connector target for minute-level speeds, incidents, closures and flood-risk points.",
    },
    {
        "id": "txdot",
        "name": "TxDOT STARS II and Open Data",
        "kind": "traffic counts and infrastructure",
        "url": "https://www.txdot.gov/data-maps/traffic-count-maps.html",
        "use": "Road-volume calibration, roadway inventory and historical count validation.",
    },
    {
        "id": "fta_cost",
        "name": "FTA 2024 agency profile 60008",
        "kind": "operating-cost benchmark",
        "url": "https://www.transit.dot.gov/sites/fta.dot.gov/files/transit_agency_profile_doc/2024/60008.pdf",
        "use": "Vehicle-revenue-hour anchors: bus $177.51, commuter bus $275.81 and light rail $397.61.",
    },
    {
        "id": "osm_osrm",
        "name": "OpenStreetMap + OSRM",
        "kind": "basemap and road routing",
        "url": "https://www.openstreetmap.org/",
        "use": "Legal basemap and street-routed origin-to-venue corridor geometries.",
    },
    {
        "id": "nominatim_overpass",
        "name": "OSM Nominatim + Overpass",
        "kind": "global place and infrastructure discovery",
        "url": "https://nominatim.org/",
        "use": "Resolve user-described venues and discover nearby rail stations, bus stations and parking facilities; low-volume requests are cached.",
    },
    {
        "id": "open_meteo",
        "name": "Open-Meteo Historical Weather",
        "kind": "climate-normal context",
        "url": "https://open-meteo.com/",
        "use": "Historical temperature, rain and wind context around the future event's calendar date.",
    },
    {
        "id": "frankfurter",
        "name": "Frankfurter currency data",
        "kind": "reference exchange rates",
        "url": "https://frankfurter.dev/",
        "use": "Translate transferable planning cost anchors into the event city's local currency.",
    },
]


CITY_PROFILES = [
    ("atlanta", "Atlanta", "Mercedes-Benz Stadium", 33.7554, -84.4008, 74, 65, 70, 60, 78),
    ("boston", "Boston", "Gillette Stadium", 42.0909, -71.2643, 46, 58, 39, 72, 82),
    ("dallas", "Dallas", "AT&T Stadium", 32.7473, -97.0945, 38, 72, 42, 55, 74),
    ("houston", "Houston", "Houston Stadium", 29.6847, -95.4107, 67, 78, 73, 48, 91),
    ("kansas_city", "Kansas City", "Arrowhead Stadium", 39.0489, -94.4839, 34, 64, 40, 62, 70),
    ("los_angeles", "Los Angeles", "SoFi Stadium", 33.9535, -118.3392, 58, 51, 55, 50, 88),
    ("miami", "Miami", "Hard Rock Stadium", 25.9580, -80.2389, 32, 61, 37, 38, 77),
    ("new_york_nj", "New York / New Jersey", "MetLife Stadium", 40.8135, -74.0745, 69, 55, 57, 68, 93),
    ("philadelphia", "Philadelphia", "Lincoln Financial Field", 39.9008, -75.1675, 86, 63, 81, 66, 86),
    ("san_francisco", "San Francisco Bay Area", "Levi's Stadium", 37.4030, -121.9700, 75, 59, 68, 64, 87),
    ("seattle", "Seattle", "Lumen Field", 47.5952, -122.3316, 91, 62, 88, 79, 90),
]


EVENTS = [
    {
        "event_id": "houston_wc26",
        "city_id": "houston",
        "name": "FIFA World Cup 2026 — Houston Stadium",
        "short_name": "World Cup match",
        "event_type": "international_football",
        "date": "2026-06-17",
        "start_time": "15:00",
        "attendance": 68777,
        "status": "calibrated template",
        "weather": {"temperature_f": 96, "humidity_pct": 58, "heat_index_f": 108},
    },
    {
        "event_id": "houston_texans",
        "city_id": "houston",
        "name": "Future Houston Texans home game",
        "short_name": "NFL game template",
        "event_type": "american_football",
        "date": "future date",
        "start_time": "12:00",
        "attendance": 70000,
        "status": "reusable forecast template",
        "weather": {"temperature_f": 88, "humidity_pct": 56, "heat_index_f": 94},
    },
    {
        "event_id": "houston_rodeo",
        "city_id": "houston",
        "name": "Future RodeoHouston peak night",
        "short_name": "Rodeo template",
        "event_type": "rodeo_concert",
        "date": "future date",
        "start_time": "18:45",
        "attendance": 72000,
        "status": "reusable forecast template",
        "weather": {"temperature_f": 76, "humidity_pct": 54, "heat_index_f": 76},
    },
    {
        "event_id": "houston_concert",
        "city_id": "houston",
        "name": "Future sold-out stadium concert",
        "short_name": "Concert template",
        "event_type": "stadium_concert",
        "date": "future date",
        "start_time": "20:00",
        "attendance": 65000,
        "status": "reusable forecast template",
        "weather": {"temperature_f": 90, "humidity_pct": 61, "heat_index_f": 99},
    },
]


PLAN_DEFINITIONS = [
    {
        "plan_id": "efficient",
        "name": "Lean operations",
        "label": "Lowest cost",
        "description": "Exploit existing rail and curb assets first; target the largest gaps with limited new operations.",
        "relief": 0.17,
        "coverage": 0.63,
        "delay_reduction": 0.16,
        "emissions_reduction": 0.12,
        "heat_reduction": 0.20,
        "robustness": 76,
        "equity": 68,
        "action_ids": ["rail", "bus_priority", "pudo", "wayfinding", "heat"],
    },
    {
        "plan_id": "balanced",
        "name": "Network balance",
        "label": "Recommended",
        "description": "Pair high-frequency rail with event shuttles, adaptive traffic control and protected last-mile paths.",
        "relief": 0.31,
        "coverage": 0.84,
        "delay_reduction": 0.29,
        "emissions_reduction": 0.24,
        "heat_reduction": 0.43,
        "robustness": 88,
        "equity": 86,
        "action_ids": ["rail", "shuttle", "bus_priority", "signals", "park_ride", "pudo", "walk", "heat"],
    },
    {
        "plan_id": "resilient",
        "name": "Maximum resilience",
        "label": "Highest impact",
        "description": "Add reserve capacity and redundancy so rail, roadway or heat disruptions do not break the event plan.",
        "relief": 0.43,
        "coverage": 0.95,
        "delay_reduction": 0.41,
        "emissions_reduction": 0.35,
        "heat_reduction": 0.61,
        "robustness": 95,
        "equity": 92,
        "action_ids": ["rail", "shuttle_max", "bus_lane", "signals_max", "park_ride_max", "pudo", "walk_max", "heat_max", "reserve"],
    },
]


def _pulse(minute: int) -> float:
    ingress = math.exp(-((minute + 48) / 54) ** 2)
    egress = 0.91 * math.exp(-((minute - 38) / 38) ** 2)
    return round(0.08 + 0.92 * max(ingress, egress), 4)


class MobilityPlatform:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.spatial_path = self.root / "data" / "local" / "spatial_layers.json"
        self.zone_path = self.root / "data" / "houston_nrg" / "zones.csv"
        self.spatial = json.loads(self.spatial_path.read_text(encoding="utf-8"))
        self.zones = self._load_zones()
        self.city_profiles = self._build_city_profiles()

    def _load_zones(self) -> list[dict[str, Any]]:
        with self.zone_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return [{
            **row,
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "visitors": int(float(row["visitors"])),
            "vulnerability": float(row["vulnerability"]),
            "base_visitors": int(float(row["visitors"])),
        } for row in rows]

    @staticmethod
    def _build_city_profiles() -> list[dict[str, Any]]:
        profiles = []
        for city_id, city, venue, lat, lon, transit, road, last_mile, climate, data in CITY_PROFILES:
            readiness = round(0.29 * transit + 0.19 * road + 0.19 * last_mile + 0.14 * climate + 0.19 * data)
            profiles.append({
                "city_id": city_id,
                "city": city,
                "venue": venue,
                "venue_lat": lat,
                "venue_lon": lon,
                "scores": {
                    "transit_access": transit,
                    "road_redundancy": road,
                    "last_mile": last_mile,
                    "climate_resilience": climate,
                    "data_maturity": data,
                    "readiness": readiness,
                },
                "priority_gap": min(
                    (("Transit access", transit), ("Road redundancy", road), ("Last mile", last_mile), ("Climate", climate)),
                    key=lambda item: item[1],
                )[0],
                "confidence": "screening",
            })
        return profiles

    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": "2.0",
            "default_event_id": "houston_wc26",
            "events": EVENTS,
            "cities": self.city_profiles,
            "sources": SOURCES,
            "data_policy": {
                "automatic_inputs": ["event template", "venue", "street network", "GTFS transit", "cost anchors", "weather scenario"],
                "production_connectors": ["Houston TranStar", "TxDOT counts", "agency GTFS/GTFS-RT", "Census/ACS", "weather"],
                "note": "Estimates are decision-support ranges, not procurement bids or guaranteed travel times.",
            },
        }

    def _event(self, event_id: str) -> dict[str, Any]:
        event = next((item for item in EVENTS if item["event_id"] == event_id), None)
        if event is None:
            raise ValueError(f"Unknown event_id: {event_id}")
        return deepcopy(event)

    def _scaled_zones(self, attendance: int) -> list[dict[str, Any]]:
        base_total = sum(row["base_visitors"] for row in self.zones)
        scale = attendance / base_total
        result = []
        assigned = 0
        for index, row in enumerate(self.zones):
            visitors = round(row["base_visitors"] * scale)
            if index == len(self.zones) - 1:
                visitors = attendance - assigned
            assigned += visitors
            result.append({
                "zone_id": row["zone_id"],
                "name": row["name"],
                "kind": row["kind"],
                "lat": row["lat"],
                "lon": row["lon"],
                "visitors": visitors,
                "vulnerability": row["vulnerability"],
                "first_mile_gap": int(float(row.get("peak_share", 0.6)) * 730),
                "timeline": [{"minute": minute, "people": round(visitors * _pulse(minute))} for minute in TIME_POINTS],
            })
        return result

    @staticmethod
    def _actions(attendance: int) -> list[dict[str, Any]]:
        scale = attendance / 68777
        bus_hour = 177.51
        rail_hour = 397.61
        commuter_bus_hour = 275.81

        def action(action_id: str, title: str, mode: str, corridor: str, units: str, capacity: int,
                   capex: float, opex: float, low: float, high: float, people: int,
                   timeline: str, owner: str, basis: str, dependency: str) -> dict[str, Any]:
            return {
                "action_id": action_id,
                "title": title,
                "mode": mode,
                "corridor": corridor,
                "units": units,
                "added_capacity": round(capacity * scale),
                "capex": round(capex * scale),
                "opex": round(opex * scale),
                "cost_mid": round((capex + opex) * scale),
                "cost_low": round(low * scale),
                "cost_high": round(high * scale),
                "people_covered": round(people * scale),
                "timeline": timeline,
                "owner": owner,
                "basis": basis,
                "dependency": dependency,
            }

        return [
            action("rail", "Six-minute Red Line event overlay", "rail", "Downtown–TMC–Stadium–Fannin South", "12 added train-hours + platform control", 9400, 165000, rail_hour * 12, 130000, 245000, 31000, "6–10 weeks", "METRO Rail Operations", "FTA rail vehicle-hour anchor plus temporary platform staffing allowance.", "Fleet, operators, signal slots and crowd-control plan"),
            action("shuttle", "32-bus hotel and airport shuttle grid", "shuttle", "EaDo, Downtown, Galleria, Hobby and IAH", "32 buses × 8 hours", 8600, 210000, bus_hour * 32 * 8, 470000, 690000, 18200, "10–14 weeks", "Host Committee + METRO", "FTA bus-hour anchor with staging, dispatch and temporary stop setup.", "Charters, CDL operators, layover space and curb permits"),
            action("shuttle_max", "60-bus redundant shuttle grid", "shuttle", "Airports, hotels and three intercept lots", "60 buses × 10 hours", 15800, 380000, commuter_bus_hour * 60 * 10, 1750000, 2350000, 30500, "14–20 weeks", "Host Committee + METRO", "Commuter-bus vehicle-hour anchor plus reserve vehicles and multi-site operations.", "Contract capacity, reserve drivers and incident detours"),
            action("bus_priority", "Event bus-priority intersections", "traffic", "Main, Fannin, Kirby and Old Spanish Trail", "12 queue-jump / priority locations", 2500, 360000, 65000, 330000, 520000, 9700, "12–18 weeks", "Houston Public Works", "Planning-level temporary signal and lane-control allowance.", "Traffic-control plan, police and signal-controller compatibility"),
            action("bus_lane", "6.5-mile reversible event bus lane", "traffic", "Fannin / Main access spine", "6.5 lane-miles", 7200, 780000, 210000, 760000, 1250000, 21800, "4–8 months", "Houston Public Works + METRO", "Temporary barriers, signs, enforcement, striping and operations allowance.", "Traffic study, emergency access and public notice"),
            action("signals", "Adaptive match-day signal plan", "traffic", "18 intersections around NRG and Medical Center", "18 intersections", 0, 450000, 90000, 430000, 680000, 24700, "3–5 months", "Houston Public Works + TranStar", "Planning allowance of $25k per intersection plus monitoring.", "Detection health check and TranStar operating protocol"),
            action("signals_max", "Adaptive signals + incident-response reserve", "traffic", "32 intersections and freeway approaches", "32 intersections + 4 response crews", 0, 920000, 250000, 940000, 1510000, 40000, "6–9 months", "Houston Public Works + TranStar", "Expanded controller work, field detection and event response staffing.", "Agency MOUs, controller access and response staging"),
            action("park_ride", "Two remote park-and-ride intercepts", "park_ride", "Fannin South + southwest intercept", "2 sites / 5,200 spaces", 9200, 330000, 240000, 470000, 760000, 17200, "10–16 weeks", "METRO + lot operators", "Site operations, attendants, signs and shuttle interface; parking fee modeled separately.", "Signed site agreement and verified usable spaces"),
            action("park_ride_max", "Three remote intercept hubs", "park_ride", "South, west and north approaches", "3 sites / 8,500 spaces", 14900, 610000, 390000, 810000, 1320000, 27200, "4–6 months", "METRO + lot operators", "Expanded site control, lighting, security and passenger-loading allowance.", "Lot contracts, neighborhood traffic plan and ADA bays"),
            action("pudo", "Geofenced rideshare and taxi staging", "rideshare", "Yellow Lot 35 / Kirby outer loop", "2 holding areas + driver geofence", 2600, 175000, 80000, 210000, 350000, 10600, "8–12 weeks", "Venue + TNCs + ARA", "Temporary curb, signs, marshals and software-geofence allowance.", "TNC agreements, taxi dispatch and curb enforcement"),
            action("wayfinding", "Multilingual transfer wayfinding", "access", "Central Station, TMC, Fannin South and venue gates", "85 signs + 45 ambassadors", 0, 120000, 145000, 220000, 340000, 23000, "6–10 weeks", "Host Committee + METRO", "Temporary wayfinding production and event staffing allowance.", "Language review, accessibility review and station permits"),
            action("walk", "Protected last-mile approach network", "walking", "Stadium/Astrodome station, Fannin and Kirby", "4 protected approaches / 38 crossings", 0, 470000, 155000, 500000, 820000, 28600, "3–5 months", "Public Works + Venue", "Barriers, crossing staff, lighting, shade and temporary traffic control.", "ADA field audit, emergency egress and property access"),
            action("walk_max", "Continuous accessible fan-route grid", "walking", "TMC, Fannin South, Kirby and fan-walk corridors", "7 routes / 64 crossings", 0, 930000, 280000, 980000, 1540000, 44800, "6–9 months", "Public Works + Venue", "Expanded protected-route, lighting, crossing and accessibility allowance.", "Construction coordination and accessible detour verification"),
            action("heat", "Heat-safe queue and transfer package", "heat", "8 transfer points and venue perimeter", "18 hydration + 8 cooling + 5 medical posts", 0, 220000, 190000, 330000, 520000, 39000, "8–12 weeks", "Public Health + Venue", "Rental, consumables, staffing and replenishment planning range.", "Power, water, EMS protocol and heat-trigger thresholds"),
            action("heat_max", "Network-wide heat resilience package", "heat", "Transit hubs, fan routes, P&R sites and venue", "32 hydration + 15 cooling + 9 medical posts", 0, 430000, 360000, 620000, 990000, 61000, "12–18 weeks", "Public Health + Venue", "Expanded cooling, hydration, shade, medical and replenishment allowance.", "Weather monitoring, supplies and mutual-aid roster"),
            action("reserve", "Disruption reserve and control-room cell", "resilience", "Citywide event network", "10 reserve buses + 4 response crews", 2800, 260000, bus_hour * 10 * 10 + 150000, 470000, 720000, 68777, "12–18 weeks", "TranStar + Host Committee", "Reserved fleet hours, response crews and joint operating cell allowance.", "Cross-agency command protocol and trigger matrix"),
        ]

    def _route_analysis(self, event: dict[str, Any], zones: list[dict[str, Any]], plan: dict[str, Any]) -> list[dict[str, Any]]:
        spatial_by_id = {row["corridor_id"]: row for row in self.spatial["roads"]["corridors"]}
        mode_by_zone = {
            "downtown_fan_zone": "rail", "midtown_hotels": "rail", "museum_district": "rail",
            "medical_center": "rail + walk", "fannin_south": "park-and-ride + rail",
            "galleria_uptown": "event shuttle", "eado_fan_zone": "rail transfer",
            "hobby_airport": "express shuttle", "iah_airport": "express shuttle",
            "sw_park_ride": "park-and-ride shuttle",
        }
        baseline_pressures = [1.27, 1.18, 1.03, 0.94, 1.16, 1.34, 1.11, 1.24, 1.29, 1.09]
        responsiveness = [0.96, 0.92, 0.90, 0.78, 0.97, 1.04, 0.94, 0.88, 0.84, 1.01]
        rows = []
        for index, zone in enumerate(zones):
            spatial = spatial_by_id.get(zone["zone_id"], {})
            distance_km = spatial.get("distance_km") or round(math.hypot(zone["lat"] - 29.6847, zone["lon"] + 95.4107) * 93, 1)
            freeflow = spatial.get("freeflow_minutes") or max(8, round(distance_km * 1.7))
            base_pressure = baseline_pressures[index]
            peak_pressure = max(0.48, base_pressure * (1 - plan["relief"] * responsiveness[index]))
            base_time = freeflow * (1 + max(0, base_pressure - 0.68) * 0.95)
            plan_time = freeflow * (1 + max(0, peak_pressure - 0.68) * 0.82)
            rows.append({
                "route_id": zone["zone_id"],
                "origin": zone["name"],
                "destination": "Houston Stadium",
                "primary_mode": mode_by_zone[zone["zone_id"]],
                "people": zone["visitors"],
                "people_covered": round(zone["visitors"] * plan["coverage"]),
                "distance_km": distance_km,
                "freeflow_minutes": round(freeflow, 1),
                "baseline_minutes": round(base_time, 1),
                "plan_minutes": round(plan_time, 1),
                "baseline_pressure": round(base_pressure, 2),
                "peak_pressure": round(peak_pressure, 2),
                "first_mile_gap_m": zone["first_mile_gap"],
                "last_mile_gap_m": 320 if "rail" in mode_by_zone[zone["zone_id"]] else 510,
                "geometry": spatial.get("geometry") or [[zone["lat"], zone["lon"]], [29.6847, -95.4107]],
                "geometry_source": spatial.get("geometry_source", "screening geometry"),
                "timeline": [{
                    "minute": minute,
                    "pressure": round(peak_pressure * _pulse(minute), 2),
                    "speed_pct_freeflow": round(max(22, 100 / (1 + max(0, peak_pressure * _pulse(minute) - 0.72) ** 2 * 2.2))),
                    "travel_minutes": round(freeflow * (1 + max(0, peak_pressure * _pulse(minute) - 0.68) * 0.82), 1),
                } for minute in TIME_POINTS],
            })
        return rows

    def plan(self, event_id: str = "houston_wc26") -> dict[str, Any]:
        event = self._event(event_id)
        zones = self._scaled_zones(event["attendance"])
        actions = {item["action_id"]: item for item in self._actions(event["attendance"])}
        plans = []
        for definition in PLAN_DEFINITIONS:
            plan = deepcopy(definition)
            plan_actions = [actions[action_id] for action_id in plan.pop("action_ids")]
            direct_cost = sum(item["cost_mid"] for item in plan_actions)
            program_cost = round(direct_cost * 0.18)
            cost_mid = direct_cost + program_cost
            plan["cost"] = {
                "low": round(sum(item["cost_low"] for item in plan_actions) * 1.12),
                "mid": cost_mid,
                "high": round(sum(item["cost_high"] for item in plan_actions) * 1.24),
                "program_delivery_and_contingency": program_cost,
                "basis": "Planning estimate in 2026 USD; includes a transparent 18% program-delivery/contingency allowance.",
            }
            plan["actions"] = plan_actions
            plan["metrics"] = {
                "people_covered": round(event["attendance"] * plan["coverage"]),
                "coverage_pct": round(plan["coverage"] * 100),
                "vehicles_avoided": round(event["attendance"] * (0.072 + plan["emissions_reduction"] * 0.32)),
                "max_pressure": round(1.34 * (1 - plan["relief"]), 2),
                "delay_reduction_pct": round(plan["delay_reduction"] * 100),
                "emissions_reduction_pct": round(plan["emissions_reduction"] * 100),
                "heat_exposure_reduction_pct": round(plan["heat_reduction"] * 100),
                "robustness_score": plan["robustness"],
                "equity_coverage_pct": plan["equity"],
            }
            plan["routes"] = self._route_analysis(event, zones, plan)
            plans.append(plan)

        baseline = {
            "max_pressure": 1.34,
            "people_covered": 0,
            "coverage_pct": 0,
            "vehicles_avoided": 0,
            "delay_reduction_pct": 0,
            "emissions_reduction_pct": 0,
            "heat_exposure_reduction_pct": 0,
            "robustness_score": 51,
            "equity_coverage_pct": 42,
        }
        return {
            "schema_version": "2.0",
            "generated_mode": "automatic",
            "event": event,
            "venue": self.spatial["venue"],
            "time_points": TIME_POINTS,
            "zones": zones,
            "baseline": baseline,
            "plans": plans,
            "recommended_plan_id": "balanced",
            "transit": self.spatial["transit"],
            "data_freshness": {
                "basemap": "live OpenStreetMap tiles",
                "road_geometry": "OSRM street-routed and cached",
                "transit": self.spatial["transit"]["feed"]["snapshot"],
                "traffic": "projection mode; TranStar live feed connector documented but not authenticated",
                "costs": "2024 FTA operations + 2026 planning allowances",
            },
            "model_limits": [
                "Traffic values are scenario projections, not a claim of current sensor conditions.",
                "Cost ranges are order-of-magnitude planning estimates, not vendor quotes or procurement bids.",
                "Cross-city scores are comparable screening outputs; Houston is the detailed implementation case.",
            ],
        }


__all__ = ["MobilityPlatform"]
