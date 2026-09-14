#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eventflow.osm_ingestion import DEFAULT_BBOX, build_osm_profile, fetch_overpass, scan_osm
from eventflow.traffic_ingestion import build_traffic_profile, scan_traffic_counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build EventFlow's OSM road graph and optional traffic calibration.")
    parser.add_argument("--osm-source", default=str(ROOT / "data" / "sample" / "mock_overpass_houston.json"))
    parser.add_argument("--download", action="store_true", help="Download a fresh Overpass JSON before building.")
    parser.add_argument("--south", type=float, default=DEFAULT_BBOX["south"])
    parser.add_argument("--west", type=float, default=DEFAULT_BBOX["west"])
    parser.add_argument("--north", type=float, default=DEFAULT_BBOX["north"])
    parser.add_argument("--east", type=float, default=DEFAULT_BBOX["east"])
    parser.add_argument("--traffic-source")
    parser.add_argument("--peak-hour-factor", type=float, default=0.09)
    parser.add_argument("--directional-factor", type=float, default=0.55)
    parser.add_argument("--max-snap-miles", type=float, default=1.25)
    args = parser.parse_args()

    osm_source = Path(args.osm_source).expanduser()
    if args.download:
        osm_source = ROOT / "data" / "local" / "houston_overpass.json"
        print(f"Downloading OSM roads to {osm_source} ...")
        fetch_overpass(
            osm_source,
            bbox={"south": args.south, "west": args.west, "north": args.north, "east": args.east},
        )

    report = scan_osm(osm_source)
    print(f"OSM: {report['node_count']} nodes, {report['way_count']} ways")
    osm_profile = ROOT / "data" / "local" / "osm_profile.json"
    profile = build_osm_profile(osm_source, osm_profile)
    print(f"Built: {profile['edge_count']} directed edges, {sum(bool(v) for v in profile['routes'].values())}/6 origin routes")

    if args.traffic_source:
        traffic_report = scan_traffic_counts(args.traffic_source)
        if not traffic_report["ready"]:
            raise SystemExit(f"Traffic file columns were not recognized: {traffic_report['fields']}")
        traffic_profile = ROOT / "data" / "local" / "traffic_profile.json"
        calibrated = build_traffic_profile(
            args.traffic_source,
            osm_profile,
            traffic_profile,
            peak_hour_factor=args.peak_hour_factor,
            directional_factor=args.directional_factor,
            max_snap_miles=args.max_snap_miles,
        )
        print(
            f"Traffic: {calibrated['matched_count_points']} points matched, "
            f"{calibrated['directly_calibrated_edges']} edges directly calibrated"
        )


if __name__ == "__main__":
    main()
