from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eventflow.local_data import build_houston_profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a sampled Houston calibration profile from Rice compressed datasets.")
    parser.add_argument("--root", default="/Users/linda/Desktop/Rice WC Hack")
    parser.add_argument("--max-files", type=int, default=1)
    parser.add_argument("--max-rows", type=int, default=75000)
    parser.add_argument("--attendance", type=int, default=72000)
    args = parser.parse_args()

    output = ROOT / "data" / "local" / "houston_profile.json"
    profile = build_houston_profile(
        args.root,
        output,
        max_files=args.max_files,
        max_rows_per_file=args.max_rows,
        event_attendance=args.attendance,
    )
    print(json.dumps({
        "mode": profile["mode"],
        "built_at": profile["built_at"],
        "zones": profile["zones"],
        "warnings": profile["warnings"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
