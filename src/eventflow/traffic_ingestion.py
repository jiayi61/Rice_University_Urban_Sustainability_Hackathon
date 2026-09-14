from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LAT_FIELDS = ("latitude", "lat", "y", "point_y", "y_coord", "y_coordinate")
LON_FIELDS = ("longitude", "lon", "lng", "long", "x", "point_x", "x_coord", "x_coordinate")
COUNT_FIELDS = (
    "aadt", "adt", "traffic_count", "traffic_volume", "volume", "count", "total_volume",
    "average_daily_traffic", "avg_daily_traffic", "vehicles", "total",
)
NAME_FIELDS = ("street", "road", "road_name", "street_name", "location", "address", "name")


def _normalize_header(value: str) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", " ").replace("/", " ").split())


def _safe_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_miles * math.asin(math.sqrt(a))


def _find_field(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {_normalize_header(header): header for header in headers}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    for candidate in candidates:
        for normalized_name, original in normalized.items():
            if candidate in normalized_name:
                return original
    return None


def _read_csv_rows(path: Path, max_rows: int = 200000) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        rows = []
        for index, row in enumerate(reader):
            if index >= max_rows:
                break
            rows.append({str(key): str(value or "") for key, value in row.items() if key is not None})
    return rows, headers


def _read_geojson_rows(path: Path, max_rows: int = 200000) -> tuple[list[dict[str, Any]], list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON must be a FeatureCollection.")
    rows: list[dict[str, Any]] = []
    headers: set[str] = set()
    for feature in payload.get("features", [])[:max_rows]:
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        if geometry.get("type") != "Point" or len(coordinates) < 2:
            continue
        properties = dict(feature.get("properties") or {})
        properties["__longitude"] = coordinates[0]
        properties["__latitude"] = coordinates[1]
        headers.update(str(key) for key in properties)
        rows.append(properties)
    return rows, sorted(headers)


def _source_rows(source: str | Path, max_rows: int = 200000) -> tuple[Path, list[dict[str, Any]], list[str]]:
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Traffic-count source not found: {path}")
    if not path.is_file():
        raise ValueError("Traffic-count source must be a CSV or GeoJSON file.")
    if path.suffix.lower() == ".csv":
        rows, headers = _read_csv_rows(path, max_rows)
    elif path.suffix.lower() in {".json", ".geojson"}:
        rows, headers = _read_geojson_rows(path, max_rows)
    else:
        raise ValueError("Traffic-count source must end in .csv, .json, or .geojson.")
    return path, rows, headers


def scan_traffic_counts(source: str | Path) -> dict[str, Any]:
    path, rows, headers = _source_rows(source, max_rows=2000)
    lat_field = "__latitude" if "__latitude" in headers else _find_field(headers, LAT_FIELDS)
    lon_field = "__longitude" if "__longitude" in headers else _find_field(headers, LON_FIELDS)
    count_field = _find_field(headers, COUNT_FIELDS)
    name_field = _find_field(headers, NAME_FIELDS)
    usable = 0
    for row in rows:
        lat = _safe_float(row.get(lat_field)) if lat_field else None
        lon = _safe_float(row.get(lon_field)) if lon_field else None
        count = _safe_float(row.get(count_field)) if count_field else None
        if lat is not None and lon is not None and count is not None and count >= 0:
            usable += 1
    return {
        "ready": bool(lat_field and lon_field and count_field and usable),
        "source": str(path),
        "sampled_rows": len(rows),
        "usable_sample_rows": usable,
        "fields": {
            "latitude": lat_field,
            "longitude": lon_field,
            "count": count_field,
            "name": name_field,
        },
        "headers": headers[:80],
    }


def _edge_midpoint(edge: dict[str, Any], nodes: dict[str, Any]) -> tuple[float, float] | None:
    geometry = edge.get("geometry") or []
    if geometry:
        return (
            sum(float(point[0]) for point in geometry) / len(geometry),
            sum(float(point[1]) for point in geometry) / len(geometry),
        )
    source = nodes.get(str(edge.get("source")))
    target = nodes.get(str(edge.get("target")))
    if source and target:
        return ((float(source["lat"]) + float(target["lat"])) / 2, (float(source["lon"]) + float(target["lon"])) / 2)
    return None


def build_traffic_profile(
    source: str | Path,
    osm_profile_path: str | Path,
    output_path: str | Path,
    *,
    peak_hour_factor: float = 0.09,
    directional_factor: float = 0.55,
    max_snap_miles: float = 1.25,
    max_rows: int = 200000,
) -> dict[str, Any]:
    if not (0 < peak_hour_factor <= 1):
        raise ValueError("peak_hour_factor must be between 0 and 1.")
    if not (0 < directional_factor <= 1):
        raise ValueError("directional_factor must be between 0 and 1.")
    if not (0.05 <= max_snap_miles <= 10):
        raise ValueError("max_snap_miles must be between 0.05 and 10.")

    osm_path = Path(osm_profile_path)
    if not osm_path.exists():
        raise FileNotFoundError("Build an OSM road profile before calibrating traffic counts.")
    osm = json.loads(osm_path.read_text(encoding="utf-8"))
    edges = list(osm.get("edges") or [])
    nodes = dict(osm.get("nodes") or {})
    if not edges:
        raise ValueError("The OSM profile contains no edges.")

    path, rows, headers = _source_rows(source, max_rows=max_rows)
    lat_field = "__latitude" if "__latitude" in headers else _find_field(headers, LAT_FIELDS)
    lon_field = "__longitude" if "__longitude" in headers else _find_field(headers, LON_FIELDS)
    count_field = _find_field(headers, COUNT_FIELDS)
    name_field = _find_field(headers, NAME_FIELDS)
    if not lat_field or not lon_field or not count_field:
        raise ValueError("Could not identify latitude, longitude and traffic-count columns.")

    edge_points: list[tuple[str, float, float, str]] = []
    # A coarse spatial grid avoids an O(count-points × road-edges) scan on full city extracts.
    cell_degrees = max(0.005, max_snap_miles / 55.0)
    edge_grid: dict[tuple[int, int], list[tuple[str, float, float, str]]] = defaultdict(list)
    for edge in edges:
        midpoint = _edge_midpoint(edge, nodes)
        if midpoint:
            point = (str(edge["edge_id"]), midpoint[0], midpoint[1], str(edge.get("highway", "")))
            edge_points.append(point)
            key = (math.floor(midpoint[0] / cell_degrees), math.floor(midpoint[1] / cell_degrees))
            edge_grid[key].append(point)

    matched_by_edge: dict[str, list[dict[str, Any]]] = defaultdict(list)
    count_points: list[dict[str, Any]] = []
    unmatched = 0
    for row in rows:
        lat = _safe_float(row.get(lat_field))
        lon = _safe_float(row.get(lon_field))
        count = _safe_float(row.get(count_field))
        if lat is None or lon is None or count is None or count < 0:
            continue
        nearest_id = ""
        nearest_distance = float("inf")
        center = (math.floor(lat / cell_degrees), math.floor(lon / cell_degrees))
        candidates: list[tuple[str, float, float, str]] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                candidates.extend(edge_grid.get((center[0] + dy, center[1] + dx), []))
        if not candidates:
            candidates = edge_points
        for edge_id, edge_lat, edge_lon, _ in candidates:
            distance = _haversine_miles(lat, lon, edge_lat, edge_lon)
            if distance < nearest_distance:
                nearest_id = edge_id
                nearest_distance = distance
        point = {
            "lat": lat,
            "lon": lon,
            "daily_count": count,
            "name": str(row.get(name_field, "")) if name_field else "",
            "nearest_edge_id": nearest_id or None,
            "snap_distance_miles": round(nearest_distance, 3) if nearest_id else None,
        }
        count_points.append(point)
        if nearest_id and nearest_distance <= max_snap_miles:
            matched_by_edge[nearest_id].append(point)
        else:
            unmatched += 1

    calibrated: dict[str, dict[str, Any]] = {}
    class_ratios: dict[str, list[float]] = defaultdict(list)
    edge_by_id = {str(edge["edge_id"]): edge for edge in edges}
    for edge_id, points in matched_by_edge.items():
        daily_values = sorted(float(point["daily_count"]) for point in points)
        median_daily = daily_values[len(daily_values) // 2]
        observed_hourly = median_daily * peak_hour_factor * directional_factor
        edge = edge_by_id[edge_id]
        assumed = float(edge.get("baseline_vehicles", 0.0))
        calibrated_hourly = 0.80 * observed_hourly + 0.20 * assumed
        calibrated[edge_id] = {
            "baseline_vehicles": round(max(0.0, calibrated_hourly), 2),
            "observed_daily_count": round(median_daily, 2),
            "matched_points": len(points),
            "nearest_count_distance_miles": round(min(float(point["snap_distance_miles"]) for point in points), 3),
            "calibration_source": "observed traffic count",
        }
        if assumed > 0:
            class_ratios[str(edge.get("highway", "unknown"))].append(calibrated_hourly / assumed)

    class_factors: dict[str, float] = {}
    for highway, ratios in class_ratios.items():
        ratios = sorted(ratios)
        factor = ratios[len(ratios) // 2]
        class_factors[highway] = max(0.35, min(2.5, factor))

    inferred_count = 0
    for edge in edges:
        edge_id = str(edge["edge_id"])
        if edge_id in calibrated:
            continue
        highway = str(edge.get("highway", "unknown"))
        if highway not in class_factors:
            continue
        factor = class_factors[highway]
        calibrated[edge_id] = {
            "baseline_vehicles": round(float(edge.get("baseline_vehicles", 0.0)) * factor, 2),
            "observed_daily_count": None,
            "matched_points": 0,
            "nearest_count_distance_miles": None,
            "calibration_source": f"road-class factor inferred from observed {highway} counts",
        }
        inferred_count += 1

    profile = {
        "mode": "traffic_calibration",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": str(path),
        "osm_profile_path": str(osm_path.resolve()),
        "settings": {
            "peak_hour_factor": peak_hour_factor,
            "directional_factor": directional_factor,
            "max_snap_miles": max_snap_miles,
            "max_rows": max_rows,
        },
        "fields": {"latitude": lat_field, "longitude": lon_field, "count": count_field, "name": name_field},
        "input_rows": len(rows),
        "usable_count_points": len(count_points),
        "matched_count_points": len(count_points) - unmatched,
        "unmatched_count_points": unmatched,
        "directly_calibrated_edges": len(matched_by_edge),
        "class_inferred_edges": inferred_count,
        "class_factors": {key: round(value, 3) for key, value in class_factors.items()},
        "edge_calibration": calibrated,
        "count_points": count_points[:5000],
        "disclaimer": (
            "Daily traffic counts are converted to a directional event-hour baseline using configurable factors. "
            "This is a planning calibration, not an official design-hour traffic forecast."
        ),
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def load_traffic_profile(path: str | Path) -> dict[str, Any] | None:
    profile_path = Path(path)
    if not profile_path.exists():
        return None
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("edge_calibration"), dict):
        return None
    return payload
