"""Export the same model used by the API for a static, login-free demonstration."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eventflow.nynj import NYNJEngine,narrative
from houston_mvp.data import load_dataset
from houston_mvp.simulation import simulate_all

CONCERT_COHORT=50000
CONCERT_SCALE=CONCERT_COHORT/48392

def concert_plan(engine,b=500000,priority='balanced',stress='normal'):
    result=engine.plan(b,priority,stress,scale=CONCERT_SCALE)
    result['case']={**result['case'],'type':'Prepared hypothetical stadium concert scenario','date':None,'attendance':None,'modelled_departures':CONCERT_COHORT,'cohort_note':'Assumed 50,000 concert departures across three modes; mode shares and reference rates transferred from the historical FIFA final. Not observed concert attendance.'}
    for assumption in result['assumptions']:
        if assumption['name']=='Demand release':assumption['value']='Assumed 50,000 concert departures released together at concert end'
    result['narrative']=narrative(result).replace('FIFA 2026 egress decision case','Prepared stadium concert scenario')
    result['narrative']=result['narrative'].replace('## Evidence and scope','## Concert scenario assumptions\nHypothetical MetLife Stadium concert in the New York region, physically in East Rutherford, New Jersey. Date unspecified. Assumed 50,000 departures; historical final-match mode shares and service rates transferred for this demonstration. The submitted free-text brief does not change these assumptions.\n\n## Historical evidence and scope')
    return result

engine=NYNJEngine(ROOT);default=concert_plan(engine)
out=ROOT/'app/static';out.mkdir(exist_ok=True)
context_keys=['case','source','rice','public_status','acs','map','assumptions','validation','observed_matches']
context={k:default[k] for k in context_keys}
houston=simulate_all(load_dataset())
context['houston']={'metadata':houston['metadata'],'scenarios':[x for x in houston['scenarios'] if x['name'] in ['Baseline','Mixed Optimized']]}
# The hosted demo exposes aggregate educational context only; full organizer records remain private.
if context['rice'].get('available'):
    for d in context['rice']['datasets'].values():d.pop('shards',None)
scenarios={}
for b in [250000,500000,1000000]:
 for priority in ['balanced','equity','resilience']:
  for stress in ['normal','rail_outage','heat_wave','demand_surge']:
   p=concert_plan(engine,b,priority,stress)
   scenarios[f'{b}:{priority}:{stress}']={k:v for k,v in p.items() if k not in context_keys}
(out/'competition-data.json').write_text(json.dumps(context,separators=(',',':'))+'\n')
(out/'competition-scenarios.json').write_text(json.dumps(scenarios,separators=(',',':'))+'\n')
(ROOT/'docs/NYNJ_SUBMISSION.md').write_text(default['narrative'])
print('Exported',len(scenarios),'independently computed control combinations; source context shared.')
