from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eventflow.local_data import scan_root


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Rice World Cup Hack compressed datasets without third-party packages.")
    parser.add_argument("--root", default="/Users/linda/Desktop/Rice WC Hack")
    args = parser.parse_args()

    report = scan_root(args.root)
    out = ROOT / "data" / "sample" / "local_scan_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
