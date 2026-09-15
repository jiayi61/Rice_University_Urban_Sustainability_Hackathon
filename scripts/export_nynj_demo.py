"""Export the same model used by the API for a static, login-free demonstration."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eventflow.nynj import NYNJEngine,narrative

engine=NYNJEngine(ROOT);default=engine.plan();default['narrative']=narrative(default)
out=ROOT/'app/static';out.mkdir(exist_ok=True)
context_keys=['case','source','rice','public_status','acs','map','assumptions','validation','observed_matches']
context={k:default[k] for k in context_keys}
# The hosted demo exposes aggregate educational context only; full organizer records remain private.
if context['rice'].get('available'):
    for d in context['rice']['datasets'].values():d.pop('shards',None)
scenarios={}
for b in [250000,500000,1000000]:
 for priority in ['balanced','equity','resilience']:
  for stress in ['normal','rail_outage','heat_wave','demand_surge']:
   p=engine.plan(b,priority,stress);p['narrative']=narrative(p)
   scenarios[f'{b}:{priority}:{stress}']={k:v for k,v in p.items() if k not in context_keys}
(out/'competition-data.json').write_text(json.dumps(context,separators=(',',':'))+'\n')
(out/'competition-scenarios.json').write_text(json.dumps(scenarios,separators=(',',':'))+'\n')
(ROOT/'docs/NYNJ_SUBMISSION.md').write_text(narrative(default))
print('Exported',len(scenarios),'independently computed control combinations; source context shared.')
