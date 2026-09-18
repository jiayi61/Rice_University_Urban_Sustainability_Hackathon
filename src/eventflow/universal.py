"""Universal natural-language event planning for EventFlow.

The module deliberately works without an LLM key.  It parses a compact event
brief, enriches it from low-volume public web services when available, and
falls back to transparent venue/city assumptions when a connector is offline.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .platform import MobilityPlatform, TIME_POINTS, _pulse
from .api_config import load_env, api_status
from .brief_api import extract_brief
from .screening import simulate_event
from .data_repository import DataRepository, TRAFFIC_KEY, TRAFFIC_LAYER, TRAFFIC_BBOX, fetch_houston_sites
from .site_selection import select_sites, site_origins


USER_AGENT = "EventFlow-Mobility-Research/3.0 (university planning prototype)"
GEOCODE_LOCK = threading.Lock()
GEOCODE_LAST = 0.0
MONTHS = {name.lower(): number for number, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1
)}

# Fast, auditable defaults for common global event cities. Online lookup can
# verify/replace these; the values keep the demo useful during an API outage.
CITY_SEEDS: dict[str, dict[str, Any]] = {
    "london": {
        "city": "London", "country": "United Kingdom", "country_code": "gb", "currency": "GBP", "symbol": "£",
        "venue": "Wembley Stadium", "lat": 51.55607, "lon": -0.27960, "capacity": 90000,
        "center": [51.5074, -0.1278], "cost_factor": 1.16,
        "origins": [
            ("Wembley Park", "rail", 51.5632, -0.2795, 0.18),
            ("London Euston", "rail", 51.5282, -0.1337, 0.14),
            ("Paddington / hotel district", "rail", 51.5154, -0.1755, 0.13),
            ("West End / Central London", "rail", 51.5115, -0.1281, 0.15),
            ("King's Cross St Pancras", "rail", 51.5308, -0.1238, 0.10),
            ("Heathrow Airport", "airport rail + coach", 51.4700, -0.4543, 0.11),
            ("Wembley Central", "rail + walk", 51.5523, -0.2968, 0.10),
            ("West London intercept parking", "park-and-ride shuttle", 51.5470, -0.3370, 0.09),
        ],
        "transit_lines": [
            ("Metropolitan line", "rail", "#8b004f", [[51.5308, -0.1238], [51.5467, -0.1901], [51.5632, -0.2795]]),
            ("Jubilee line", "rail", "#7c878e", [[51.5030, -0.1132], [51.5226, -0.1566], [51.5632, -0.2795]]),
            ("London Overground / Bakerloo", "rail", "#e86a10", [[51.5282, -0.1337], [51.5343, -0.2206], [51.5523, -0.2968]]),
        ],
    },
    "houston": {"city": "Houston", "country": "United States", "country_code": "us", "currency": "USD", "symbol": "$", "venue": "NRG Stadium", "lat": 29.6847, "lon": -95.4107, "capacity": 72220, "center": [29.7604, -95.3698], "cost_factor": 1.0},
    "new york": {"city": "New York / New Jersey", "country": "United States", "country_code": "us", "currency": "USD", "symbol": "$", "venue": "MetLife Stadium", "lat": 40.8135, "lon": -74.0745, "capacity": 82500, "center": [40.7580, -73.9855], "cost_factor": 1.12},
    "los angeles": {"city": "Los Angeles", "country": "United States", "country_code": "us", "currency": "USD", "symbol": "$", "venue": "SoFi Stadium", "lat": 33.9535, "lon": -118.3392, "capacity": 70240, "center": [34.0522, -118.2437], "cost_factor": 1.14},
    "paris": {"city": "Paris", "country": "France", "country_code": "fr", "currency": "EUR", "symbol": "€", "venue": "Stade de France", "lat": 48.9245, "lon": 2.3601, "capacity": 80698, "center": [48.8566, 2.3522], "cost_factor": 1.12},
    "madrid": {"city": "Madrid", "country": "Spain", "country_code": "es", "currency": "EUR", "symbol": "€", "venue": "Santiago Bernabéu Stadium", "lat": 40.4531, "lon": -3.6883, "capacity": 83186, "center": [40.4168, -3.7038], "cost_factor": .94},
    "toronto": {"city": "Toronto", "country": "Canada", "country_code": "ca", "currency": "CAD", "symbol": "C$", "venue": "Rogers Centre", "lat": 43.6414, "lon": -79.3894, "capacity": 49000, "center": [43.6532, -79.3832], "cost_factor": 1.04},
    "mexico city": {"city": "Mexico City", "country": "Mexico", "country_code": "mx", "currency": "MXN", "symbol": "MX$", "venue": "Estadio Azteca", "lat": 19.3029, "lon": -99.1505, "capacity": 83264, "center": [19.4326, -99.1332], "cost_factor": .61},
    "tokyo": {"city": "Tokyo", "country": "Japan", "country_code": "jp", "currency": "JPY", "symbol": "¥", "venue": "Tokyo Dome", "lat": 35.7056, "lon": 139.7519, "capacity": 55000, "center": [35.6762, 139.6503], "cost_factor": 1.02},
}

CURRENCY_BY_COUNTRY = {"gb": ("GBP", "£"), "us": ("USD", "$"), "fr": ("EUR", "€"), "es": ("EUR", "€"), "de": ("EUR", "€"), "it": ("EUR", "€"), "ca": ("CAD", "C$"), "mx": ("MXN", "MX$"), "jp": ("JPY", "¥"), "au": ("AUD", "A$"), "br": ("BRL", "R$"), "ch": ("CHF", "CHF")}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "event"


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


class UniversalPlanner:
    def __init__(self, root: str | Path, platform: MobilityPlatform):
        self.root = Path(root)
        load_env(self.root)
        self.platform = platform
        self.database = DataRepository(self.root)
        self.cache_dir = self.root / "data" / "cache" / "universal"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def parse_brief(prompt: str) -> dict[str, Any]:
        text = " ".join(str(prompt).strip().split())
        if len(text) < 8:
            raise ValueError("Describe an event, city and approximate date (for example: Shakira concert in London June 8th 2027).")
        month_pattern = "|".join(name.title() for name in MONTHS)
        date_match = re.search(rf"\b({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(\d{{4}})\b", text, re.I)
        if date_match:
            event_date = date(int(date_match.group(3)), MONTHS[date_match.group(1).lower()], int(date_match.group(2))).isoformat()
            date_start = date_match.start()
        else:
            iso_match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
            event_date = iso_match.group(0) if iso_match else "date not specified"
            date_start = iso_match.start() if iso_match else len(text)
        venue_match = re.search(r"\bat\s+(.+?)(?=\s+in\s+|\s+(?:on\s+)?(?:20\d{2}|" + month_pattern + r")\b|$)", text, re.I)
        city_match = re.search(r"\bin\s+(.+?)(?=\s+(?:on\s+)?(?:20\d{2}|" + month_pattern + r")\b|$)", text, re.I)
        city = re.split(r'[.!?]|\s+(?:attendance|crowd|budget)\b', city_match.group(1), maxsplit=1, flags=re.I)[0].strip(" ,.") if city_match else ""
        venue = venue_match.group(1).strip(" ,.") if venue_match else ""
        lowered = text.lower()
        if any(word in lowered for word in ("concert", "tour", "live show", "gig")):
            event_type, default_time = "stadium_concert", "19:30"
        elif any(word in lowered for word in ("marathon", "road race", "10k", "5k")):
            event_type, default_time = "road_event", "08:00"
        elif any(word in lowered for word in ("festival", "carnival")):
            event_type, default_time = "festival", "14:00"
        elif any(word in lowered for word in ("football", "soccer", "world cup")):
            event_type, default_time = "football", "15:00"
        elif any(word in lowered for word in ("conference", "convention", "expo")):
            event_type, default_time = "convention", "09:00"
        else:
            event_type, default_time = "major_event", "18:00"
        clock_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.I)
        if clock_match:
            hour = int(clock_match.group(1)) % 12 + (12 if clock_match.group(3).lower() == "pm" else 0)
            start_time = f"{hour:02d}:{int(clock_match.group(2) or 0):02d}"
        else:
            start_time = default_time
        core = re.sub(r"^(?:give|show|create|make|run)\s+me\s+(?:projections?|a plan|planning)\s+for\s+", "", text[:date_start], flags=re.I)
        core = re.sub(r"\s+(?:at|in)\s+.+$", "", core, flags=re.I).strip(" ,.")
        title = re.sub(r"^(?:a|an)\s+", "", core, flags=re.I) or "Major event"
        budget_match = re.search(r'\$\s*([\d,]+(?:\.\d+)?)', text)
        return {"prompt": text, "title": title, "short_name": title, "city_query": city, "venue_query": venue, "date": event_date, "start_time": start_time, "event_type": event_type, 'budget_usd': float(budget_match.group(1).replace(',', '')) if budget_match else None}

    def _read_cache(self, key: str, max_age_days: int = 30) -> Any | None:
        return self.database.read(key, max_age_days)

    def _write_cache(self, key: str, payload: Any, source_url: str, max_age_days: int = 30) -> None:
        record = self.database.write(key, payload, source_url, max_age_days)
        payload['_data_access'] = {'tier': 'external API', 'source_url': source_url,
                                   'retrieved_at': record['retrieved_at'], 'key': record['key'],
                                   'max_age_days': max_age_days}

    @staticmethod
    def _get_json(url: str, timeout: float = 7) -> Any:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _nominatim(self, query: str, online: bool = True) -> dict[str, Any] | None:
        global GEOCODE_LAST
        key = f"geocode_{query}"
        cached = self._read_cache(key, 120)
        if cached:
            return cached
        if not online:
            return None
        params = urlencode({"format": "jsonv2", "q": query, "limit": 1, "addressdetails": 1, "extratags": 1})
        endpoint = os.getenv('NOMINATIM_URL', 'https://nominatim.openstreetmap.org').rstrip('/')
        with GEOCODE_LOCK:
            time.sleep(max(0, 1.05 - (time.monotonic() - GEOCODE_LAST)))
            try:
                rows = self._get_json(f"{endpoint}/search?{params}")
            finally:
                GEOCODE_LAST = time.monotonic()
        result = rows[0] if rows else None
        if result:
            self._write_cache(key, result, f'{endpoint}/search?{params}', 120)
        return result

    def _resolve_place(self, parsed: dict[str, Any], online: bool) -> tuple[dict[str, Any], list[dict[str, str]]]:
        city_key = parsed["city_query"].lower().split(',')[0].strip()
        city_key = {'nyc': 'new york', 'new york city': 'new york', 'new york / new jersey': 'new york'}.get(city_key, city_key)
        if not city_key:
            raise ValueError('Please specify a city. No city has been selected automatically.')
        seed = deepcopy(CITY_SEEDS.get(city_key) or {})
        assumptions: list[dict[str, str]] = []
        if seed:
            assumptions.append({"field": "Venue", "value": seed["venue"], "confidence": "medium", "basis": "Best-fit major venue for this event and city; edit the prompt to specify another venue."})
        known_place = self._read_cache(f"geocode_{seed['venue']}, {city_key}", 120) if seed and not parsed['venue_query'] else None
        if parsed["venue_query"] or not seed or known_place:
            query = f"{parsed['venue_query']}, {city_key}" if parsed["venue_query"] else f"stadium, {city_key}"
            try:
                hit = known_place or self._nominatim(query, online=online)
                if hit and (parsed["venue_query"] or not seed or known_place):
                    address = hit.get("address", {})
                    country_code = address.get("country_code", seed.get("country_code", "us"))
                    currency, symbol = CURRENCY_BY_COUNTRY.get(country_code, (seed.get("currency", "USD"), seed.get("symbol", "$")))
                    if parsed['venue_query'] and parsed['venue_query'].casefold() != seed.get('venue', '').casefold():
                        seed.pop('origins', None)
                        seed.pop('transit_lines', None)
                    capacity_text = str(hit.get('extratags', {}).get('capacity', '')).replace(',', '')
                    capacity = int(capacity_text) if capacity_text.isdigit() else 60000
                    seed.update({
                        "city": parsed["city_query"] or address.get("city") or address.get("town") or "Selected city",
                        "country": address.get("country", seed.get("country", "")), "country_code": country_code,
                        "currency": currency, "symbol": symbol, "venue": hit.get("name") or hit.get("display_name", "").split(",")[0],
                        "lat": float(hit["lat"]), "lon": float(hit["lon"]), "capacity": capacity,
                        "center": seed.get("center", [float(hit["lat"]), float(hit["lon"])]), "cost_factor": seed.get("cost_factor", 1.0),
                        '_data_access': hit.get('_data_access', {}),
                    })
                    assumptions[0 if assumptions else 0:] = [{"field": "Venue", "value": seed["venue"], "confidence": "high" if parsed["venue_query"] else "medium", "basis": "Resolved through OpenStreetMap Nominatim."}]
            except Exception:
                hit = None
            if parsed['venue_query'] and not hit and (online or parsed['venue_query'].casefold() != seed.get('venue', '').casefold()):
                raise ValueError('The specified venue could not be verified. Check its name and city, then retry.')
        elif parsed['venue_query'] and parsed['venue_query'].casefold() != seed.get('venue', '').casefold():
            raise ValueError('Online lookup is required to verify this venue.')
        if not seed:
            raise ValueError(f"I could not resolve a venue for ‘{parsed['city_query'] or 'that city'}’. Add a city and, if possible, a venue name.")
        return seed, assumptions

    @staticmethod
    def _attendance(parsed: dict[str, Any], place: dict[str, Any]) -> tuple[int, dict[str, str]]:
        if parsed.get('attendance') is not None:
            value = parsed['attendance']
            return value, {'field': 'Attendance', 'value': str(value), 'confidence': 'high', 'basis': 'User input; not an observed count.'}
        explicit = re.search(r"\b(?:attendance|crowd|capacity)\s*(?:of|=|:)?\s*([\d,]+)", parsed["prompt"], re.I)
        if explicit:
            value = int(explicit.group(1).replace(",", ""))
            if not 500 <= value <= 500000:
                raise ValueError('Attendance must be between 500 and 500,000.')
            return value, {"field": "Attendance", "value": f"{value:,}", "confidence": "high", "basis": "Provided in the event brief."}
        ratio = {"stadium_concert": .83, "football": .96, "festival": .72, "convention": .35, "road_event": .45}.get(parsed["event_type"], .75)
        value = max(500, min(500000, round(place.get("capacity", 60000) * ratio / 500) * 500))
        return value, {"field": "Attendance", "value": f"{value:,}", "confidence": "low", "basis": f"Assumed {ratio:.0%} of planning capacity; capacity may use a 60,000 fallback. Enter an explicit audience count."}

    def _weather(self, place: dict[str, Any], event_date: str, online: bool = True) -> dict[str, Any]:
        key = f"weather_{place['lat']:.3f}_{place['lon']:.3f}_{event_date}"
        cached = self._read_cache(key, 120)
        if cached:
            return cached
        if not online:
            raise LookupError('Weather unavailable in the local database.')
        event_day = date.fromisoformat(event_date) if re.match(r"\d{4}-\d{2}-\d{2}$", event_date) else date.today() + timedelta(days=180)
        last_year = min(event_day.year - 1, date.today().year - 1)
        years = range(max(1940, last_year - 4), last_year + 1)
        days = [date(year, event_day.month, min(event_day.day, 28)) for year in years]
        start, end = min(days) - timedelta(days=12), max(days) + timedelta(days=12)
        params = urlencode({"latitude": place["lat"], "longitude": place["lon"], "start_date": start.isoformat(), "end_date": end.isoformat(), "daily": "temperature_2m_max,precipitation_sum,wind_speed_10m_max", "timezone": "auto"})
        payload = self._get_json(f"https://archive-api.open-meteo.com/v1/archive?{params}", 10)
        daily = payload.get("daily", {})
        selected = []
        for index, raw in enumerate(daily.get("time", [])):
            day = date.fromisoformat(raw)
            if day.month == event_day.month and abs(day.day - event_day.day) <= 12:
                selected.append(index)
        temps = [daily["temperature_2m_max"][i] for i in selected if daily["temperature_2m_max"][i] is not None]
        rain = [daily["precipitation_sum"][i] for i in selected if daily["precipitation_sum"][i] is not None]
        winds = [daily["wind_speed_10m_max"][i] for i in selected if daily["wind_speed_10m_max"][i] is not None]
        c = sum(temps) / len(temps) if temps else 22
        result = {"temperature_c": round(c, 1), "temperature_f": round(c * 9 / 5 + 32), "rain_probability_pct": round(sum(v > 1 for v in rain) / max(1, len(rain)) * 100), "wind_kmh": round(sum(winds) / max(1, len(winds)), 1), "basis": f"Open-Meteo historical normal around this calendar date ({min(years)}–{max(years)})."}
        self._write_cache(key, result, f'https://archive-api.open-meteo.com/v1/archive?{params}', 120)
        return result

    def _exchange_rate(self, currency: str) -> dict[str, Any]:
        if currency == "USD":
            return {"rate": 1.0, "date": date.today().isoformat(), "source": "USD base"}
        cached = self._read_cache(f"fx_usd_{currency}", 7)
        if cached:
            return cached
        payload = self._get_json(f"https://api.frankfurter.app/latest?from=USD&to={currency}", 7)
        result = {"rate": float(payload["rates"][currency]), "date": payload["date"], "source": "Frankfurter / ECB reference rates"}
        self._write_cache(f"fx_usd_{currency}", result, 'https://api.frankfurter.app/latest', 7)
        return result

    def _transport(self, place: dict[str, Any], online: bool = True) -> dict[str, Any]:
        key = f"transport_{place['lat']:.4f}_{place['lon']:.4f}"
        cached = self._read_cache(key, 30)
        if cached:
            return cached
        if not online:
            raise LookupError('Transport unavailable in the local database.')
        query = f'''[out:json][timeout:20];(node(around:6500,{place['lat']},{place['lon']})[railway=station];node(around:6500,{place['lat']},{place['lon']})[amenity=bus_station];node(around:6500,{place['lat']},{place['lon']})[amenity=parking];);out tags center 100;'''
        url = "https://overpass-api.de/api/interpreter?" + urlencode({"data": query})
        payload = self._get_json(url, 24)
        stations = []
        for element in payload.get("elements", []):
            tags = element.get("tags", {})
            kind = "parking" if tags.get("amenity") == "parking" else ("bus" if tags.get("amenity") == "bus_station" else "rail")
            stations.append({"name": tags.get("name") or f"{kind.title()} facility", "mode": kind, "lat": element.get("lat"), "lon": element.get("lon"), "wheelchair": tags.get("wheelchair", "unknown"), 'access': tags.get('access', 'unknown'), 'osm_id': element.get('id')})
        result = {"stations": [s for s in stations if s["lat"] is not None][:60], "source": "OpenStreetMap Overpass", "retrieved": date.today().isoformat()}
        self._write_cache(key, result, url, 30)
        return result

    def _traffic_context(self, place: dict[str, Any], online: bool) -> dict[str, Any]:
        west, south, east, north = TRAFFIC_BBOX
        if not (west <= place['lon'] <= east and south <= place['lat'] <= north):
            return {'features': [], 'source': 'No configured official survey-location connector for this venue.'}
        cached = self._read_cache(TRAFFIC_KEY, 90)
        if cached:
            return cached
        if not online:
            return {'features': [], 'source': 'Official survey locations unavailable locally.'}
        result = fetch_houston_sites(self._get_json)
        self._write_cache(TRAFFIC_KEY, result, TRAFFIC_LAYER, 90)
        return result

    def _osrm(self, origin: tuple[float, float], destination: tuple[float, float], online: bool = True) -> dict[str, Any]:
        key = f"route_{origin[0]:.4f}_{origin[1]:.4f}_{destination[0]:.4f}_{destination[1]:.4f}"
        cached = self._read_cache(key, 120)
        if cached:
            return cached
        if not online:
            raise LookupError('Road route unavailable in the local database.')
        url = f"https://router.project-osrm.org/route/v1/driving/{origin[1]},{origin[0]};{destination[1]},{destination[0]}?overview=full&geometries=geojson"
        payload = self._get_json(url, 12)
        row = payload["routes"][0]
        result = {"distance_km": round(row["distance"] / 1000, 1), "minutes": round(row["duration"] / 60, 1), "geometry": [[lat, lon] for lon, lat in row["geometry"]["coordinates"]], "source": "OpenStreetMap + OSRM (live or cached, up to 120 days)"}
        self._write_cache(key, result, url, 120)
        return result

    @staticmethod
    def _fallback_origins(place: dict[str, Any]) -> list[tuple[str, str, float, float, float]]:
        if place.get("origins"):
            return place["origins"]
        lat, lon = place["lat"], place["lon"]
        center = place.get("center", [lat + .05, lon + .05])
        return [
            ("City centre / hotels", "rail + shuttle", center[0], center[1], .24),
            ("Central rail station", "rail", center[0] + .012, center[1] - .008, .16),
            ("North visitor catchment", "bus + shuttle", lat + .075, lon, .12),
            ("East visitor catchment", "bus + rideshare", lat, lon + .085, .12),
            ("South visitor catchment", "park-and-ride shuttle", lat - .075, lon, .12),
            ("West visitor catchment", "bus + rideshare", lat, lon - .085, .12),
            ("Airport / regional arrivals", "airport rail + coach", lat + .13, lon + .11, .12),
        ]

    def _zones_and_routes(self, place: dict[str, Any], attendance: int, base_plans: list[dict[str, Any]], online: bool) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        origins = self._fallback_origins(place)
        total_share = sum(row[4] for row in origins)
        zones, route_base = [], {}
        remaining = attendance
        destination = (place["lat"], place["lon"])
        route_results: dict[int, dict[str, Any]] = {}
        return_results: dict[int, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {}
            for index, row in enumerate(origins):
                origin = (row[2], row[3])
                # Egress: occupied bus leaves venue, then returns to collect again.
                futures[pool.submit(self._osrm, destination, origin, online=online)] = (index, 'outbound')
                futures[pool.submit(self._osrm, origin, destination, online=online)] = (index, 'return')
            for future in as_completed(futures):
                try:
                    index, direction = futures[future]
                    (route_results if direction == 'outbound' else return_results)[index] = future.result()
                except Exception:
                    pass
        for index, (name, mode, lat, lon, share) in enumerate(origins):
            visitors = remaining if index == len(origins) - 1 else round(attendance * share / total_share)
            remaining -= visitors
            distance = _distance_km((lat, lon), destination)
            fallback = {"distance_km": round(distance, 1), "minutes": round(max(7, distance * 2.1), 1), "geometry": [[place["lat"], place["lon"]], [lat, lon]], "source": "screening geometry; online routing unavailable"}
            routed = route_results.get(index, fallback)
            back = return_results.get(index)
            routed = {**routed, 'return_minutes': back['minutes'] if back else routed['minutes'],
                      'return_source': back['source'] if back else 'Assumed same as outbound; return route unavailable',
                      'return_data_access': back.get('_data_access') if back else None}
            vulnerability = .68 if "airport" in mode else (.56 if "ride" in mode else .38)
            gap = 210 if "rail" in mode else (620 if "ride" in mode else 430)
            zone_id = f"zone_{index + 1}"
            zones.append({"zone_id": zone_id, "name": name, "kind": "park_ride" if "park-and-ride" in mode else "demand", "lat": lat, "lon": lon, "visitors": visitors, "vulnerability": vulnerability, "first_mile_gap": gap, "timeline": [{"minute": minute, "people": round(visitors * _pulse(minute))} for minute in TIME_POINTS]})
            route_base[zone_id] = {"mode": mode, **routed}
        return zones, route_base

    def plan_from_brief(self, prompt: str, online: bool = True, inputs: dict | None = None) -> dict[str, Any]:
        if not isinstance(prompt, str) or not 8 <= len(prompt.strip()) <= 3000:
            raise ValueError('Event brief must contain 8–3000 characters.')
        inputs = inputs or {}
        if not isinstance(inputs, dict):
            raise ValueError('inputs must be an object.')
        parser = 'Structured form / deterministic parser'
        if online and api_status()['configured'] and not inputs.get('city_query'):
            parsed = extract_brief(prompt)
            parsed.update(prompt=prompt, short_name=parsed['title'])
            parser = 'OpenAI structured extraction; Python simulation'
        else:
            parsed = self.parse_brief(prompt)
        for key in ('city_query', 'venue_query', 'date', 'attendance', 'budget_usd'):
            if inputs.get(key) not in (None, ''):
                parsed[key] = inputs[key]
        for key in ('city_query', 'venue_query'):
            if not isinstance(parsed.get(key), str) or len(parsed[key]) > 200:
                raise ValueError(f'{key} must be text of at most 200 characters.')
        if parsed.get('attendance') is not None:
            value = parsed['attendance']
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value) or not 500 <= value <= 500000:
                raise ValueError('Attendance must be an integer between 500 and 500,000.')
            parsed['attendance'] = int(value)
        budget = parsed.get('budget_usd')
        if budget is not None and (isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or not 0 <= budget <= 100000000):
            raise ValueError('Budget must be between 0 and 100,000,000 USD.')
        parsed['date'] = parsed.get('date') or 'date not specified'
        if parsed['date'] != 'date not specified':
            date.fromisoformat(parsed['date'])
        parsed['start_time'] = parsed.get('start_time') or '19:30'
        place, assumptions = self._resolve_place(parsed, online)
        attendance, attendance_assumption = self._attendance(parsed, place)
        assumptions.append(attendance_assumption)
        assumptions.extend([
            {"field": "Start time", "value": parsed["start_time"], "confidence": "medium", "basis": "Inferred from event type unless a time appears in the prompt."},
            {"field": "Demand origins", "value": "Assumed catchment allocation", "confidence": "medium", "basis": "Major stations, visitor districts, airport and intercept access; validate with ticketing/postcode data."},
        ])
        base = {}
        weather = {"temperature_c": 22, "temperature_f": 72, "rain_probability_pct": 25, "wind_kmh": 14, "basis": "seasonal planning fallback"}
        transport = {"stations": [], "source": "unavailable; using assumed catchments", "retrieved": None}
        traffic = {'features': [], 'source': 'Official survey locations unavailable.'}
        jobs = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            if parsed["date"] != "date not specified": jobs[pool.submit(self._weather, place, parsed["date"], online=online)] = "weather"
            jobs[pool.submit(self._transport, place, online=online)] = "transport"
            jobs[pool.submit(self._traffic_context, place, online)] = "traffic"
            for future in as_completed(jobs):
                try:
                    value = future.result()
                    if jobs[future] == "weather": weather = value
                    elif jobs[future] == "traffic": traffic = value
                    else: transport = value
                except Exception:
                    pass
        facilities = transport.get('stations', [])
        selected_sites = select_sites(facilities, place)
        if facilities and not place.get('origins'):
            if selected_sites:
                place['origins'] = site_origins(selected_sites)
                assumptions = [a for a in assumptions if a['field'] != 'Demand origins']
                assumptions.append({'field': 'Transfer-site demand', 'value': f'{len(selected_sites)} nearby candidate sites; equal assumed demand shares', 'confidence': 'low', 'basis': 'Public facilities within 0.5–6.5 km; interchange types prioritized and nearby duplicates merged. These are transfer destinations, not measured attendee origins. Loading permissions and usable capacity remain unverified.'})
        zones, route_base = self._zones_and_routes(place, attendance, [], online)
        event = {"event_id": f"brief_{_slug(parsed['title'])}_{_slug(place['city'])}", "city_id": _slug(place["city"]), "name": f"{parsed['title']} — {place['city']}", "short_name": parsed["title"], "event_type": parsed["event_type"], "date": parsed["date"], "start_time": parsed["start_time"], "attendance": attendance, "status": "generated from natural-language brief", "weather": weather}
        base["event"] = event
        base["venue"] = {"name": place["venue"], "lat": place["lat"], "lon": place["lon"], "capacity": place["capacity"], "city": place["city"], "country": place["country"]}
        base["zones"] = zones
        base["transit"] = transport
        base['traffic_context'] = traffic
        base['candidate_sites'] = selected_sites
        evidence = {'venue': place, 'transport': transport, 'weather': weather, 'traffic survey sites': traffic, **route_base}
        base['data_access'] = {name: value.get('_data_access') or {'tier': 'assumption / unavailable'} for name, value in evidence.items()}
        base['data_access'].update({name+' return': route.get('return_data_access') or {'tier': 'assumption / unavailable'} for name, route in route_base.items()})
        base["currency"] = {"code": "USD", "symbol": "$"}
        base["brief"] = {"original_prompt": parsed["prompt"], "parser": parser, "assumptions": assumptions, "online_enrichment": online, "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}
        base["data_freshness"] = {"basemap": "live OpenStreetMap tiles", "venue": "Nominatim / curated fallback", "road_geometry": f"{sum(1 for r in route_base.values() if 'screening' not in r['source'])}/{len(route_base)} routes from OSRM/cache; others estimated", "transit": f"{transport.get('source')} · {len(transport.get('stations', []))} facilities", "weather": weather["basis"], "costs": "User-editable USD charter assumptions; no local quote"}
        base["model_limits"] = ["Venue and attendance may be inferred; review the assumptions before operational use.", "Traffic values are scenario projections, not live sensor readings.", "Public transport discovery is not a substitute for an agency timetable or GTFS/GTFS-RT feed.", "Costs are transferable planning ranges, not local vendor quotes or procurement bids."]
        tiers = ('repository', 'local cache', 'external API', 'assumption / unavailable')
        base['data_freshness']['data_lookup'] = 'Repository → local cache → external API. ' + '; '.join(f"{tier}: {sum(info['tier'] == tier for info in base['data_access'].values())}" for tier in tiers)
        base['data_freshness']['traffic_survey_sites'] = f"{len(traffic.get('features', []))} official locations; geographic evidence only, no measured flow or capacity."
        base["schema_version"] = "4.0"
        base['simulation'] = simulate_event(zones, route_base, place, inputs, budget)
        base['model_limits'].extend(base['simulation']['limitations'])
        return base


__all__ = ["UniversalPlanner"]
