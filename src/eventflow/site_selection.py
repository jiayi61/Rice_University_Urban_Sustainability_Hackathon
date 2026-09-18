"""Deterministic screening of nearby public facilities, not inferred audience OD."""
import math


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


def select_sites(stations, place, limit=8):
    venue = (place['lat'], place['lon'])
    candidates = []
    for item in stations:
        try:
            lat, lon = float(item['lat']), float(item['lon'])
            if not math.isfinite(lat+lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            distance = distance_km((lat, lon), venue)
            if not .5 < distance <= 6.5 or item.get('access') in ('private', 'no'):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        candidates.append({**item, 'lat': lat, 'lon': lon, 'distance_to_venue_km': round(distance, 2),
                           'selection_basis': 'Nearby public facility; loading permission and capacity unverified.'})
    # Prefer named interchange facilities; merge platforms/entrances within 250m.
    priority = {'rail': 0, 'bus': 1, 'parking': 2}
    candidates.sort(key=lambda s: (priority.get(s.get('mode'), 3), s['distance_to_venue_km'], s.get('name', ''), s['lat'], s['lon']))
    selected = []
    for item in candidates:
        if any(distance_km((item['lat'], item['lon']), (s['lat'], s['lon'])) < .25 for s in selected):
            continue
        selected.append(item)
        if len(selected) == limit:
            break
    return selected


def site_origins(sites):
    return [(s['name'], 'proposed shuttle', s['lat'], s['lon'], 1/len(sites)) for s in sites]
