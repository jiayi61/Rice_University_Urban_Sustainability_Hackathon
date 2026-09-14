from __future__ import annotations

import csv
import io
import json
import math
import zipfile
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO

from .sample_data import load_demo_zones

REQUIRED_FILES = {"stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}
OPTIONAL_FILES = {"agency.txt", "calendar.txt", "calendar_dates.txt"}
VENUE = {"name": "Houston Stadium / NRG Stadium", "lat": 29.6847, "lon": -95.4107}


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_miles * math.asin(math.sqrt(a))


def _parse_service_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("event_date must use YYYY-MM-DD.") from exc


def _parse_clock(value: str) -> int:
    try:
        parsed = datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError("kickoff_time must use HH:MM in 24-hour time.") from exc
    return parsed.hour * 60 + parsed.minute


def _gtfs_minutes(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) != 3:
        return None
    try:
        hours, minutes, seconds = (int(part) for part in parts)
    except ValueError:
        return None
    return hours * 60 + minutes + (1 if seconds >= 30 else 0)


def _safe_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class GTFSFeed:
    def __init__(self, source: str | Path) -> None:
        self.source = Path(source).expanduser().resolve()
        if not self.source.exists():
            raise FileNotFoundError(f"GTFS source not found: {self.source}")
        self.is_zip = self.source.is_file() and self.source.suffix.lower() == ".zip"
        if not self.is_zip and not self.source.is_dir():
            raise ValueError("GTFS source must be a .zip file or a folder containing GTFS .txt files.")
        if self.source.is_file() and not self.is_zip:
            raise ValueError("GTFS source file must have a .zip extension.")

    def names(self) -> set[str]:
        if self.is_zip:
            with zipfile.ZipFile(self.source) as archive:
                return {Path(name).name for name in archive.namelist() if not name.endswith("/")}
        return {path.name for path in self.source.glob("*.txt")}

    @contextmanager
    def open_text(self, name: str) -> Iterator[TextIO]:
        if self.is_zip:
            archive = zipfile.ZipFile(self.source)
            matching = next((item for item in archive.namelist() if Path(item).name == name), None)
            if matching is None:
                archive.close()
                raise FileNotFoundError(f"{name} not found in {self.source}")
            raw = archive.open(matching)
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
            try:
                yield text
            finally:
                text.close()
                archive.close()
            return

        path = self.source / name
        if not path.exists():
            raise FileNotFoundError(f"{name} not found in {self.source}")
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield handle

    def rows(self, name: str) -> Iterable[dict[str, str]]:
        with self.open_text(name) as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yield {str(key): str(value or "") for key, value in row.items() if key is not None}


def scan_gtfs(source: str | Path) -> dict[str, Any]:
    feed = GTFSFeed(source)
    names = feed.names()
    missing = sorted(REQUIRED_FILES - names)
    agency_names: list[str] = []
    if "agency.txt" in names:
        for row in feed.rows("agency.txt"):
            name = row.get("agency_name", "").strip()
            if name:
                agency_names.append(name)
    return {
        "source": str(feed.source),
        "kind": "zip" if feed.is_zip else "folder",
        "files": sorted(names),
        "required_present": sorted(REQUIRED_FILES & names),
        "optional_present": sorted(OPTIONAL_FILES & names),
        "missing_required": missing,
        "ready": not missing,
        "agency_names": agency_names,
    }


def _active_service_ids(feed: GTFSFeed, names: set[str], service_date: date) -> set[str] | None:
    active: set[str] | None = None
    if "calendar.txt" in names:
        active = set()
        weekday = service_date.strftime("%A").lower()
        target = service_date.strftime("%Y%m%d")
        for row in feed.rows("calendar.txt"):
            service_id = row.get("service_id", "").strip()
            if not service_id:
                continue
            start = row.get("start_date", "")
            end = row.get("end_date", "")
            if start and target < start:
                continue
            if end and target > end:
                continue
            if row.get(weekday, "0").strip() == "1":
                active.add(service_id)

    if "calendar_dates.txt" in names:
        if active is None:
            active = set()
        target = service_date.strftime("%Y%m%d")
        for row in feed.rows("calendar_dates.txt"):
            if row.get("date", "").strip() != target:
                continue
            service_id = row.get("service_id", "").strip()
            exception = row.get("exception_type", "").strip()
            if exception == "1":
                active.add(service_id)
            elif exception == "2":
                active.discard(service_id)
    return active


def _score_access(nearest: float | None, stops_1mi: int, routes: int, departures_peak: int) -> float:
    nearest_component = 0.0 if nearest is None else max(0.0, 1.0 - nearest / 2.0)
    score = (
        25.0 * nearest_component
        + 20.0 * min(1.0, stops_1mi / 10.0)
        + 20.0 * min(1.0, routes / 8.0)
        + 35.0 * min(1.0, departures_peak / 60.0)
    )
    return round(max(0.0, min(100.0, score)), 1)


def _route_mode(route_type: str) -> str:
    value = str(route_type or "").strip()
    return {
        "0": "tram/light rail",
        "1": "subway/metro",
        "2": "rail",
        "3": "bus",
        "4": "ferry",
        "5": "cable tram",
        "6": "aerial lift",
        "7": "funicular",
        "11": "trolleybus",
        "12": "monorail",
    }.get(value, "other")


def build_gtfs_profile(
    source: str | Path,
    output_path: str | Path,
    *,
    event_date: str,
    kickoff_time: str,
    venue_lat: float = VENUE["lat"],
    venue_lon: float = VENUE["lon"],
) -> dict[str, Any]:
    feed = GTFSFeed(source)
    names = feed.names()
    missing = REQUIRED_FILES - names
    if missing:
        raise ValueError(f"Missing required GTFS files: {sorted(missing)}")

    service_date = _parse_service_date(event_date)
    kickoff = _parse_clock(kickoff_time)
    active_services = _active_service_ids(feed, names, service_date)

    agency_names: list[str] = []
    if "agency.txt" in names:
        for row in feed.rows("agency.txt"):
            name = row.get("agency_name", "").strip()
            if name:
                agency_names.append(name)

    stops: dict[str, dict[str, Any]] = {}
    locations = {
        "stadium": {"name": VENUE["name"], "lat": venue_lat, "lon": venue_lon},
        **{
            zone.zone_id: {"name": zone.name, "lat": zone.lat, "lon": zone.lon}
            for zone in load_demo_zones()
        },
    }
    location_stop_distances: dict[str, dict[str, float]] = {key: {} for key in locations}

    for row in feed.rows("stops.txt"):
        stop_id = row.get("stop_id", "").strip()
        lat = _safe_float(row.get("stop_lat"))
        lon = _safe_float(row.get("stop_lon"))
        if not stop_id or lat is None or lon is None:
            continue
        stops[stop_id] = {
            "stop_id": stop_id,
            "stop_name": row.get("stop_name", "").strip() or stop_id,
            "lat": lat,
            "lon": lon,
        }
        for key, location in locations.items():
            distance = _haversine_miles(lat, lon, float(location["lat"]), float(location["lon"]))
            if distance <= 5.0:
                location_stop_distances[key][stop_id] = distance

    routes: dict[str, dict[str, str]] = {}
    for row in feed.rows("routes.txt"):
        route_id = row.get("route_id", "").strip()
        if not route_id:
            continue
        routes[route_id] = {
            "route_id": route_id,
            "short_name": row.get("route_short_name", "").strip(),
            "long_name": row.get("route_long_name", "").strip(),
            "mode": _route_mode(row.get("route_type", "")),
        }

    trip_to_route: dict[str, str] = {}
    for row in feed.rows("trips.txt"):
        trip_id = row.get("trip_id", "").strip()
        route_id = row.get("route_id", "").strip()
        service_id = row.get("service_id", "").strip()
        if not trip_id or not route_id:
            continue
        if active_services is not None and service_id not in active_services:
            continue
        trip_to_route[trip_id] = route_id

    windows = {
        "pre_match": (kickoff - 180, kickoff - 60),
        "ingress_peak": (kickoff - 60, kickoff),
        "egress_peak": (kickoff + 120, kickoff + 240),
    }
    location_departures: dict[str, dict[str, int]] = {
        key: {window: 0 for window in windows} for key in locations
    }
    location_routes: dict[str, set[str]] = {key: set() for key in locations}
    location_modes: dict[str, defaultdict[str, int]] = {
        key: defaultdict(int) for key in locations
    }
    relevant_stop_to_locations: dict[str, list[str]] = defaultdict(list)
    for key, distances in location_stop_distances.items():
        for stop_id, distance in distances.items():
            if distance <= 1.5:
                relevant_stop_to_locations[stop_id].append(key)

    stop_time_rows = 0
    matched_stop_time_rows = 0
    for row in feed.rows("stop_times.txt"):
        stop_time_rows += 1
        trip_id = row.get("trip_id", "").strip()
        stop_id = row.get("stop_id", "").strip()
        if trip_id not in trip_to_route or stop_id not in relevant_stop_to_locations:
            continue
        minute = _gtfs_minutes(row.get("departure_time") or row.get("arrival_time"))
        if minute is None:
            continue
        route_id = trip_to_route[trip_id]
        route = routes.get(route_id, {"mode": "other"})
        for location_key in relevant_stop_to_locations[stop_id]:
            matched_stop_time_rows += 1
            location_routes[location_key].add(route_id)
            location_modes[location_key][route.get("mode", "other")] += 1
            for window_name, (start, end) in windows.items():
                if start <= minute <= end:
                    location_departures[location_key][window_name] += 1

    access: dict[str, Any] = {}
    for key, location in locations.items():
        distances = location_stop_distances[key]
        nearest = min(distances.values()) if distances else None
        stops_1mi = sum(distance <= 1.0 for distance in distances.values())
        stops_3mi = sum(distance <= 3.0 for distance in distances.values())
        route_ids = location_routes[key]
        access[key] = {
            "name": location["name"],
            "lat": location["lat"],
            "lon": location["lon"],
            "nearest_stop_miles": round(nearest, 3) if nearest is not None else None,
            "stops_1mi": stops_1mi,
            "stops_3mi": stops_3mi,
            "route_count": len(route_ids),
            "routes": [
                routes.get(route_id, {"route_id": route_id, "short_name": "", "long_name": "", "mode": "other"})
                for route_id in sorted(route_ids)
            ],
            "departures": location_departures[key],
            "mode_observations": dict(location_modes[key]),
            "access_score": _score_access(
                nearest,
                stops_1mi,
                len(route_ids),
                location_departures[key]["ingress_peak"],
            ),
        }

    warnings: list[str] = []
    if active_services is not None and not active_services:
        warnings.append("No active service IDs were found for the selected event date.")
    if not trip_to_route:
        warnings.append("No active trips were found for the selected event date.")
    if access.get("stadium", {}).get("stops_3mi", 0) == 0:
        warnings.append("No GTFS stops were found within three miles of the stadium.")

    is_metro = any("metro" in name.casefold() or "metropolitan transit authority" in name.casefold() for name in agency_names)
    attribution = (
        "Data is provided by permission of The Metropolitan Transit Authority of Harris County, Texas."
        if is_metro
        else "GTFS data is provided by the publishing transit agency; verify and display the agency's required attribution."
    )

    profile = {
        "mode": "gtfs_schedule",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": str(feed.source),
        "source_kind": "zip" if feed.is_zip else "folder",
        "agency_names": agency_names,
        "event_date": event_date,
        "kickoff_time": kickoff_time,
        "active_service_filter": active_services is not None,
        "active_service_count": len(active_services or []),
        "feed_summary": {
            "stop_count": len(stops),
            "route_count": len(routes),
            "active_trip_count": len(trip_to_route),
            "stop_time_rows": stop_time_rows,
            "matched_stop_time_rows": matched_stop_time_rows,
        },
        "access": access,
        "attribution": attribution,
        "warnings": warnings,
        "disclaimer": "Schedule-based accessibility profile. It does not include real-time delays, crowding, temporary event service, or guaranteed vehicle capacity.",
    }

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile
