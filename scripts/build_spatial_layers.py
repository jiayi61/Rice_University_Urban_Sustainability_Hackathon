#!/usr/bin/env python3
"""Build compact, browser-ready transit and routed-road layers.

The input is a standard GTFS zip. One representative shape is retained for
every route so the UI can offer a comprehensive system layer without shipping
the full feed. Event-origin road paths are resolved against OSRM and cached;
the checked-in fallback geometry keeps the demo usable when routing is offline.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GTFS_DEFAULT = ROOT / "data" / "external" / "houston_metro_gtfs_2026-09-01.zip"
OUTPUT_DEFAULT = ROOT / "data" / "local" / "spatial_layers.json"
VENUE = {"name": "Houston Stadium", "lat": 29.6847, "lon": -95.4107}
ORIGINS = [
    ("downtown_fan_zone", "Downtown / Discovery Green", 29.7604, -95.3698),
    ("midtown_hotels", "Midtown hotels", 29.7426, -95.3767),
    ("museum_district", "Museum District", 29.7216, -95.3896),
    ("medical_center", "Texas Medical Center", 29.7069, -95.4018),
    ("fannin_south", "Fannin South P&R", 29.6744, -95.4029),
    ("galleria_uptown", "Galleria / Uptown", 29.7390, -95.4641),
    ("eado_fan_zone", "EaDo fan zone", 29.7522, -95.3524),
    ("hobby_airport", "Hobby Airport", 29.6454, -95.2789),
    ("iah_airport", "Bush IAH", 29.9902, -95.3368),
    ("sw_park_ride", "Southwest P&R", 29.6511, -95.4647),
]


def read_csv(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    raw = zf.read(name).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))


def simplify(points: list[list[float]], max_points: int = 110) -> list[list[float]]:
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) / (max_points - 1)
    chosen = [points[round(i * step)] for i in range(max_points)]
    chosen[-1] = points[-1]
    return chosen


def build_transit(gtfs_path: Path) -> dict:
    with zipfile.ZipFile(gtfs_path) as zf:
        routes = {r["route_id"]: r for r in read_csv(zf, "routes.txt")}
        trips = read_csv(zf, "trips.txt")
        shapes = read_csv(zf, "shapes.txt")
        stops = read_csv(zf, "stops.txt")

    shape_votes: dict[str, Counter[str]] = defaultdict(Counter)
    for trip in trips:
        shape_id = trip.get("shape_id")
        if shape_id:
            shape_votes[trip["route_id"]][shape_id] += 1
    chosen_shapes = {
        route_id: votes.most_common(1)[0][0]
        for route_id, votes in shape_votes.items()
        if route_id in routes and votes
    }
    wanted_shape_ids = set(chosen_shapes.values())
    by_shape: dict[str, list[tuple[int, list[float]]]] = defaultdict(list)
    for row in shapes:
        shape_id = row.get("shape_id")
        if shape_id not in wanted_shape_ids:
            continue
        by_shape[shape_id].append((
            int(float(row.get("shape_pt_sequence", "0"))),
            [float(row["shape_pt_lat"]), float(row["shape_pt_lon"])],
        ))

    rendered = []
    venue_access = {"014", "060", "084", "700"}
    for route_id, shape_id in chosen_shapes.items():
        route = routes[route_id]
        geometry = [point for _, point in sorted(by_shape.get(shape_id, []))]
        if len(geometry) < 2:
            continue
        route_type = int(route.get("route_type", "3") or 3)
        rendered.append({
            "route_id": route_id,
            "short_name": route.get("route_short_name") or route_id,
            "name": route.get("route_long_name") or route.get("route_short_name") or route_id,
            "mode": "rail" if route_type in {0, 1, 2} else "bus",
            "color": f"#{route.get('route_color') or ('ef4444' if route_type in {0, 1, 2} else '3388ff')}",
            "venue_access": route_id in venue_access,
            "geometry": simplify(geometry),
        })
    rendered.sort(key=lambda row: (row["mode"], row["short_name"]))

    nearby_stops = []
    for stop in stops:
        try:
            lat, lon = float(stop["stop_lat"]), float(stop["stop_lon"])
        except (KeyError, TypeError, ValueError):
            continue
        miles = math.hypot((lat - VENUE["lat"]) * 69.0, (lon - VENUE["lon"]) * 60.0)
        if miles <= 1.15:
            nearby_stops.append({
                "stop_id": stop.get("stop_id"),
                "name": stop.get("stop_name", "Transit stop"),
                "lat": lat,
                "lon": lon,
                "distance_miles": round(miles, 2),
            })

    return {
        "feed": {
            "name": "METRO Houston GTFS",
            "snapshot": "2026-09-01",
            "source": "MobilityDatabase mdb-2060 (producer feed archive)",
            "license_note": "GTFS data is retained as a compact visualization derivative.",
        },
        "route_count": len(rendered),
        "bus_route_count": sum(r["mode"] == "bus" for r in rendered),
        "rail_route_count": sum(r["mode"] == "rail" for r in rendered),
        "routes": rendered,
        "nearby_stops": nearby_stops,
    }


def fallback_path(lat: float, lon: float) -> list[list[float]]:
    midpoint = [(lat + VENUE["lat"]) / 2, (lon + VENUE["lon"]) / 2]
    return [[lat, lon], midpoint, [VENUE["lat"], VENUE["lon"]]]


def osrm_route(lat: float, lon: float) -> tuple[list[list[float]], float, float, str]:
    coordinates = f"{lon},{lat};{VENUE['lon']},{VENUE['lat']}"
    query = urllib.parse.urlencode({"overview": "full", "geometries": "geojson", "steps": "false"})
    url = f"https://router.project-osrm.org/route/v1/driving/{coordinates}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "EventFlow-Academic-Prototype/2.0"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
        route = payload["routes"][0]
        geometry = [[lat_, lon_] for lon_, lat_ in route["geometry"]["coordinates"]]
        return simplify(geometry, 180), route["distance"] / 1000, route["duration"] / 60, "OSRM street-routed"
    except Exception:
        return fallback_path(lat, lon), 0.0, 0.0, "fallback straight-line"


def build_roads() -> dict:
    corridors = []
    for zone_id, name, lat, lon in ORIGINS:
        geometry, distance_km, freeflow_minutes, source = osrm_route(lat, lon)
        corridors.append({
            "corridor_id": zone_id,
            "name": f"{name} → {VENUE['name']}",
            "origin_name": name,
            "origin": {"lat": lat, "lon": lon},
            "destination": VENUE,
            "distance_km": round(distance_km, 1),
            "freeflow_minutes": round(freeflow_minutes, 1),
            "geometry_source": source,
            "geometry": geometry,
        })
    return {
        "routing_engine": "OSRM over OpenStreetMap",
        "generated_for": "Houston event-demand origins",
        "corridors": corridors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gtfs", type=Path, default=GTFS_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    args = parser.parse_args()
    payload = {
        "schema_version": "2.0",
        "venue": VENUE,
        "transit": build_transit(args.gtfs),
        "roads": build_roads(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "transit_routes": payload["transit"]["route_count"],
        "road_corridors": len(payload["roads"]["corridors"]),
        "street_routed": sum(c["geometry_source"].startswith("OSRM") for c in payload["roads"]["corridors"]),
    }))


if __name__ == "__main__":
    main()
