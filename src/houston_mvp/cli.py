from __future__ import annotations

import argparse
import json
from pathlib import Path

from .advisor import attach_advice
from .data import load_dataset
from .simulation import simulate_all


ROOT = Path(__file__).resolve().parents[2]


def build_dashboard_payload() -> dict:
    dataset = load_dataset()
    payload = simulate_all(dataset)
    return attach_advice(payload)


def write_dashboard_payload(out_path: Path) -> dict:
    payload = build_dashboard_payload()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate FIFA 2026 Houston EventFlow dashboard data."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "outputs" / "dashboard_data.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()
    payload = write_dashboard_payload(args.out)
    print(
        f"Wrote {args.out} with {len(payload['scenarios'])} scenarios and "
        f"{payload['metadata']['total_visitors']:,} synthetic visitors."
    )


if __name__ == "__main__":
    main()
