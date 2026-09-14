from __future__ import annotations

import csv
import gzip
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .sample_data import load_demo_zones

DATASET_DIRS = {
    "poi": "core-poi-geometry-rice",
    "visits": "store-visits-rice",
    "spend_patterns": "spend-patterns-rice",
    "daily_spend": "daily-spend-brand-and-state-rice",
    "weather": "daily-weather-rice",
    "uhi": "urban-heat-index-rice",
}

HOUSTON_BOUNDS = {
    "min_lat": 29.45,
    "max_lat": 30.20,
    "min_lon": -95.85,
    "max_lon": -94.95,
}

RESOURCE_KEYWORDS = {
    "hospital", "medical", "clinic", "pharmacy", "drug store", "grocery",
    "supermarket", "convenience", "restaurant", "cafe", "coffee", "shopping",
    "mall", "department store", "library", "recreation", "park",
}

WEATHER_TOKENS = ("HOUSTON", "HOU", "IAH", "HOBBY", "KHOU", "KIAH")


def discover_files(root: str | Path, dataset_key: str) -> list[Path]:
    root_path = Path(root).expanduser().resolve()
    folder = root_path / DATASET_DIRS[dataset_key]
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(folder.glob("*.csv.gz"))


def read_header(path: str | Path) -> list[str]:
    with gzip.open(Path(path), "rt", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            return []


def scan_root(root: str | Path) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    report: dict[str, Any] = {
        "root": str(root_path),
        "exists": root_path.exists(),
        "datasets": {},
    }
    for key, dirname in DATASET_DIRS.items():
        folder = root_path / dirname
        files = discover_files(root_path, key) if folder.exists() else []
        item: dict[str, Any] = {
            "folder": str(folder),
            "exists": folder.exists(),
            "file_count": len(files),
            "first_file": str(files[0]) if files else None,
            "columns": [],
        }
        if files:
            try:
                item["columns"] = read_header(files[0])
            except Exception as exc:  # corrupted or inaccessible archive
                item["error"] = str(exc)
        report["datasets"][key] = item
    report["ready"] = all(report["datasets"][key]["file_count"] > 0 for key in ("poi", "visits", "weather", "uhi"))
    return report


def _clean_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.casefold() in {"nan", "none", "null"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _text(row: dict[str, str], field: str) -> str:
    return str(row.get(field, "") or "").strip()


def _contains_city(row: dict[str, str], city: str) -> bool:
    city_fold = city.casefold()
    for field in ("CITY", "MARKET", "LOCATION_NAME", "REGION"):
        value = _text(row, field).casefold()
        if city_fold and city_fold in value:
            return True
    return False


def _coordinates(row: dict[str, str]) -> tuple[float, float] | None:
    lat = _clean_number(row.get("LATITUDE"))
    lon = _clean_number(row.get("LONGITUDE"))
    if lat is None or lon is None:
        return None
    return lat, lon


def _inside_houston(lat: float, lon: float) -> bool:
    return (
        HOUSTON_BOUNDS["min_lat"] <= lat <= HOUSTON_BOUNDS["max_lat"]
        and HOUSTON_BOUNDS["min_lon"] <= lon <= HOUSTON_BOUNDS["max_lon"]
    )


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_miles * math.asin(math.sqrt(a))


def _nearest_zone(lat: float, lon: float) -> str | None:
    zones = load_demo_zones()
    nearest = min(zones, key=lambda zone: _haversine_miles(lat, lon, zone.lat, zone.lon))
    distance = _haversine_miles(lat, lon, nearest.lat, nearest.lon)
    return nearest.zone_id if distance <= 35 else None


def _is_resource(row: dict[str, str]) -> bool:
    combined = " ".join(
        _text(row, field)
        for field in ("TOP_CATEGORY", "SUB_CATEGORY", "TOP_CATEGORY_2022", "SUB_CATEGORY_2022", "CATEGORY_TAGS", "CATEGORY")
    ).casefold()
    return any(keyword in combined for keyword in RESOURCE_KEYWORDS)


def _iter_rows(files: Iterable[Path], max_rows_per_file: int) -> Iterable[tuple[Path, dict[str, str]]]:
    for file_path in files:
        with gzip.open(file_path, "rt", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                if index >= max_rows_per_file:
                    break
                yield file_path, row


def _source_report(files_found: int) -> dict[str, Any]:
    return {
        "files_found": files_found,
        "files_scanned": 0,
        "rows_read": 0,
        "rows_matched": 0,
        "columns": [],
    }


def _safe_share(values: dict[str, float], zone_ids: list[str]) -> dict[str, float]:
    total = sum(max(0.0, values.get(zone_id, 0.0)) for zone_id in zone_ids)
    if total <= 0:
        return {zone_id: 1.0 / len(zone_ids) for zone_id in zone_ids}
    return {zone_id: max(0.0, values.get(zone_id, 0.0)) / total for zone_id in zone_ids}


def _minmax_gap(values: dict[str, float], fallback: dict[str, float]) -> dict[str, float]:
    clean = [value for value in values.values() if math.isfinite(value)]
    if not clean or max(clean) - min(clean) < 1e-9:
        return fallback
    low, high = min(clean), max(clean)
    return {zone_id: 1.0 - (values[zone_id] - low) / (high - low) for zone_id in values}


def _heat_index_f(temp_c: float | None, humidity: float | None) -> float | None:
    if temp_c is None:
        return None
    temp_f = temp_c * 9 / 5 + 32
    if humidity is None or temp_f < 80:
        return temp_f
    rh = humidity
    hi = (
        -42.379
        + 2.04901523 * temp_f
        + 10.14333127 * rh
        - 0.22475541 * temp_f * rh
        - 0.00683783 * temp_f * temp_f
        - 0.05481717 * rh * rh
        + 0.00122874 * temp_f * temp_f * rh
        + 0.00085282 * temp_f * rh * rh
        - 0.00000199 * temp_f * temp_f * rh * rh
    )
    return max(temp_f, hi)


def build_houston_profile(
    root: str | Path,
    output_path: str | Path,
    *,
    city: str = "Houston",
    max_files: int = 1,
    max_rows_per_file: int = 75_000,
    event_attendance: int = 72_000,
) -> dict[str, Any]:
    if max_files < 1 or max_files > 32:
        raise ValueError("max_files must be between 1 and 32.")
    if max_rows_per_file < 1_000 or max_rows_per_file > 1_000_000:
        raise ValueError("max_rows_per_file must be between 1,000 and 1,000,000.")

    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Dataset root not found: {root_path}")

    demo_zones = load_demo_zones()
    zone_ids = [zone.zone_id for zone in demo_zones]
    zone_centers = {zone.zone_id: {"name": zone.name, "lat": zone.lat, "lon": zone.lon} for zone in demo_zones}
    default_gap = {zone.zone_id: zone.resource_gap for zone in demo_zones}

    poi_count = defaultdict(float)
    resource_count = defaultdict(float)
    visit_total = defaultdict(float)
    spend_total = defaultdict(float)
    customer_total = defaultdict(float)
    uhi_values: dict[str, list[float]] = defaultdict(list)
    store_to_zone: dict[str, str] = {}
    sources: dict[str, Any] = {}
    warnings: list[str] = []

    # POI geometry: creates the spatial store lookup used by the visits dataset.
    poi_files_all = discover_files(root_path, "poi")
    poi_files = poi_files_all[:max_files]
    report = _source_report(len(poi_files_all))
    if poi_files:
        report["columns"] = read_header(poi_files[0])
        report["files_scanned"] = len(poi_files)
        for _, row in _iter_rows(poi_files, max_rows_per_file):
            report["rows_read"] += 1
            coord = _coordinates(row)
            if not (_contains_city(row, city) or (coord and _inside_houston(*coord))):
                continue
            if not coord:
                continue
            zone_id = _nearest_zone(*coord)
            if zone_id is None:
                continue
            report["rows_matched"] += 1
            poi_count[zone_id] += 1
            if _is_resource(row):
                resource_count[zone_id] += 1
            store_id = _text(row, "STORE_ID")
            if store_id:
                store_to_zone[store_id] = zone_id
    else:
        warnings.append("POI dataset was not found; zone activity uses fallback weights.")
    sources["poi"] = report

    # UHI: directly spatial and therefore highly useful for corridor heat adjustment.
    uhi_files_all = discover_files(root_path, "uhi")
    uhi_files = uhi_files_all[:max_files]
    report = _source_report(len(uhi_files_all))
    if uhi_files:
        report["columns"] = read_header(uhi_files[0])
        report["files_scanned"] = len(uhi_files)
        for _, row in _iter_rows(uhi_files, max_rows_per_file):
            report["rows_read"] += 1
            coord = _coordinates(row)
            if not (_contains_city(row, city) or (coord and _inside_houston(*coord))):
                continue
            if not coord:
                continue
            zone_id = _nearest_zone(*coord)
            value = _clean_number(row.get("UHI"))
            if zone_id is None or value is None:
                continue
            report["rows_matched"] += 1
            uhi_values[zone_id].append(value)
    else:
        warnings.append("Urban heat dataset was not found; demo heat values remain in use.")
    sources["uhi"] = report

    # Spend patterns: spatial demand and activity proxy.
    spend_files_all = discover_files(root_path, "spend_patterns")
    spend_files = spend_files_all[:max_files]
    report = _source_report(len(spend_files_all))
    if spend_files:
        report["columns"] = read_header(spend_files[0])
        report["files_scanned"] = len(spend_files)
        for _, row in _iter_rows(spend_files, max_rows_per_file):
            report["rows_read"] += 1
            coord = _coordinates(row)
            if not (_contains_city(row, city) or (coord and _inside_houston(*coord))):
                continue
            if not coord:
                continue
            zone_id = _nearest_zone(*coord)
            if zone_id is None:
                continue
            report["rows_matched"] += 1
            customer_total[zone_id] += _clean_number(row.get("RAW_NUM_CUSTOMERS")) or 0.0
            spend_total[zone_id] += _clean_number(row.get("RAW_TOTAL_SPEND")) or 0.0
    else:
        warnings.append("Spend-pattern dataset was not found; demand uses POI and visit proxies only.")
    sources["spend_patterns"] = report

    # Store visits: spatialized through STORE_ID join when possible.
    visit_files_all = discover_files(root_path, "visits")
    visit_files = visit_files_all[:max_files]
    report = _source_report(len(visit_files_all))
    citywide_visit_total = 0.0
    mapped_visit_total = 0.0
    if visit_files:
        report["columns"] = read_header(visit_files[0])
        report["files_scanned"] = len(visit_files)
        for _, row in _iter_rows(visit_files, max_rows_per_file):
            report["rows_read"] += 1
            store_id = _text(row, "STORE_ID")
            zone_id = store_to_zone.get(store_id)
            city_match = _contains_city(row, city)
            if not city_match and zone_id is None:
                continue
            value = _clean_number(row.get("DAILY_VISITS")) or 0.0
            citywide_visit_total += value
            if zone_id is not None:
                visit_total[zone_id] += value
                mapped_visit_total += value
            report["rows_matched"] += 1
        if citywide_visit_total > 0 and mapped_visit_total / citywide_visit_total < 0.20:
            poi_share = _safe_share(dict(poi_count), zone_ids)
            for zone_id in zone_ids:
                visit_total[zone_id] = citywide_visit_total * poi_share[zone_id]
            warnings.append("Store-visit rows had a limited POI join; citywide visits were allocated by POI share.")
    else:
        warnings.append("Store-visits dataset was not found; demand uses other available proxies.")
    sources["visits"] = report

    # Daily spend is city-level in this dataset and is retained as context.
    daily_files_all = discover_files(root_path, "daily_spend")
    daily_files = daily_files_all[:max_files]
    report = _source_report(len(daily_files_all))
    daily_spend_amount = 0.0
    daily_transactions = 0.0
    if daily_files:
        report["columns"] = read_header(daily_files[0])
        report["files_scanned"] = len(daily_files)
        for _, row in _iter_rows(daily_files, max_rows_per_file):
            report["rows_read"] += 1
            if not _contains_city(row, city):
                continue
            report["rows_matched"] += 1
            daily_spend_amount += _clean_number(row.get("SPEND_AMOUNT")) or 0.0
            daily_transactions += _clean_number(row.get("TRANS_COUNT")) or 0.0
    sources["daily_spend"] = report

    # Weather: match station identifiers conservatively; fall back without pretending a match.
    weather_files_all = discover_files(root_path, "weather")
    weather_files = weather_files_all[:max_files]
    report = _source_report(len(weather_files_all))
    max_temps: list[float] = []
    avg_temps: list[float] = []
    humidities: list[float] = []
    if weather_files:
        report["columns"] = read_header(weather_files[0])
        report["files_scanned"] = len(weather_files)
        identifier_field = "CITY_LOCATION_IDENTIFIER__UP_TO_9_ALPHANUMERIC_CHARACTERS_"
        for _, row in _iter_rows(weather_files, max_rows_per_file):
            report["rows_read"] += 1
            identifier = _text(row, identifier_field).upper()
            if not any(token in identifier for token in WEATHER_TOKENS):
                continue
            report["rows_matched"] += 1
            value = _clean_number(row.get("MAXIMUM_TEMPERATURE_C___FLOAT_VALUE_TO_NEAREST_HUNDREDTHS_PLACE"))
            if value is not None and -20 <= value <= 60:
                max_temps.append(value)
            value = _clean_number(row.get("AVERAGE_TEMPERATURE_C___FLOAT_VALUE_TO_NEAREST_HUNDREDTHS_PLACE"))
            if value is not None and -20 <= value <= 60:
                avg_temps.append(value)
            value = _clean_number(row.get("AVERAGE_RELATIVE_HUMIDITY_____FLOAT_VALUE_TO_NEAREST_HUNDREDTHS_PLACE"))
            if value is not None and 0 <= value <= 100:
                humidities.append(value)
        if not max_temps:
            warnings.append("No Houston-like weather station identifier was matched; demo temperature remains in use.")
    else:
        warnings.append("Weather dataset was not found; demo temperature remains in use.")
    sources["weather"] = report

    poi_share = _safe_share(dict(poi_count), zone_ids)
    visit_share = _safe_share(dict(visit_total), zone_ids)
    customer_share = _safe_share(dict(customer_total), zone_ids)
    spend_share = _safe_share(dict(spend_total), zone_ids)

    raw_demand_share = {
        zone_id: 0.30 * poi_share[zone_id] + 0.40 * visit_share[zone_id] + 0.20 * customer_share[zone_id] + 0.10 * spend_share[zone_id]
        for zone_id in zone_ids
    }
    demand_share = _safe_share(raw_demand_share, zone_ids)
    modeled_demand = event_attendance * 0.78

    resource_ratio = {
        zone_id: resource_count.get(zone_id, 0.0) / max(1.0, poi_count.get(zone_id, 0.0))
        for zone_id in zone_ids
    }
    resource_gap = _minmax_gap(resource_ratio, default_gap)

    uhi_mean_by_zone = {
        zone_id: (sum(uhi_values[zone_id]) / len(uhi_values[zone_id])) if uhi_values[zone_id] else 6.0
        for zone_id in zone_ids
    }
    city_uhi_mean = sum(uhi_mean_by_zone.values()) / len(zone_ids)
    max_temp_c = max(max_temps) if max_temps else 35.0
    avg_humidity = sum(humidities) / len(humidities) if humidities else 58.0
    base_heat_f = _heat_index_f(max_temp_c, avg_humidity) or 96.0

    zones = []
    for zone_id in zone_ids:
        center = zone_centers[zone_id]
        adjusted_heat = max(80.0, min(125.0, base_heat_f + (uhi_mean_by_zone[zone_id] - city_uhi_mean) * 1.8))
        zones.append({
            "zone_id": zone_id,
            "name": center["name"],
            "lat": center["lat"],
            "lon": center["lon"],
            "demand": round(modeled_demand * demand_share[zone_id], 1),
            "heat_index": round(adjusted_heat, 1),
            "resource_gap": round(max(0.0, min(1.0, resource_gap[zone_id])), 3),
            "signals": {
                "poi_count": int(poi_count.get(zone_id, 0)),
                "resource_count": int(resource_count.get(zone_id, 0)),
                "sampled_visits": round(visit_total.get(zone_id, 0.0), 1),
                "sampled_customers": round(customer_total.get(zone_id, 0.0), 1),
                "sampled_spend": round(spend_total.get(zone_id, 0.0), 2),
                "uhi_mean": round(uhi_mean_by_zone[zone_id], 2),
            },
        })

    profile = {
        "mode": "rice_sampled",
        "city": city,
        "root": str(root_path),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "max_files": max_files,
            "max_rows_per_file": max_rows_per_file,
            "event_attendance": event_attendance,
            "modeled_demand": round(modeled_demand),
        },
        "weather": {
            "matched_rows": len(max_temps),
            "max_temp_c": round(max_temp_c, 2),
            "average_temp_c": round(sum(avg_temps) / len(avg_temps), 2) if avg_temps else None,
            "average_humidity_pct": round(avg_humidity, 2),
            "base_heat_index_f": round(base_heat_f, 1),
        },
        "city_context": {
            "sampled_daily_spend": round(daily_spend_amount, 2),
            "sampled_daily_transactions": round(daily_transactions, 1),
        },
        "sources": sources,
        "zones": zones,
        "warnings": warnings,
        "disclaimer": (
            "This profile uses sampled, anonymized and perturbed hackathon data. "
            "It calibrates the demonstration model and is not an operational traffic forecast."
        ),
    }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def load_profile(path: str | Path) -> dict[str, Any] | None:
    profile_path = Path(path)
    if not profile_path.exists():
        return None
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("zones"), list):
        raise ValueError(f"Invalid local profile: {profile_path}")
    return data
