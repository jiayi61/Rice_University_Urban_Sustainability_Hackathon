"""Refresh the Houston introduction from the same model as /api/houston-mvp."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from houston_mvp.data import load_dataset
from houston_mvp.simulation import simulate_all

payload=simulate_all(load_dataset())
path=ROOT/'app/static/competition-data.json'
context=json.loads(path.read_text())
context['houston']={'metadata':payload['metadata'],'scenarios':[s for s in payload['scenarios'] if s['name'] in ('Baseline','Mixed Optimized')]}
path.write_text(json.dumps(context,separators=(',',':'))+'\n')
print(json.dumps({k:v for k,v in payload['metadata']['evidence'].items() if k!='survey_features'},indent=2))
