#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eventflow.model import EventFlowModel  # noqa: E402
from eventflow.submission import build_submission_package  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export EventFlow competition submission package.")
    parser.add_argument("--budget", type=float, default=500000)
    parser.add_argument("--time-window", default="ingress_peak")
    parser.add_argument("--objective-mode", default="balanced")
    args = parser.parse_args()

    local = ROOT / "data" / "local"
    model = EventFlowModel(
        local / "houston_profile.json",
        local / "gtfs_profile.json",
        local / "osm_profile.json",
        local / "traffic_profile.json",
        local / "candidate_profile.json",
        local / "equity_profile.json",
    )
    package = build_submission_package(
        model,
        budget_usd=args.budget,
        time_window=args.time_window,
        objective_mode=args.objective_mode,
    )
    out = ROOT / "data" / "exports"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "eventflow_submission_package_v0_9.json"
    md_path = out / "eventflow_submission_narrative_v0_9.md"
    json_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(package["markdown"], encoding="utf-8")
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
