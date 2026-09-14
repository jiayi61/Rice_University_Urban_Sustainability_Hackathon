from __future__ import annotations

import csv
import heapq
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .osm_ingestion import VENUE
from .sample_data import load_demo_zones

ALLOWED_TYPES = {"park_ride", "rideshare", "fan_zone", "cooling_medical"}
TYPE_LABELS = {
    "park_ride": "Park-and-Ride",
    "rideshare": "Rideshare staging",
    "fan_zone": "Fan Zone",
    "cooling_medical": "Cooling / medical",
}

ALIASES = {
    "candidate_id": ("candidate_id", "site_id", "id", "location_id"),
    "name": ("name", "site_name", "location_name"),
    "candidate_type": ("candidate_type", "site_type", "type", "category"),
    "latitude": ("latitude", "lat", "y"),
    "longitude": ("longitude", "lon", "lng", "x"),
    "capacity_riders": ("capacity_riders", "capacity", "spaces", "throughput", "throughput_per_hour"),
    "cost_usd": ("cost_usd", "cost", "estimated_cost"),
    "accessible": ("accessible", "ada_accessible", "ada", "wheelchair_accessible"),
    "address": ("address", "street_address", "facility_address"),
    "source_name": ("source_name", "source", "agency"),
    "source_url": ("source_url", "url", "citation_url"),
    "evidence_level": ("evidence_level", "evidence", "verification_level"),
    "official_source": ("official_source", "official", "agency_verified"),
    "capacity_verified": ("capacity_verified", "verified_capacity", "capacity_official"),
    "accessibility_verified": ("accessibility_verified", "ada_verified", "accessible_verified"),
}


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "accessible", "ada"}


def _evidence_level(value: Any, official: bool) -> str:
    text = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    mapping = {
        "official_verified": "official_verified",
        "verified": "official_verified" if official else "user_verified",
        "official_location": "official_location",
        "agency_planning": "agency_planning",
        "user_verified": "user_verified",
        "user_input": "user_input",
        "illustrative": "illustrative",
        "synthetic": "illustrative",
    }
    if text in mapping:
        return mapping[text]
    return "official_location" if official else "user_input"


def _evidence_score(level: str) -> float:
    return {
        "official_verified": 1.0,
        "official_location": 0.78,
        "agency_planning": 0.68,
        "user_verified": 0.62,
        "user_input": 0.42,
        "illustrative": 0.22,
    }.get(level, 0.35)


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_miles * math.asin(math.sqrt(a))


def _canonical_type(value: Any) -> str | None:
    text = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    mapping = {
        "park_and_ride": "park_ride",
        "parkride": "park_ride",
        "parking": "park_ride",
        "park_ride": "park_ride",
        "rideshare": "rideshare",
        "ride_share": "rideshare",
        "rideshare_staging": "rideshare",
        "fan_zone": "fan_zone",
        "fanzone": "fan_zone",
        "cooling": "cooling_medical",
        "medical": "cooling_medical",
        "cooling_medical": "cooling_medical",
        "cooling_and_medical": "cooling_medical",
    }
    return mapping.get(text)


def _field_map(columns: Iterable[str]) -> dict[str, str | None]:
    lookup = {str(column).strip().casefold(): str(column) for column in columns}
    result: dict[str, str | None] = {}
    for canonical, aliases in ALIASES.items():
        result[canonical] = next((lookup[alias.casefold()] for alias in aliases if alias.casefold() in lookup), None)
    return result


def _load_rows(source: str | Path) -> tuple[list[dict[str, Any]], list[str], str]:
    path = Path(source).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Candidate-site file not found: {path}")
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
            columns = list(reader.fieldnames or [])
        return rows, columns, str(path)
    if suffix in {".json", ".geojson"}:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows: list[dict[str, Any]] = []
        if isinstance(payload, dict) and isinstance(payload.get("features"), list):
            for feature in payload["features"]:
                props = dict(feature.get("properties") or {})
                coords = ((feature.get("geometry") or {}).get("coordinates") or [])
                if isinstance(coords, list) and len(coords) >= 2:
                    props.setdefault("longitude", coords[0])
                    props.setdefault("latitude", coords[1])
                rows.append(props)
        elif isinstance(payload, list):
            rows = [dict(row) for row in payload if isinstance(row, dict)]
        else:
            raise ValueError("Candidate JSON must be a GeoJSON FeatureCollection or a list of records.")
        columns = sorted({key for row in rows for key in row})
        return rows, columns, str(path)
    raise ValueError("Candidate-site source must be CSV, JSON or GeoJSON.")


def scan_candidates(source: str | Path) -> dict[str, Any]:
    rows, columns, resolved = _load_rows(source)
    fields = _field_map(columns)
    required = ("candidate_type", "latitude", "longitude")
    missing = [field for field in required if not fields.get(field)]
    recognized = 0
    type_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        candidate_type = _canonical_type(row.get(fields["candidate_type"])) if fields.get("candidate_type") else None
        lat = _safe_float(row.get(fields["latitude"])) if fields.get("latitude") else None
        lon = _safe_float(row.get(fields["longitude"])) if fields.get("longitude") else None
        if candidate_type and lat is not None and lon is not None:
            recognized += 1
            type_counts[candidate_type] += 1
    return {
        "ready": not missing and recognized > 0,
        "source": resolved,
        "rows": len(rows),
        "recognized_rows": recognized,
        "columns": columns,
        "field_map": fields,
        "missing_required_fields": missing,
        "type_counts": {TYPE_LABELS.get(key, key): value for key, value in sorted(type_counts.items())},
    }


def _nearest_zone(lat: float, lon: float) -> tuple[str, str, float]:
    zones = load_demo_zones()
    zone = min(zones, key=lambda item: _haversine_miles(lat, lon, item.lat, item.lon))
    return zone.zone_id, zone.name, _haversine_miles(lat, lon, zone.lat, zone.lon)


def _load_osm_graph(osm_profile_path: str | Path | None) -> tuple[dict[str, dict[str, float]], dict[str, list[tuple[str, str, float, float]]]]:
    if not osm_profile_path:
        return {}, {}
    path = Path(osm_profile_path)
    if not path.exists():
        return {}, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, {}
    nodes = {
        str(node_id): {"lat": float(row["lat"]), "lon": float(row["lon"])}
        for node_id, row in (payload.get("nodes") or {}).items()
        if "lat" in row and "lon" in row
    }
    adjacency: dict[str, list[tuple[str, str, float, float]]] = defaultdict(list)
    for edge in payload.get("edges", []):
        try:
            adjacency[str(edge["source"])].append(
                (
                    str(edge["target"]),
                    str(edge["edge_id"]),
                    float(edge.get("freeflow_minutes", 0.1)),
                    float(edge.get("distance_miles", 0.01)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return nodes, dict(adjacency)


def _nearest_node(nodes: dict[str, dict[str, float]], lat: float, lon: float) -> tuple[str, float] | None:
    if not nodes:
        return None
    node_id = min(nodes, key=lambda key: _haversine_miles(lat, lon, nodes[key]["lat"], nodes[key]["lon"]))
    return node_id, _haversine_miles(lat, lon, nodes[node_id]["lat"], nodes[node_id]["lon"])


def _dijkstra(
    adjacency: dict[str, list[tuple[str, str, float, float]]], start: str, goal: str
) -> tuple[list[str], float, float] | None:
    heap: list[tuple[float, str]] = [(0.0, start)]
    distances = {start: 0.0}
    previous: dict[str, tuple[str, str, float]] = {}
    while heap:
        minutes, node = heapq.heappop(heap)
        if minutes > distances.get(node, float("inf")):
            continue
        if node == goal:
            edge_ids: list[str] = []
            miles = 0.0
            cursor = goal
            while cursor != start:
                parent, edge_id, distance_miles = previous[cursor]
                edge_ids.append(edge_id)
                miles += distance_miles
                cursor = parent
            edge_ids.reverse()
            return edge_ids, minutes, miles
        for neighbor, edge_id, edge_minutes, edge_miles in adjacency.get(node, []):
            candidate = minutes + edge_minutes
            if candidate + 1e-12 < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                previous[neighbor] = (node, edge_id, edge_miles)
                heapq.heappush(heap, (candidate, neighbor))
    return None


def _site_score(
    candidate_type: str,
    capacity: float,
    route_minutes: float,
    distance_miles: float,
    accessible: bool,
    cost: float,
    *,
    evidence_level: str,
    capacity_verified: bool,
    accessibility_verified: bool,
) -> float:
    capacity_component = min(1.0, math.log1p(max(0.0, capacity)) / math.log1p(12000.0))
    if capacity > 0 and not capacity_verified:
        capacity_component *= 0.78
    travel_component = max(0.0, min(1.0, 1.0 - route_minutes / 90.0))
    if accessible and accessibility_verified:
        accessibility_component = 1.0
    elif accessible:
        accessibility_component = 0.68
    else:
        accessibility_component = 0.25
    evidence_component = _evidence_score(evidence_level)
    cost_component = max(0.0, min(1.0, 1.0 - cost / 800000.0))
    if candidate_type == "park_ride":
        location_component = 1.0 if 3.0 <= distance_miles <= 15.0 else max(0.2, 1.0 - abs(distance_miles - 8.0) / 18.0)
        score = 0.25 * capacity_component + 0.20 * travel_component + 0.16 * accessibility_component + 0.16 * location_component + 0.10 * cost_component + 0.13 * evidence_component
    elif candidate_type == "rideshare":
        location_component = 1.0 if 1.0 <= distance_miles <= 5.0 else max(0.2, 1.0 - abs(distance_miles - 2.5) / 10.0)
        score = 0.25 * capacity_component + 0.23 * travel_component + 0.17 * accessibility_component + 0.13 * location_component + 0.09 * cost_component + 0.13 * evidence_component
    elif candidate_type == "fan_zone":
        score = 0.28 * capacity_component + 0.18 * travel_component + 0.17 * accessibility_component + 0.12 * cost_component + 0.10 * max(0.0, 1.0 - distance_miles / 20.0) + 0.15 * evidence_component
    else:
        score = 0.20 * capacity_component + 0.17 * travel_component + 0.24 * accessibility_component + 0.12 * cost_component + 0.10 * max(0.0, 1.0 - distance_miles / 8.0) + 0.17 * evidence_component
    return round(max(0.0, min(100.0, score * 100.0)), 1)


def build_candidate_profile(
    source: str | Path,
    output_path: str | Path,
    *,
    osm_profile_path: str | Path | None = None,
) -> dict[str, Any]:
    rows, columns, resolved = _load_rows(source)
    fields = _field_map(columns)
    missing = [field for field in ("candidate_type", "latitude", "longitude") if not fields.get(field)]
    if missing:
        raise ValueError(f"Missing required candidate fields: {missing}")

    nodes, adjacency = _load_osm_graph(osm_profile_path)
    stadium_snap = _nearest_node(nodes, VENUE["lat"], VENUE["lon"])
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, row in enumerate(rows, start=1):
        candidate_type = _canonical_type(row.get(fields["candidate_type"]))
        lat = _safe_float(row.get(fields["latitude"]))
        lon = _safe_float(row.get(fields["longitude"]))
        if candidate_type not in ALLOWED_TYPES or lat is None or lon is None:
            continue
        candidate_id = str(row.get(fields.get("candidate_id") or "") or f"site_{index}").strip()
        name = str(row.get(fields.get("name") or "") or f"Candidate site {index}").strip()
        capacity = max(0.0, _safe_float(row.get(fields.get("capacity_riders") or ""), 0.0) or 0.0)
        cost = max(0.0, _safe_float(row.get(fields.get("cost_usd") or ""), 0.0) or 0.0)
        accessible = _truthy(row.get(fields.get("accessible") or ""))
        official_source = _truthy(row.get(fields.get("official_source") or ""))
        capacity_verified = _truthy(row.get(fields.get("capacity_verified") or ""))
        accessibility_verified = _truthy(row.get(fields.get("accessibility_verified") or ""))
        evidence_level = _evidence_level(row.get(fields.get("evidence_level") or ""), official_source)
        address = str(row.get(fields.get("address") or "") or "").strip()
        source_name = str(row.get(fields.get("source_name") or "") or ("Official agency source" if official_source else "User-provided candidate file")).strip()
        source_url = str(row.get(fields.get("source_url") or "") or "").strip()
        straight_line = _haversine_miles(lat, lon, VENUE["lat"], VENUE["lon"])
        route_source = "straight-line estimate"
        route_minutes = max(4.0, straight_line / 22.0 * 60.0)
        route_miles = straight_line * 1.25
        route_edges: list[str] = []
        snap_distance = None
        if nodes and adjacency and stadium_snap:
            site_snap = _nearest_node(nodes, lat, lon)
            if site_snap:
                path = _dijkstra(adjacency, site_snap[0], stadium_snap[0])
                snap_distance = site_snap[1]
                if path:
                    route_edges, route_minutes, route_miles = path
                    route_source = "OSM network"
        zone_id, zone_name, zone_distance = _nearest_zone(lat, lon)
        cycle_minutes = route_minutes * 2.0 + (14.0 if candidate_type == "park_ride" else 8.0)
        score = _site_score(
            candidate_type, capacity, route_minutes, straight_line, accessible, cost,
            evidence_level=evidence_level, capacity_verified=capacity_verified,
            accessibility_verified=accessibility_verified,
        )
        candidates.append(
            {
                "candidate_id": candidate_id,
                "name": name,
                "candidate_type": candidate_type,
                "candidate_type_label": TYPE_LABELS[candidate_type],
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "capacity_riders": round(capacity),
                "cost_usd": round(cost, 2),
                "accessible": accessible,
                "accessibility_verified": accessibility_verified,
                "capacity_verified": capacity_verified,
                "official_source": official_source,
                "evidence_level": evidence_level,
                "evidence_score": round(_evidence_score(evidence_level) * 100.0, 1),
                "address": address,
                "source_name": source_name,
                "source_url": source_url,
                "nearest_zone_id": zone_id,
                "nearest_zone_name": zone_name,
                "distance_to_zone_miles": round(zone_distance, 2),
                "straight_line_to_stadium_miles": round(straight_line, 2),
                "route_distance_miles": round(route_miles, 2),
                "one_way_minutes": round(route_minutes, 1),
                "estimated_cycle_minutes": round(cycle_minutes, 1),
                "route_source": route_source,
                "snap_distance_miles": round(snap_distance, 2) if snap_distance is not None else None,
                "route_edges": route_edges,
                "readiness_score": score,
            }
        )

    if not candidates:
        raise ValueError("No usable candidate sites were found.")
    candidates.sort(key=lambda item: (item["candidate_type"], -item["readiness_score"], item["cost_usd"]))
    rankings: dict[str, list[str]] = {}
    type_summary: dict[str, dict[str, Any]] = {}
    for candidate_type in sorted(ALLOWED_TYPES):
        subset = [item for item in candidates if item["candidate_type"] == candidate_type]
        if not subset:
            continue
        rankings[candidate_type] = [item["candidate_id"] for item in sorted(subset, key=lambda item: item["readiness_score"], reverse=True)]
        type_summary[candidate_type] = {
            "label": TYPE_LABELS[candidate_type],
            "site_count": len(subset),
            "total_capacity_riders": round(sum(item["capacity_riders"] for item in subset)),
            "accessible_site_count": sum(item["accessible"] for item in subset),
            "verified_accessible_site_count": sum(item["accessible"] and item["accessibility_verified"] for item in subset),
            "official_site_count": sum(item["official_source"] for item in subset),
            "verified_capacity_riders": round(sum(item["capacity_riders"] for item in subset if item["capacity_verified"])),
            "best_site_id": rankings[candidate_type][0],
        }
    if not nodes:
        warnings.append("No OSM road profile was connected; route times use transparent straight-line estimates.")

    profile = {
        "mode": "candidate_sites",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": resolved,
        "candidate_count": len(candidates),
        "type_summary": type_summary,
        "rankings": rankings,
        "candidates": candidates,
        "warnings": warnings,
        "disclaimer": (
            "Candidate-site rankings are planning-screening outputs. Site control, permits, curb operations, "
            "ADA compliance and agency feasibility require field validation."
        ),
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def load_candidate_profile(path: str | Path) -> dict[str, Any] | None:
    profile_path = Path(path)
    if not profile_path.exists():
        return None
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        return None
    return payload
