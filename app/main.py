from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
RICE_PROFILE_PATH = ROOT / "data" / "local" / "houston_profile.json"
GTFS_PROFILE_PATH = ROOT / "data" / "local" / "gtfs_profile.json"
OSM_PROFILE_PATH = ROOT / "data" / "local" / "osm_profile.json"
TRAFFIC_PROFILE_PATH = ROOT / "data" / "local" / "traffic_profile.json"
CANDIDATE_PROFILE_PATH = ROOT / "data" / "local" / "candidate_profile.json"
EQUITY_PROFILE_PATH = ROOT / "data" / "local" / "equity_profile.json"
OSM_DOWNLOAD_PATH = ROOT / "data" / "local" / "houston_overpass.json"
DYNAMIC_DATASET_DB_PATH = ROOT / "data" / "local" / "dynamic_city_datasets.json"
sys.path.insert(0, str(ROOT / "src"))

from eventflow.advisor import generate_action_plan
from eventflow.candidate_ingestion import build_candidate_profile, scan_candidates
from eventflow.gtfs_ingestion import build_gtfs_profile, scan_gtfs
from eventflow.equity_ingestion import build_equity_profile, scan_equity
from eventflow.local_data import build_houston_profile, scan_root
from eventflow.osm_ingestion import DEFAULT_BBOX, build_osm_profile, fetch_overpass, scan_osm
from eventflow.traffic_ingestion import build_traffic_profile, scan_traffic_counts
from eventflow.model import EventFlowModel
from eventflow.platform import MobilityPlatform
from eventflow.universal import UniversalPlanner
from eventflow.sample_data import demo_city_readiness
from eventflow.submission import build_submission_package
from houston_mvp.cli import build_dashboard_payload as build_houston_mvp_payload

app = FastAPI(title="EventFlow Universal Mobility Planner", version="3.0.0")
model = EventFlowModel(RICE_PROFILE_PATH, GTFS_PROFILE_PATH, OSM_PROFILE_PATH, TRAFFIC_PROFILE_PATH, CANDIDATE_PROFILE_PATH, EQUITY_PROFILE_PATH)
platform = MobilityPlatform(ROOT)
universal_planner = UniversalPlanner(ROOT, platform)


class SimulationRequest(BaseModel):
    interventions: List[str] = Field(default_factory=list)
    time_window: str = "ingress_peak"
    operations: Dict[str, float] = Field(default_factory=dict)


class StressRequest(SimulationRequest):
    stressor_id: str = "attendance_surge"


class ExplainRequest(SimulationRequest):
    objective_mode: str = "balanced"


class OptimizationRequest(BaseModel):
    budget_usd: float = Field(default=500000, ge=0)
    required: List[str] = Field(default_factory=list)
    excluded: List[str] = Field(default_factory=list)
    time_window: str = "ingress_peak"
    operations: Dict[str, float] = Field(default_factory=dict)
    objective_mode: str = "balanced"
    minimum_equity_coverage_pct: float = Field(default=0, ge=0, le=100)
    minimum_accessibility_coverage_pct: float = Field(default=0, ge=0, le=100)


class DataRootRequest(BaseModel):
    root: str


class DataBuildRequest(DataRootRequest):
    max_files: int = Field(default=1, ge=1, le=32)
    max_rows_per_file: int = Field(default=75000, ge=1000, le=1000000)
    event_attendance: int = Field(default=72000, ge=10000, le=150000)


class GTFSRequest(BaseModel):
    source: str
    event_date: str = "2026-06-14"
    kickoff_time: str = "15:00"

class OSMRequest(BaseModel):
    source: str = "data/sample/mock_overpass_houston.json"


class OSMDownloadRequest(BaseModel):
    south: float = DEFAULT_BBOX["south"]
    west: float = DEFAULT_BBOX["west"]
    north: float = DEFAULT_BBOX["north"]
    east: float = DEFAULT_BBOX["east"]


class TrafficRequest(BaseModel):
    source: str = "data/sample/mock_houston_traffic_counts.csv"
    peak_hour_factor: float = Field(default=0.09, gt=0, le=1)
    directional_factor: float = Field(default=0.55, gt=0, le=1)
    max_snap_miles: float = Field(default=1.25, ge=0.05, le=10)


class CandidateRequest(BaseModel):
    source: str = "data/sample/mock_candidate_sites.csv"


class EquityRequest(BaseModel):
    source: str = "data/sample/mock_equity_profile.csv"


class DynamicDatasetRequest(BaseModel):
    name: str = "Untitled city traffic dataset"
    city: str = "custom"
    center: Dict[str, float] = Field(default_factory=dict)
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)


class PlannerRequest(BaseModel):
    event_id: str = "houston_wc26"


class EventBriefRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=1000)
    online: bool = True


def dynamic_dataset_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_id": record.get("dataset_id"),
        "name": record.get("name"),
        "city": record.get("city"),
        "saved_at": record.get("saved_at"),
        "node_count": len(record.get("nodes", [])),
        "edge_count": len(record.get("edges", [])),
    }


def load_dynamic_datasets() -> list[dict[str, Any]]:
    if not DYNAMIC_DATASET_DB_PATH.exists():
        return []
    payload = json.loads(DYNAMIC_DATASET_DB_PATH.read_text(encoding="utf-8"))
    records = payload.get("datasets", []) if isinstance(payload, dict) else []
    return records if isinstance(records, list) else []


def write_dynamic_datasets(records: list[dict[str, Any]]) -> None:
    DYNAMIC_DATASET_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DYNAMIC_DATASET_DB_PATH.write_text(json.dumps({"datasets": records[-30:]}, indent=2, ensure_ascii=False), encoding="utf-8")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/legacy.html")
def legacy() -> FileResponse:
    return FileResponse(ROOT / "app" / "static" / "legacy.html")


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(ROOT / "app" / "static" / "styles.css", media_type="text/css")


@app.get("/app.js")
def script() -> FileResponse:
    return FileResponse(ROOT / "app" / "static" / "app.js", media_type="application/javascript")


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mode": model.data_mode, "version": "3.0"}


@app.get("/api/v2/catalog")
def planner_catalog() -> dict:
    return platform.catalog()


@app.post("/api/v2/plan")
def planner_plan(request: PlannerRequest) -> dict:
    try:
        return platform.plan(request.event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v3/brief")
def plan_event_brief(request: EventBriefRequest) -> dict:
    try:
        return universal_planner.plan_from_brief(request.prompt, request.online)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/catalog")
def catalog() -> dict:
    return {
        "time_windows": model.time_window_catalog(),
        "stressors": model.stressor_catalog(),
        "presets": model.preset_catalog(),
    }

@app.get("/api/operations")
def operations() -> dict:
    return model.operations_catalog()


@app.get("/api/validation")
def validation() -> dict:
    return model.validation_report()


@app.get("/api/demand-calibration")
def demand_calibration() -> dict:
    return model.demand_calibration()


@app.get("/api/audit")
def audit() -> dict:
    return model.baseline_audit()


@app.get("/api/candidates/status")
def candidate_status() -> dict:
    return model.candidate_recommendations()


@app.get("/api/equity/status")
def equity_status() -> dict:
    return model.equity_report()


@app.get("/api/readiness")
def readiness() -> dict:
    return {
        "disclaimer": "Methodology comparison; cross-city values remain illustrative in v0.9.",
        "cities": demo_city_readiness(),
    }


@app.get("/api/interventions")
def interventions() -> dict:
    return {"interventions": model.intervention_catalog()}


@app.get("/api/baseline")
def baseline() -> dict:
    return model.baseline()


@app.get("/api/data/status")
def data_status() -> dict:
    return model.data_status()


@app.get("/api/houston-mvp")
def houston_mvp() -> dict:
    return build_houston_mvp_payload()


@app.get("/api/dynamic-map/datasets")
def dynamic_datasets() -> dict:
    return {"datasets": [dynamic_dataset_summary(record) for record in load_dynamic_datasets()]}


@app.get("/api/dynamic-map/datasets/{dataset_id}")
def dynamic_dataset(dataset_id: str) -> dict:
    match = next((record for record in load_dynamic_datasets() if record.get("dataset_id") == dataset_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Dynamic map dataset not found")
    return match


@app.post("/api/dynamic-map/datasets")
def save_dynamic_dataset(request: DynamicDatasetRequest) -> dict:
    if len(request.nodes) + len(request.edges) > 700:
        raise HTTPException(status_code=400, detail="Dynamic map dataset is too large for this local MVP.")
    record = {
        "dataset_id": f"dyn_{int(time.time() * 1000)}",
        "name": request.name.strip()[:90] or "Untitled city traffic dataset",
        "city": request.city.strip()[:40] or "custom",
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "center": request.center,
        "nodes": request.nodes,
        "edges": request.edges,
    }
    records = [item for item in load_dynamic_datasets() if item.get("dataset_id") != record["dataset_id"]]
    records.append(record)
    write_dynamic_datasets(records)
    return {"dataset": dynamic_dataset_summary(record)}


@app.post("/api/simulate")
def simulate(request: SimulationRequest) -> dict:
    try:
        return model.simulate(request.interventions, request.time_window, request.operations)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/time-windows")
def time_windows(request: SimulationRequest) -> dict:
    try:
        return model.compare_time_windows(request.interventions, request.operations)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/stress")
def stress(request: StressRequest) -> dict:
    try:
        return model.stress_test(request.interventions, request.stressor_id, request.time_window, request.operations)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sensitivity")
def sensitivity(request: SimulationRequest) -> dict:
    try:
        return model.sensitivity_analysis(request.interventions, request.time_window, request.operations)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/optimize")
def optimize(request: OptimizationRequest) -> dict:
    try:
        return model.optimize(
            request.budget_usd,
            request.required,
            request.excluded,
            time_window=request.time_window,
            operations=request.operations,
            objective_mode=request.objective_mode,
            minimum_equity_coverage_pct=request.minimum_equity_coverage_pct,
            minimum_accessibility_coverage_pct=request.minimum_accessibility_coverage_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/explain")
def explain(request: ExplainRequest) -> dict:
    try:
        return model.portfolio_explainability(
            request.interventions,
            request.time_window,
            request.operations,
            request.objective_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/implementation")
def implementation(request: SimulationRequest) -> dict:
    try:
        return model.implementation_playbook(request.interventions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/submission")
def submission(request: OptimizationRequest) -> dict:
    try:
        return build_submission_package(
            model,
            budget_usd=request.budget_usd,
            required=request.required,
            excluded=request.excluded,
            time_window=request.time_window,
            operations=request.operations,
            objective_mode=request.objective_mode,
            minimum_equity_coverage_pct=request.minimum_equity_coverage_pct,
            minimum_accessibility_coverage_pct=request.minimum_accessibility_coverage_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/advisor")
def advisor(request: OptimizationRequest) -> dict:
    try:
        result = model.optimize(
            request.budget_usd,
            request.required,
            request.excluded,
            time_window=request.time_window,
            operations=request.operations,
            objective_mode=request.objective_mode,
            minimum_equity_coverage_pct=request.minimum_equity_coverage_pct,
            minimum_accessibility_coverage_pct=request.minimum_accessibility_coverage_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "optimization": result,
        "action_plan": generate_action_plan(result, request.budget_usd),
    }


@app.post("/api/data/scan")
def data_scan(request: DataRootRequest) -> dict:
    try:
        return scan_root(request.root)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/data/build")
def data_build(request: DataBuildRequest) -> dict:
    try:
        profile = build_houston_profile(
            request.root,
            RICE_PROFILE_PATH,
            max_files=request.max_files,
            max_rows_per_file=request.max_rows_per_file,
            event_attendance=request.event_attendance,
        )
        model.reload_data()
        return {"status": model.data_status(), "profile": profile, "baseline": model.baseline()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/data/reset")
def data_reset() -> dict:
    if RICE_PROFILE_PATH.exists():
        RICE_PROFILE_PATH.unlink()
    model.reload_data()
    return {"status": model.data_status(), "baseline": model.baseline()}


@app.post("/api/gtfs/scan")
def gtfs_scan(request: GTFSRequest) -> dict:
    try:
        return scan_gtfs(request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/gtfs/build")
def gtfs_build(request: GTFSRequest) -> dict:
    try:
        profile = build_gtfs_profile(
            request.source,
            GTFS_PROFILE_PATH,
            event_date=request.event_date,
            kickoff_time=request.kickoff_time,
        )
        model.reload_data()
        return {"status": model.data_status(), "profile": profile, "baseline": model.baseline()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/gtfs/reset")
def gtfs_reset() -> dict:
    if GTFS_PROFILE_PATH.exists():
        GTFS_PROFILE_PATH.unlink()
    model.reload_data()
    return {"status": model.data_status(), "baseline": model.baseline()}

@app.post("/api/osm/scan")
def osm_scan(request: OSMRequest) -> dict:
    try:
        return scan_osm(request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/osm/download")
def osm_download(request: OSMDownloadRequest) -> dict:
    try:
        bbox = {"south": request.south, "west": request.west, "north": request.north, "east": request.east}
        fetch_overpass(OSM_DOWNLOAD_PATH, bbox=bbox)
        return scan_osm(OSM_DOWNLOAD_PATH)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/osm/build")
def osm_build(request: OSMRequest) -> dict:
    try:
        profile = build_osm_profile(request.source, OSM_PROFILE_PATH)
        if TRAFFIC_PROFILE_PATH.exists():
            TRAFFIC_PROFILE_PATH.unlink()
        if CANDIDATE_PROFILE_PATH.exists():
            CANDIDATE_PROFILE_PATH.unlink()
        model.reload_data()
        return {"status": model.data_status(), "profile": profile, "baseline": model.baseline()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/osm/reset")
def osm_reset() -> dict:
    for path in (OSM_PROFILE_PATH, TRAFFIC_PROFILE_PATH, CANDIDATE_PROFILE_PATH):
        if path.exists():
            path.unlink()
    model.reload_data()
    return {"status": model.data_status(), "baseline": model.baseline()}


@app.post("/api/traffic/scan")
def traffic_scan(request: TrafficRequest) -> dict:
    try:
        return scan_traffic_counts(request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/traffic/build")
def traffic_build(request: TrafficRequest) -> dict:
    try:
        profile = build_traffic_profile(
            request.source,
            OSM_PROFILE_PATH,
            TRAFFIC_PROFILE_PATH,
            peak_hour_factor=request.peak_hour_factor,
            directional_factor=request.directional_factor,
            max_snap_miles=request.max_snap_miles,
        )
        model.reload_data()
        return {"status": model.data_status(), "profile": profile, "baseline": model.baseline()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/traffic/reset")
def traffic_reset() -> dict:
    if TRAFFIC_PROFILE_PATH.exists():
        TRAFFIC_PROFILE_PATH.unlink()
    model.reload_data()
    return {"status": model.data_status(), "baseline": model.baseline()}



@app.post("/api/candidates/scan")
def candidates_scan(request: CandidateRequest) -> dict:
    try:
        return scan_candidates(request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/candidates/build")
def candidates_build(request: CandidateRequest) -> dict:
    try:
        profile = build_candidate_profile(
            request.source,
            CANDIDATE_PROFILE_PATH,
            osm_profile_path=OSM_PROFILE_PATH,
        )
        model.reload_data()
        return {
            "status": model.data_status(),
            "profile": profile,
            "recommendations": model.candidate_recommendations(),
            "baseline": model.baseline(),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/candidates/reset")
def candidates_reset() -> dict:
    if CANDIDATE_PROFILE_PATH.exists():
        CANDIDATE_PROFILE_PATH.unlink()
    model.reload_data()
    return {"status": model.data_status(), "recommendations": model.candidate_recommendations(), "baseline": model.baseline()}


@app.post("/api/equity/scan")
def equity_scan(request: EquityRequest) -> dict:
    try:
        return scan_equity(request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/equity/build")
def equity_build(request: EquityRequest) -> dict:
    try:
        profile = build_equity_profile(request.source, EQUITY_PROFILE_PATH)
        model.reload_data()
        return {
            "status": model.data_status(),
            "profile": profile,
            "equity": model.equity_report(),
            "baseline": model.baseline(),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/equity/reset")
def equity_reset() -> dict:
    if EQUITY_PROFILE_PATH.exists():
        EQUITY_PROFILE_PATH.unlink()
    model.reload_data()
    return {"status": model.data_status(), "equity": model.equity_report(), "baseline": model.baseline()}
