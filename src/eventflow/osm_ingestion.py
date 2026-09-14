from __future__ import annotations

import heapq
import json
import math
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .sample_data import load_demo_zones

VENUE = {"location_id": "stadium", "name": "Houston Stadium / NRG Stadium", "lat": 29.6847, "lon": -95.4107}
DEFAULT_BBOX = {"south": 29.62, "west": -95.53, "north": 30.03, "east": -95.25}
DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

HIGHWAY_DEFAULTS: dict[str, dict[str, float]] = {
    "motorway": {"speed_mph": 60, "lanes": 6, "capacity_per_lane": 2000, "baseline_utilization": 0.58},
    "motorway_link": {"speed_mph": 40, "lanes": 2, "capacity_per_lane": 1500, "baseline_utilization": 0.50},
    "trunk": {"speed_mph": 50, "lanes": 4, "capacity_per_lane": 1900, "baseline_utilization": 0.55},
    "trunk_link": {"speed_mph": 35, "lanes": 2, "capacity_per_lane": 1450, "baseline_utilization": 0.48},
    "primary": {"speed_mph": 40, "lanes": 4, "capacity_per_lane": 1650, "baseline_utilization": 0.52},
    "primary_link": {"speed_mph": 30, "lanes": 2, "capacity_per_lane": 1300, "baseline_utilization": 0.46},
    "secondary": {"speed_mph": 35, "lanes": 4, "capacity_per_lane": 1450, "baseline_utilization": 0.47},
    "secondary_link": {"speed_mph": 28, "lanes": 2, "capacity_per_lane": 1200, "baseline_utilization": 0.42},
    "tertiary": {"speed_mph": 30, "lanes": 2, "capacity_per_lane": 1250, "baseline_utilization": 0.40},
    "tertiary_link": {"speed_mph": 25, "lanes": 2, "capacity_per_lane": 1050, "baseline_utilization": 0.36},
    "unclassified": {"speed_mph": 25, "lanes": 2, "capacity_per_lane": 950, "baseline_utilization": 0.33},
    "residential": {"speed_mph": 22, "lanes": 2, "capacity_per_lane": 800, "baseline_utilization": 0.28},
    "service": {"speed_mph": 15, "lanes": 1, "capacity_per_lane": 550, "baseline_utilization": 0.24},
    "living_street": {"speed_mph": 12, "lanes": 1, "capacity_per_lane": 400, "baseline_utilization": 0.20},
}


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_miles * math.asin(math.sqrt(a))


def _parse_maxspeed(value: Any, default: float) -> float:
    text = str(value or "").strip().lower()
    if not text:
        return default
    if ";" in text:
        text = text.split(";", 1)[0]
    digits = "".join(ch if (ch.isdigit() or ch == ".") else " " for ch in text).split()
    if not digits:
        return default
    number = _safe_float(digits[0], default) or default
    if "km" in text:
        number *= 0.621371
    return max(5.0, min(80.0, number))


def _parse_lanes(value: Any, default: float, oneway: bool) -> float:
    text = str(value or "").strip()
    parsed = _safe_float(text.split(";")[0] if text else None, default) or default
    directional = parsed if oneway else max(1.0, parsed / 2.0)
    return max(1.0, min(8.0, directional))


def _is_oneway(tags: dict[str, Any], highway: str) -> bool:
    value = str(tags.get("oneway", "")).strip().lower()
    if value in {"yes", "1", "true"}:
        return True
    if value in {"no", "0", "false"}:
        return False
    return highway in {"motorway", "motorway_link"} or str(tags.get("junction", "")).lower() == "roundabout"


def _road_name(tags: dict[str, Any], highway: str, way_id: str) -> str:
    name = str(tags.get("name") or tags.get("ref") or "").strip()
    return name or f"{highway.replace('_', ' ').title()} {way_id}"


def _locations() -> dict[str, dict[str, Any]]:
    return {
        VENUE["location_id"]: dict(VENUE),
        **{
            zone.zone_id: {
                "location_id": zone.zone_id,
                "name": zone.name,
                "lat": zone.lat,
                "lon": zone.lon,
            }
            for zone in load_demo_zones()
        },
    }


def build_overpass_query(bbox: dict[str, float] | None = None) -> str:
    box = bbox or DEFAULT_BBOX
    south, west, north, east = (box["south"], box["west"], box["north"], box["east"])
    venue_lat, venue_lon = VENUE["lat"], VENUE["lon"]
    return f"""[out:json][timeout:90];
(
  way[\"highway\"~\"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link)$\"]({south},{west},{north},{east});
  way[\"highway\"~\"^(unclassified|residential|service|living_street)$\"](around:6000,{venue_lat},{venue_lon});
);
out body;
>;
out skel qt;
"""


def fetch_overpass(
    output_path: str | Path,
    *,
    bbox: dict[str, float] | None = None,
    endpoint: str = DEFAULT_OVERPASS_URL,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    query = build_overpass_query(bbox)
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "User-Agent": "EventFlowAI/0.6 (academic hackathon prototype)",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except Exception as exc:  # network behavior varies by local machine
        raise RuntimeError(
            "Could not download OpenStreetMap data from Overpass. Check the internet connection, "
            "retry later, or use a local Overpass JSON file."
        ) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Overpass returned an unreadable response.") from exc
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def load_osm_source(source: str | Path) -> dict[str, Any]:
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"OpenStreetMap source not found: {path}")
    if not path.is_file():
        raise ValueError("OpenStreetMap source must be an Overpass JSON file.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid Overpass JSON: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("The file does not look like an Overpass JSON response.")
    return payload


def scan_osm(source: str | Path) -> dict[str, Any]:
    payload = load_osm_source(source)
    elements = payload.get("elements", [])
    node_count = sum(1 for item in elements if item.get("type") == "node")
    ways = [item for item in elements if item.get("type") == "way" and item.get("tags", {}).get("highway")]
    highway_counts: dict[str, int] = defaultdict(int)
    for way in ways:
        highway_counts[str(way.get("tags", {}).get("highway", "unknown"))] += 1
    return {
        "ready": node_count > 1 and bool(ways),
        "source": str(Path(source).expanduser().resolve()),
        "node_count": node_count,
        "way_count": len(ways),
        "highway_counts": dict(sorted(highway_counts.items())),
        "attribution": "© OpenStreetMap contributors; data accessed through the Overpass API or a local export.",
    }


def _nearest_node(nodes: dict[str, dict[str, float]], lat: float, lon: float) -> tuple[str, float]:
    if not nodes:
        raise ValueError("The OSM network contains no nodes.")
    best_id = ""
    best_distance = float("inf")
    for node_id, node in nodes.items():
        distance = _haversine_miles(lat, lon, node["lat"], node["lon"])
        if distance < best_distance:
            best_id = node_id
            best_distance = distance
    return best_id, best_distance


def _dijkstra(
    adjacency: dict[str, list[tuple[str, str, float]]],
    start: str,
    goal: str,
    penalties: dict[str, float] | None = None,
) -> tuple[list[str], float] | None:
    penalties = penalties or {}
    heap: list[tuple[float, str]] = [(0.0, start)]
    distances = {start: 0.0}
    previous: dict[str, tuple[str, str]] = {}
    while heap:
        distance, node = heapq.heappop(heap)
        if distance > distances.get(node, float("inf")):
            continue
        if node == goal:
            edge_path: list[str] = []
            current = goal
            while current != start:
                parent, edge_id = previous[current]
                edge_path.append(edge_id)
                current = parent
            edge_path.reverse()
            return edge_path, distance
        for neighbor, edge_id, weight in adjacency.get(node, []):
            candidate = distance + weight * penalties.get(edge_id, 1.0)
            if candidate + 1e-12 < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                previous[neighbor] = (node, edge_id)
                heapq.heappush(heap, (candidate, neighbor))
    return None


def _route_shares(
    adjacency: dict[str, list[tuple[str, str, float]]],
    start: str,
    goal: str,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    primary = _dijkstra(adjacency, start, goal)
    if primary is None:
        return {}, []
    primary_edges, primary_minutes = primary
    penalties = {edge_id: 2.4 for edge_id in primary_edges}
    alternative = _dijkstra(adjacency, start, goal, penalties)
    paths: list[tuple[list[str], float, float]] = [(primary_edges, primary_minutes, 1.0)]
    if alternative is not None:
        alt_edges, alt_penalized_minutes = alternative
        overlap = len(set(primary_edges) & set(alt_edges)) / max(1, len(set(primary_edges) | set(alt_edges)))
        # Recalculate unpenalized travel time from adjacency weights.
        edge_weights = {edge_id: weight for rows in adjacency.values() for _, edge_id, weight in rows}
        alt_minutes = sum(edge_weights.get(edge_id, 0.0) for edge_id in alt_edges)
        if alt_edges != primary_edges and alt_minutes <= primary_minutes * 1.65 and overlap <= 0.80:
            paths = [(primary_edges, primary_minutes, 0.75), (alt_edges, alt_minutes, 0.25)]
    shares: dict[str, float] = defaultdict(float)
    path_rows: list[dict[str, Any]] = []
    for edges, minutes, share in paths:
        for edge_id in edges:
            shares[edge_id] += share
        path_rows.append({"edge_ids": edges, "travel_minutes": round(minutes, 2), "share": share})
    return dict(shares), path_rows


def build_osm_profile(source: str | Path, output_path: str | Path) -> dict[str, Any]:
    payload = load_osm_source(source)
    elements = payload.get("elements", [])
    nodes: dict[str, dict[str, float]] = {}
    ways: list[dict[str, Any]] = []
    for item in elements:
        if item.get("type") == "node":
            lat = _safe_float(item.get("lat"))
            lon = _safe_float(item.get("lon"))
            if lat is not None and lon is not None:
                nodes[str(item.get("id"))] = {"lat": lat, "lon": lon}
        elif item.get("type") == "way" and item.get("tags", {}).get("highway"):
            ways.append(item)
    if not nodes or not ways:
        raise ValueError("The OSM source does not contain usable road nodes and ways.")

    edges: list[dict[str, Any]] = []
    adjacency: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    edge_lookup: dict[str, dict[str, Any]] = {}
    skipped_segments = 0

    for way in ways:
        tags = dict(way.get("tags") or {})
        highway = str(tags.get("highway", "unclassified"))
        if highway not in HIGHWAY_DEFAULTS:
            continue
        defaults = HIGHWAY_DEFAULTS[highway]
        oneway = _is_oneway(tags, highway)
        lanes = _parse_lanes(tags.get("lanes"), defaults["lanes"], oneway)
        speed_mph = _parse_maxspeed(tags.get("maxspeed"), defaults["speed_mph"])
        capacity = max(250.0, lanes * defaults["capacity_per_lane"])
        baseline = capacity * defaults["baseline_utilization"]
        way_id = str(way.get("id"))
        name = _road_name(tags, highway, way_id)
        node_ids = [str(value) for value in way.get("nodes", [])]
        for index, (segment_source, segment_target) in enumerate(zip(node_ids, node_ids[1:])):
            if segment_source not in nodes or segment_target not in nodes:
                skipped_segments += 1
                continue
            a, b = nodes[segment_source], nodes[segment_target]
            distance = _haversine_miles(a["lat"], a["lon"], b["lat"], b["lon"])
            if distance <= 0 or distance > 20:
                skipped_segments += 1
                continue
            freeflow = distance / speed_mph * 60.0
            directions = [(segment_source, segment_target, "f")]
            if not oneway:
                directions.append((segment_target, segment_source, "r"))
            for edge_source, edge_target, suffix in directions:
                edge_id = f"w{way_id}_{index}_{suffix}"
                row = {
                    "edge_id": edge_id,
                    "source": edge_source,
                    "target": edge_target,
                    "name": name,
                    "highway": highway,
                    "distance_miles": round(distance, 5),
                    "freeflow_minutes": round(max(0.05, freeflow), 4),
                    "baseline_vehicles": round(baseline, 2),
                    "capacity_vehicles": round(capacity, 2),
                    "lanes_directional": round(lanes, 2),
                    "speed_mph": round(speed_mph, 1),
                    "geometry": [[a["lat"], a["lon"]], [b["lat"], b["lon"]]] if suffix == "f" else [[b["lat"], b["lon"]], [a["lat"], a["lon"]]],
                    "calibration_source": "highway-class assumption",
                }
                edges.append(row)
                edge_lookup[edge_id] = row
                adjacency[edge_source].append((edge_target, edge_id, row["freeflow_minutes"]))

    raw_node_count = len(nodes)
    raw_edge_count = len(edges)

    locations = _locations()
    snapped: dict[str, dict[str, Any]] = {}
    for location_id, location in locations.items():
        node_id, distance = _nearest_node(nodes, float(location["lat"]), float(location["lon"]))
        snapped[location_id] = {
            **location,
            "node_id": node_id,
            "snap_distance_miles": round(distance, 3),
        }

    stadium_node = snapped["stadium"]["node_id"]
    routes: dict[str, dict[str, float]] = {}
    route_paths: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    for zone in load_demo_zones():
        start_node = snapped[zone.zone_id]["node_id"]
        shares, paths = _route_shares(adjacency, start_node, stadium_node)
        routes[zone.zone_id] = shares
        route_paths[zone.zone_id] = paths
        if not shares:
            warnings.append(f"No drivable path was found from {zone.name} to the stadium.")

    route_usage: dict[str, float] = defaultdict(float)
    for zone in load_demo_zones():
        for edge_id, share in routes.get(zone.zone_id, {}).items():
            route_usage[edge_id] += zone.demand * zone.car_share * share

    used_edges = {edge_id for route in routes.values() for edge_id in route}
    core_edges: list[str] = []
    for edge_id in used_edges:
        edge = edge_lookup[edge_id]
        midpoint_lat = sum(point[0] for point in edge["geometry"]) / len(edge["geometry"])
        midpoint_lon = sum(point[1] for point in edge["geometry"]) / len(edge["geometry"])
        if _haversine_miles(midpoint_lat, midpoint_lon, VENUE["lat"], VENUE["lon"]) <= 2.0:
            core_edges.append(edge_id)
    critical_corridors = [edge_id for edge_id, _ in sorted(route_usage.items(), key=lambda item: item[1], reverse=True)[:24]]
    if not core_edges:
        core_edges = critical_corridors[:8]

    # The operational model uses the union of assigned paths. This keeps a city-scale
    # Overpass extract fast enough for scenario optimization and sensitivity analysis.
    model_edge_ids = set(used_edges)
    edges = [edge for edge in edges if edge["edge_id"] in model_edge_ids]
    used_node_ids = {str(edge["source"]) for edge in edges} | {str(edge["target"]) for edge in edges}
    nodes = {node_id: node for node_id, node in nodes.items() if node_id in used_node_ids}
    edge_lookup = {edge["edge_id"]: edge for edge in edges}
    core_edges = [edge_id for edge_id in core_edges if edge_id in edge_lookup]
    critical_corridors = [edge_id for edge_id in critical_corridors if edge_id in edge_lookup]

    profile = {
        "mode": "osm_network",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": str(Path(source).expanduser().resolve()),
        "bbox": DEFAULT_BBOX,
        "attribution": "© OpenStreetMap contributors; network extracted through Overpass or a local Overpass JSON file.",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "raw_node_count": raw_node_count,
        "raw_edge_count": raw_edge_count,
        "way_count": len(ways),
        "skipped_segments": skipped_segments,
        "nodes": nodes,
        "edges": edges,
        "locations": snapped,
        "routes": routes,
        "route_paths": route_paths,
        "target_groups": {
            "stadium_core": core_edges,
            "critical_corridors": critical_corridors,
        },
        "warnings": warnings,
        "disclaimer": (
            "Road geometry comes from OpenStreetMap. Capacities and uncalibrated baseline volumes are inferred "
            "from road class, lane and speed tags until traffic counts are connected."
        ),
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def load_osm_profile(path: str | Path) -> dict[str, Any] | None:
    profile_path = Path(path)
    if not profile_path.exists():
        return None
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("edges"), list):
        return None
    return payload
