from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .sample_data import load_demo_zones

ALIASES = {
    "zone_id": ("zone_id", "origin_zone", "zone", "id"),
    "zone_name": ("zone_name", "name", "origin_name"),
    "population": ("population", "pop", "total_population"),
    "zero_vehicle_share": ("zero_vehicle_share", "no_vehicle_share", "households_no_vehicle", "zero_car_share"),
    "low_income_share": ("low_income_share", "poverty_share", "below_poverty_share", "low_income_pct"),
    "disability_share": ("disability_share", "disabled_share", "population_with_disability", "disability_pct"),
    "svi_percentile": ("svi_percentile", "svi", "rpl_themes", "social_vulnerability"),
    "ada_path_score": ("ada_path_score", "accessible_path_score", "sidewalk_accessibility", "ada_access"),
    "source_name": ("source_name", "source", "dataset"),
    "source_url": ("source_url", "url", "citation_url"),
    "evidence_year": ("evidence_year", "year", "vintage"),
}


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _share(value: Any, default: float = 0.0) -> float:
    number = _safe_float(value, default)
    if number is None:
        return default
    if number > 1.0 and number <= 100.0:
        number /= 100.0
    return max(0.0, min(1.0, number))


def _field_map(columns: Iterable[str]) -> dict[str, str | None]:
    lookup = {str(column).strip().casefold(): str(column) for column in columns}
    return {
        canonical: next((lookup[a.casefold()] for a in aliases if a.casefold() in lookup), None)
        for canonical, aliases in ALIASES.items()
    }


def _load_rows(source: str | Path) -> tuple[list[dict[str, Any]], list[str], str]:
    path = Path(source).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Equity file not found: {path}")
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
            columns = list(reader.fieldnames or [])
        return rows, columns, str(path)
    if suffix in {".json", ".geojson"}:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("features"), list):
            rows = [dict(feature.get("properties") or {}) for feature in payload["features"]]
        elif isinstance(payload, list):
            rows = [dict(row) for row in payload if isinstance(row, dict)]
        elif isinstance(payload, dict) and isinstance(payload.get("zones"), list):
            rows = [dict(row) for row in payload["zones"] if isinstance(row, dict)]
        else:
            raise ValueError("Equity JSON must be a list, FeatureCollection, or object with a zones list.")
        columns = sorted({key for row in rows for key in row})
        return rows, columns, str(path)
    raise ValueError("Equity source must be CSV, JSON or GeoJSON.")


def scan_equity(source: str | Path) -> dict[str, Any]:
    rows, columns, resolved = _load_rows(source)
    fields = _field_map(columns)
    required = ["zone_id"]
    missing = [field for field in required if not fields.get(field)]
    metric_fields = [field for field in ("zero_vehicle_share", "low_income_share", "disability_share", "svi_percentile", "ada_path_score") if fields.get(field)]
    return {
        "source": resolved,
        "row_count": len(rows),
        "columns": columns,
        "field_map": fields,
        "metric_fields": metric_fields,
        "missing_required": missing,
        "ready": not missing and bool(metric_fields),
        "supported_zone_ids": [zone.zone_id for zone in load_demo_zones()],
    }


def build_equity_profile(source: str | Path, output_path: str | Path) -> dict[str, Any]:
    rows, columns, resolved = _load_rows(source)
    fields = _field_map(columns)
    if not fields.get("zone_id"):
        raise ValueError("Missing required equity field: zone_id")
    metric_fields = [field for field in ("zero_vehicle_share", "low_income_share", "disability_share", "svi_percentile", "ada_path_score") if fields.get(field)]
    if not metric_fields:
        raise ValueError("No supported equity or accessibility metric fields were found.")

    known = {zone.zone_id: zone.name for zone in load_demo_zones()}
    zones: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for raw in rows:
        zone_id = str(raw.get(fields["zone_id"] or "") or "").strip().casefold()
        if not zone_id or zone_id not in known or zone_id in seen:
            continue
        seen.add(zone_id)
        population = max(0.0, _safe_float(raw.get(fields.get("population") or ""), 0.0) or 0.0)
        zero_vehicle = _share(raw.get(fields.get("zero_vehicle_share") or ""), 0.0)
        low_income = _share(raw.get(fields.get("low_income_share") or ""), 0.0)
        disability = _share(raw.get(fields.get("disability_share") or ""), 0.0)
        svi = _share(raw.get(fields.get("svi_percentile") or ""), 0.0)
        ada_path = _share(raw.get(fields.get("ada_path_score") or ""), 0.5)
        evidence_count = sum(fields.get(field) is not None and str(raw.get(fields.get(field) or "") or "").strip() != "" for field in ("zero_vehicle_share", "low_income_share", "disability_share", "svi_percentile", "ada_path_score"))
        vulnerability = 0.30 * zero_vehicle + 0.25 * low_income + 0.25 * disability + 0.20 * svi
        zones.append({
            "zone_id": zone_id,
            "zone_name": str(raw.get(fields.get("zone_name") or "") or known[zone_id]).strip(),
            "population": round(population),
            "zero_vehicle_share": round(zero_vehicle, 4),
            "low_income_share": round(low_income, 4),
            "disability_share": round(disability, 4),
            "svi_percentile": round(svi, 4),
            "ada_path_score": round(ada_path, 4),
            "vulnerability_index": round(vulnerability, 4),
            "evidence_fields": evidence_count,
            "source_name": str(raw.get(fields.get("source_name") or "") or "User-provided equity profile").strip(),
            "source_url": str(raw.get(fields.get("source_url") or "") or "").strip(),
            "evidence_year": str(raw.get(fields.get("evidence_year") or "") or "").strip(),
        })

    if not zones:
        raise ValueError("No rows matched the supported EventFlow origin zones.")
    missing_zones = sorted(set(known) - {row["zone_id"] for row in zones})
    if missing_zones:
        warnings.append(f"No equity evidence was supplied for zones: {', '.join(missing_zones)}")

    profile = {
        "mode": "equity_accessibility",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": resolved,
        "zone_count": len(zones),
        "zones": zones,
        "warnings": warnings,
        "method": {
            "vulnerability_formula": "30% zero-vehicle share + 25% low-income share + 25% disability share + 20% SVI percentile",
            "ada_path_score": "Planning proxy for accessible origin-to-transit and last-mile paths; field validation remains required.",
        },
        "disclaimer": (
            "Equity indicators are planning-screening inputs. They identify who may face disproportionate mobility burdens; "
            "they do not establish legal ADA compliance or individual-level vulnerability."
        ),
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def load_equity_profile(path: str | Path) -> dict[str, Any] | None:
    profile_path = Path(path)
    if not profile_path.exists():
        return None
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("zones"), list):
        return None
    return payload
