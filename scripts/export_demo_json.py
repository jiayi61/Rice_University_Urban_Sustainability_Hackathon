from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eventflow.model import EventFlowModel

model = EventFlowModel()
outputs = {
    "baseline": model.baseline(),
    "optimized_500k": model.optimize(500000),
}
(ROOT / "data" / "sample" / "demo_outputs.json").write_text(
    json.dumps(outputs, indent=2), encoding="utf-8"
)
print(ROOT / "data" / "sample" / "demo_outputs.json")
