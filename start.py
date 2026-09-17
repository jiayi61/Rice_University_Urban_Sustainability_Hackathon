#!/usr/bin/env python3
"""Zero-dependency launcher for EventFlow universal mobility planner v3."""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
import webbrowser
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATIC_FILE = ROOT / "app" / "static" / "index.html"
LEGACY_FILE = ROOT / "app" / "static" / "legacy.html"
STYLES_FILE = ROOT / "app" / "static" / "styles.css"
SCRIPT_FILE = ROOT / "app" / "static" / "app.js"
RICE_PROFILE_PATH = ROOT / "data" / "local" / "houston_profile.json"
GTFS_PROFILE_PATH = ROOT / "data" / "local" / "gtfs_profile.json"
OSM_PROFILE_PATH = ROOT / "data" / "local" / "osm_profile.json"
TRAFFIC_PROFILE_PATH = ROOT / "data" / "local" / "traffic_profile.json"
CANDIDATE_PROFILE_PATH = ROOT / "data" / "local" / "candidate_profile.json"
EQUITY_PROFILE_PATH = ROOT / "data" / "local" / "equity_profile.json"
OSM_DOWNLOAD_PATH = ROOT / "data" / "local" / "houston_overpass.json"
DYNAMIC_DATASET_DB_PATH = ROOT / "data" / "local" / "dynamic_city_datasets.json"
sys.path.insert(0, str(ROOT / "src"))

from eventflow.advisor import generate_action_plan  # noqa: E402
from eventflow.candidate_ingestion import build_candidate_profile, scan_candidates  # noqa: E402
from eventflow.gtfs_ingestion import build_gtfs_profile, scan_gtfs  # noqa: E402
from eventflow.equity_ingestion import build_equity_profile, scan_equity  # noqa: E402
from eventflow.local_data import build_houston_profile, scan_root  # noqa: E402
from eventflow.osm_ingestion import build_osm_profile, fetch_overpass, scan_osm  # noqa: E402
from eventflow.traffic_ingestion import build_traffic_profile, scan_traffic_counts  # noqa: E402
from eventflow.model import EventFlowModel  # noqa: E402
from eventflow.platform import MobilityPlatform  # noqa: E402
from eventflow.nynj import NYNJEngine, narrative  # noqa: E402
from eventflow.universal import UniversalPlanner  # noqa: E402
from eventflow.api_config import api_status
from eventflow.sample_data import demo_city_readiness  # noqa: E402
from eventflow.submission import build_submission_package  # noqa: E402
from houston_mvp.cli import build_dashboard_payload as build_houston_mvp_payload  # noqa: E402

MODEL = EventFlowModel(RICE_PROFILE_PATH, GTFS_PROFILE_PATH, OSM_PROFILE_PATH, TRAFFIC_PROFILE_PATH, CANDIDATE_PROFILE_PATH, EQUITY_PROFILE_PATH)
PLATFORM = MobilityPlatform(ROOT)
NYNJ = NYNJEngine(ROOT)
UNIVERSAL = UniversalPlanner(ROOT, PLATFORM)


def find_available_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free port found in {preferred}-{preferred + 49}.")


def validate_ids(values: list[str], field: str) -> None:
    known = set(MODEL.intervention_map)
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"Unknown {field}: {sorted(unknown)}")


def _validated_path(value: Any, label: str) -> str:
    path = str(value or "").strip()
    if not path:
        raise ValueError(f"{label} is required.")
    if len(path) > 1000:
        raise ValueError(f"{label} is too long.")
    return path


def _dynamic_dataset_summary(record: dict[str, Any]) -> dict[str, Any]:
    nodes = record.get("nodes", [])
    edges = record.get("edges", [])
    return {
        "dataset_id": record.get("dataset_id"),
        "name": record.get("name"),
        "city": record.get("city"),
        "saved_at": record.get("saved_at"),
        "node_count": len(nodes) if isinstance(nodes, list) else 0,
        "edge_count": len(edges) if isinstance(edges, list) else 0,
    }


def _load_dynamic_datasets() -> list[dict[str, Any]]:
    if not DYNAMIC_DATASET_DB_PATH.exists():
        return []
    payload = json.loads(DYNAMIC_DATASET_DB_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    records = payload.get("datasets", [])
    return records if isinstance(records, list) else []


def _write_dynamic_datasets(records: list[dict[str, Any]]) -> None:
    DYNAMIC_DATASET_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"datasets": records[-30:]}
    DYNAMIC_DATASET_DB_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _save_dynamic_dataset(data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "Untitled city traffic dataset").strip()[:90]
    city = str(data.get("city") or "custom").strip()[:40]
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    center = data.get("center", {})
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Dynamic map dataset must include nodes and edges arrays.")
    if len(nodes) + len(edges) > 700:
        raise ValueError("Dynamic map dataset is too large for this local MVP. Use 700 nodes plus edges or fewer.")
    record = {
        "dataset_id": f"dyn_{int(time.time() * 1000)}",
        "name": name,
        "city": city,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "center": center if isinstance(center, dict) else {},
        "nodes": nodes,
        "edges": edges,
    }
    records = [item for item in _load_dynamic_datasets() if item.get("dataset_id") != record["dataset_id"]]
    records.append(record)
    _write_dynamic_datasets(records)
    return record


class Handler(BaseHTTPRequestHandler):
    server_version = "EventFlowStandalone/2.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, source: Path = STATIC_FILE) -> None:
        if not source.exists():
            self.send_json({"detail": f"Missing frontend: {source}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        body = source.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_asset(self, source: Path, content_type: str) -> None:
        if not source.exists():
            self.send_json({"detail": "Asset not found"}, HTTPStatus.NOT_FOUND)
            return
        body = source.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("Request body is too large.")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON body.") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object.")
        return data

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in {"/", "/index.html"}:
                self.send_html()
            elif path == "/legacy.html":
                self.send_html(LEGACY_FILE)
            elif path == "/styles.css":
                self.send_asset(STYLES_FILE, "text/css; charset=utf-8")
            elif path == "/app.js":
                self.send_asset(SCRIPT_FILE, "application/javascript; charset=utf-8")
            elif path in {"/competition-data.json", "/competition-scenarios.json"}:
                self.send_asset(ROOT / "app" / "static" / path.lstrip("/"), "application/json; charset=utf-8")
            elif path == "/api/nynj/catalog":
                self.send_json(NYNJ.catalog())
            elif path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
            elif path == "/api/health":
                self.send_json({"status": "ok", "mode": MODEL.data_mode, "server": "standalone", "version": "3.0"})
            elif path == '/api/config':
                self.send_json(api_status())
            elif path == "/api/v2/catalog":
                self.send_json(PLATFORM.catalog())
            elif path == "/api/catalog":
                self.send_json({
                    "time_windows": MODEL.time_window_catalog(),
                    "stressors": MODEL.stressor_catalog(),
                    "presets": MODEL.preset_catalog(),
                })
            elif path == "/api/operations":
                self.send_json(MODEL.operations_catalog())
            elif path == "/api/validation":
                self.send_json(MODEL.validation_report())
            elif path == "/api/demand-calibration":
                self.send_json(MODEL.demand_calibration())
            elif path == "/api/audit":
                self.send_json(MODEL.baseline_audit())
            elif path == "/api/candidates/status":
                self.send_json(MODEL.candidate_recommendations())
            elif path == "/api/equity/status":
                self.send_json(MODEL.equity_report())
            elif path == "/api/readiness":
                self.send_json({
                    "disclaimer": "Methodology comparison; cross-city values remain illustrative in v0.9.",
                    "cities": demo_city_readiness(),
                })
            elif path == "/api/interventions":
                self.send_json({"interventions": MODEL.intervention_catalog()})
            elif path == "/api/baseline":
                self.send_json(MODEL.baseline())
            elif path == "/api/data/status":
                self.send_json(MODEL.data_status())
            elif path == "/api/houston-mvp":
                self.send_json(build_houston_mvp_payload())
            elif path == "/api/dynamic-map/datasets":
                records = _load_dynamic_datasets()
                self.send_json({"datasets": [_dynamic_dataset_summary(record) for record in records]})
            elif path.startswith("/api/dynamic-map/datasets/"):
                dataset_id = path.rsplit("/", 1)[-1]
                match = next((record for record in _load_dynamic_datasets() if record.get("dataset_id") == dataset_id), None)
                if not match:
                    self.send_json({"detail": "Dynamic map dataset not found"}, HTTPStatus.NOT_FOUND)
                else:
                    self.send_json(match)
            else:
                self.send_json({"detail": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json({"detail": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            data = self.read_json()
            if path == "/api/nynj/plan":
                result = NYNJ.plan(data.get("budget", 500000), data.get("priority", "balanced"), data.get("stress", "normal"))
                result["narrative"] = narrative(result)
                self.send_json(result)
                return
            if path == "/api/v2/plan":
                self.send_json(PLATFORM.plan(str(data.get("event_id") or "houston_wc26")))
                return
            if path == "/api/v3/brief":
                if not isinstance(data.get('online', True), bool):
                    raise ValueError('online must be boolean.')
                self.send_json(UNIVERSAL.plan_from_brief(data.get("prompt") or "", data.get("online", True), data.get('inputs')))
                return
            if path == "/api/dynamic-map/datasets":
                record = _save_dynamic_dataset(data)
                self.send_json({"dataset": _dynamic_dataset_summary(record)})
                return

            interventions = list(data.get("interventions", []))
            time_window = str(data.get("time_window", "ingress_peak"))
            operations = data.get("operations", {})
            if not isinstance(operations, dict):
                raise ValueError("operations must be an object.")

            if path == "/api/simulate":
                validate_ids(interventions, "interventions")
                self.send_json(MODEL.simulate(interventions, time_window, operations))
                return

            if path == "/api/time-windows":
                validate_ids(interventions, "interventions")
                self.send_json(MODEL.compare_time_windows(interventions, operations))
                return

            if path == "/api/stress":
                validate_ids(interventions, "interventions")
                stressor_id = str(data.get("stressor_id", "attendance_surge"))
                self.send_json(MODEL.stress_test(interventions, stressor_id, time_window, operations))
                return

            if path == "/api/sensitivity":
                validate_ids(interventions, "interventions")
                self.send_json(MODEL.sensitivity_analysis(interventions, time_window, operations))
                return

            if path == "/api/explain":
                validate_ids(interventions, "interventions")
                self.send_json(MODEL.portfolio_explainability(
                    interventions,
                    time_window,
                    operations,
                    str(data.get("objective_mode", "balanced")),
                ))
                return

            if path == "/api/implementation":
                validate_ids(interventions, "interventions")
                self.send_json(MODEL.implementation_playbook(interventions))
                return

            if path == "/api/submission":
                budget = float(data.get("budget_usd", 500_000))
                if budget < 0:
                    raise ValueError("budget_usd must be non-negative.")
                required = list(data.get("required", []))
                excluded = list(data.get("excluded", []))
                validate_ids(required, "required interventions")
                validate_ids(excluded, "excluded interventions")
                self.send_json(build_submission_package(
                    MODEL,
                    budget_usd=budget,
                    required=required,
                    excluded=excluded,
                    time_window=time_window,
                    operations=operations,
                    objective_mode=str(data.get("objective_mode", "balanced")),
                    minimum_equity_coverage_pct=float(data.get("minimum_equity_coverage_pct", 0.0)),
                    minimum_accessibility_coverage_pct=float(data.get("minimum_accessibility_coverage_pct", 0.0)),
                ))
                return

            if path in {"/api/optimize", "/api/advisor"}:
                budget = float(data.get("budget_usd", 500_000))
                if budget < 0:
                    raise ValueError("budget_usd must be non-negative.")
                required = list(data.get("required", []))
                excluded = list(data.get("excluded", []))
                validate_ids(required, "required interventions")
                validate_ids(excluded, "excluded interventions")
                if set(required) & set(excluded):
                    raise ValueError("An intervention cannot be both required and excluded.")
                result = MODEL.optimize(
                    budget,
                    required,
                    excluded,
                    time_window=time_window,
                    operations=operations,
                    objective_mode=str(data.get("objective_mode", "balanced")),
                    minimum_equity_coverage_pct=float(data.get("minimum_equity_coverage_pct", 0.0)),
                    minimum_accessibility_coverage_pct=float(data.get("minimum_accessibility_coverage_pct", 0.0)),
                )
                if path == "/api/optimize":
                    self.send_json(result)
                else:
                    self.send_json({
                        "optimization": result,
                        "action_plan": generate_action_plan(result, budget),
                    })
                return

            if path == "/api/data/scan":
                root = _validated_path(data.get("root"), "Dataset root path")
                self.send_json(scan_root(root))
                return

            if path == "/api/data/build":
                root = _validated_path(data.get("root"), "Dataset root path")
                max_files = int(data.get("max_files", 1))
                max_rows = int(data.get("max_rows_per_file", 75_000))
                attendance = int(data.get("event_attendance", 72_000))
                if attendance < 10_000 or attendance > 150_000:
                    raise ValueError("event_attendance must be between 10,000 and 150,000.")
                profile = build_houston_profile(
                    root,
                    RICE_PROFILE_PATH,
                    max_files=max_files,
                    max_rows_per_file=max_rows,
                    event_attendance=attendance,
                )
                MODEL.reload_data()
                self.send_json({
                    "status": MODEL.data_status(),
                    "profile": profile,
                    "baseline": MODEL.baseline(),
                })
                return

            if path == "/api/data/reset":
                if RICE_PROFILE_PATH.exists():
                    RICE_PROFILE_PATH.unlink()
                MODEL.reload_data()
                self.send_json({"status": MODEL.data_status(), "baseline": MODEL.baseline()})
                return

            if path == "/api/gtfs/scan":
                source = _validated_path(data.get("source"), "GTFS source")
                self.send_json(scan_gtfs(source))
                return

            if path == "/api/gtfs/build":
                source = _validated_path(data.get("source"), "GTFS source")
                event_date = str(data.get("event_date", "2026-06-14"))
                kickoff_time = str(data.get("kickoff_time", "15:00"))
                profile = build_gtfs_profile(
                    source,
                    GTFS_PROFILE_PATH,
                    event_date=event_date,
                    kickoff_time=kickoff_time,
                )
                MODEL.reload_data()
                self.send_json({
                    "status": MODEL.data_status(),
                    "profile": profile,
                    "baseline": MODEL.baseline(),
                })
                return

            if path == "/api/gtfs/reset":
                if GTFS_PROFILE_PATH.exists():
                    GTFS_PROFILE_PATH.unlink()
                MODEL.reload_data()
                self.send_json({"status": MODEL.data_status(), "baseline": MODEL.baseline()})
                return

            if path == "/api/osm/scan":
                source = _validated_path(data.get("source"), "OpenStreetMap source")
                self.send_json(scan_osm(source))
                return

            if path == "/api/osm/download":
                bbox = {
                    "south": float(data.get("south", 29.62)),
                    "west": float(data.get("west", -95.53)),
                    "north": float(data.get("north", 30.03)),
                    "east": float(data.get("east", -95.25)),
                }
                if not (bbox["south"] < bbox["north"] and bbox["west"] < bbox["east"]):
                    raise ValueError("Invalid bounding box.")
                fetch_overpass(OSM_DOWNLOAD_PATH, bbox=bbox)
                self.send_json(scan_osm(OSM_DOWNLOAD_PATH))
                return

            if path == "/api/osm/build":
                source = _validated_path(data.get("source"), "OpenStreetMap source")
                profile = build_osm_profile(source, OSM_PROFILE_PATH)
                if TRAFFIC_PROFILE_PATH.exists():
                    TRAFFIC_PROFILE_PATH.unlink()
                if CANDIDATE_PROFILE_PATH.exists():
                    CANDIDATE_PROFILE_PATH.unlink()
                MODEL.reload_data()
                self.send_json({"status": MODEL.data_status(), "profile": profile, "baseline": MODEL.baseline()})
                return

            if path == "/api/osm/reset":
                for profile_path in (OSM_PROFILE_PATH, TRAFFIC_PROFILE_PATH, CANDIDATE_PROFILE_PATH):
                    if profile_path.exists():
                        profile_path.unlink()
                MODEL.reload_data()
                self.send_json({"status": MODEL.data_status(), "baseline": MODEL.baseline()})
                return

            if path == "/api/traffic/scan":
                source = _validated_path(data.get("source"), "Traffic-count source")
                self.send_json(scan_traffic_counts(source))
                return

            if path == "/api/traffic/build":
                source = _validated_path(data.get("source"), "Traffic-count source")
                profile = build_traffic_profile(
                    source,
                    OSM_PROFILE_PATH,
                    TRAFFIC_PROFILE_PATH,
                    peak_hour_factor=float(data.get("peak_hour_factor", 0.09)),
                    directional_factor=float(data.get("directional_factor", 0.55)),
                    max_snap_miles=float(data.get("max_snap_miles", 1.25)),
                )
                MODEL.reload_data()
                self.send_json({"status": MODEL.data_status(), "profile": profile, "baseline": MODEL.baseline()})
                return

            if path == "/api/traffic/reset":
                if TRAFFIC_PROFILE_PATH.exists():
                    TRAFFIC_PROFILE_PATH.unlink()
                if CANDIDATE_PROFILE_PATH.exists():
                    CANDIDATE_PROFILE_PATH.unlink()
                MODEL.reload_data()
                self.send_json({"status": MODEL.data_status(), "baseline": MODEL.baseline()})
                return

            if path == "/api/candidates/scan":
                source = _validated_path(data.get("source"), "Candidate-site source")
                self.send_json(scan_candidates(source))
                return

            if path == "/api/candidates/build":
                source = _validated_path(data.get("source"), "Candidate-site source")
                profile = build_candidate_profile(source, CANDIDATE_PROFILE_PATH, osm_profile_path=OSM_PROFILE_PATH)
                MODEL.reload_data()
                self.send_json({
                    "status": MODEL.data_status(),
                    "profile": profile,
                    "recommendations": MODEL.candidate_recommendations(),
                    "baseline": MODEL.baseline(),
                })
                return

            if path == "/api/candidates/reset":
                if CANDIDATE_PROFILE_PATH.exists():
                    CANDIDATE_PROFILE_PATH.unlink()
                MODEL.reload_data()
                self.send_json({
                    "status": MODEL.data_status(),
                    "recommendations": MODEL.candidate_recommendations(),
                    "baseline": MODEL.baseline(),
                })
                return

            if path == "/api/equity/scan":
                source = _validated_path(data.get("source"), "Equity source")
                self.send_json(scan_equity(source))
                return

            if path == "/api/equity/build":
                source = _validated_path(data.get("source"), "Equity source")
                profile = build_equity_profile(source, EQUITY_PROFILE_PATH)
                MODEL.reload_data()
                self.send_json({
                    "status": MODEL.data_status(),
                    "profile": profile,
                    "equity": MODEL.equity_report(),
                    "baseline": MODEL.baseline(),
                })
                return

            if path == "/api/equity/reset":
                if EQUITY_PROFILE_PATH.exists():
                    EQUITY_PROFILE_PATH.unlink()
                MODEL.reload_data()
                self.send_json({
                    "status": MODEL.data_status(),
                    "equity": MODEL.equity_report(),
                    "baseline": MODEL.baseline(),
                })
                return

            self.send_json({"detail": "Not found"}, HTTPStatus.NOT_FOUND)
        except (ValueError, FileNotFoundError, zipfile.BadZipFile) as exc:  # type: ignore[name-defined]
            self.send_json({"detail": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"detail": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def open_later(url: str) -> None:
    time.sleep(0.8)
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run EventFlow AI locally without installing packages.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    port = find_available_port(args.host, args.port)
    server = ThreadingHTTPServer((args.host, port), Handler)
    url = f"http://{args.host}:{port}"

    print("\nEventFlow Mobility Readiness Platform v2.0")
    print("=" * 43)
    print(f"Open: {url}")
    print(f"Data mode: {MODEL.data_mode}")
    if port != args.port:
        print(f"Port {args.port} was occupied; using {port} instead.")
    print("Press Ctrl+C to stop.\n")

    if not args.no_browser:
        threading.Thread(target=open_later, args=(url,), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping EventFlow AI...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
