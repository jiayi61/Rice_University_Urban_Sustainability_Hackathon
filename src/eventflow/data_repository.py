"""Versioned public-data snapshots first, private runtime cache second.

Only provider responses belong here: never event briefs, credentials or reports.
Freshness uses retrieval timestamps, not file mtime (which changes on git clone).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def normalized_key(key: str) -> str:
    return ' '.join(key.casefold().split())


class DataRepository:
    def __init__(self, root: Path):
        self.published = root / 'data/database/resources'
        self.runtime = root / 'data/cache/resources'

    @staticmethod
    def filename(key: str) -> str:
        return hashlib.sha256(normalized_key(key).encode()).hexdigest() + '.json'

    def read(self, key: str, max_age_days: int) -> dict | None:
        for directory, tier in ((self.published, 'repository'), (self.runtime, 'local cache')):
            try:
                record = json.loads((directory / self.filename(key)).read_text())
                if record['key'] != normalized_key(key) or record['schema_version'] != 1:
                    continue
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(record['retrieved_at'])).total_seconds()
                if not 0 <= age <= min(max_age_days, record['max_age_days']) * 86400:
                    continue
                payload = record['payload']
                if not isinstance(payload, dict) or not payload or 'error' in payload:
                    continue
                checksum = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                if checksum != record['sha256']:
                    continue
                return {**payload, '_data_access': {
                    'tier': tier, 'source_url': record['source_url'],
                    'retrieved_at': record['retrieved_at'], 'key': record['key'],
                    'max_age_days': record['max_age_days'],
                }}
            except (OSError, ValueError, KeyError, TypeError, OverflowError):
                continue
        return None

    def write(self, key: str, payload: dict, source_url: str, max_age_days: int,
              *, publish: bool = False, retrieved_at: str | None = None) -> dict:
        clean = {k: v for k, v in payload.items() if k != '_data_access'}
        record = {
            'schema_version': 1, 'key': normalized_key(key),
            'retrieved_at': retrieved_at or datetime.now(timezone.utc).isoformat(),
            'source_url': source_url, 'max_age_days': max_age_days,
            'sha256': hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            'payload': clean,
        }
        directory = self.published if publish else self.runtime
        directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=directory, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(record, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
            os.replace(name, directory / self.filename(key))
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return record


TRAFFIC_LAYER = 'https://geogimsms.houstontx.gov/arcgis/rest/services/TDO/Traffic_Management_gx/MapServer/14'
TRAFFIC_KEY = 'traffic_sites_houston_nrg'
TRAFFIC_BBOX = [-95.45, 29.65, -95.37, 29.72]


def fetch_houston_sites(get_json) -> dict:
    """Read survey locations, deliberately not a volume/capacity observation."""
    from urllib.parse import urlencode
    west, south, east, north = TRAFFIC_BBOX
    params = {
        'f': 'geojson', 'where': '1=1', 'outSR': 4326, 'inSR': 4326,
        'geometry': json.dumps(dict(xmin=west, ymin=south, xmax=east, ymax=north,
                                    spatialReference={'wkid': 4326})),
        'geometryType': 'esriGeometryEnvelope', 'spatialRel': 'esriSpatialRelIntersects',
        'outFields': 'OBJECTID,ADDRESS,SEGMENT,StationID,COLLECTIONTYPE',
        'orderByFields': 'OBJECTID', 'resultRecordCount': 1000,
    }
    features = []
    for offset in range(0, 10000, 1000):
        data = get_json(TRAFFIC_LAYER + '/query?' + urlencode({**params, 'resultOffset': offset}), 25)
        if data.get('type') != 'FeatureCollection':
            raise ValueError('Official traffic endpoint returned no feature collection.')
        for feature in data['features']:
            lon, lat = feature['geometry']['coordinates'][:2]
            if west <= lon <= east and south <= lat <= north:
                features.append(feature)
        if not data.get('exceededTransferLimit'):
            break
    else:
        raise ValueError('Traffic query exceeded the bounded download limit.')
    if not features:
        raise ValueError('Official traffic query returned no matching locations.')
    return {'type': 'FeatureCollection', 'features': features, 'bbox': TRAFFIC_BBOX,
            'source': 'City of Houston · Major Thoroughfare ADT survey locations',
            'source_url': TRAFFIC_LAYER, 'has_traffic_volumes': False,
            'use': 'Geographic evidence only; no measured traffic volumes or road capacity in this layer.'}
