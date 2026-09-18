"""Reproduce city evidence checks and example decision PDFs without external calls."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eventflow.universal import UniversalPlanner
from eventflow.pdf_report import build_pdf
from houston_mvp.data import load_dataset, load_routes
from houston_mvp.simulation import simulate_all

planner=UniversalPlanner(ROOT,None)
output=ROOT/'output/pdf'
output.mkdir(parents=True,exist_ok=True)
summary=[]
for city in ('Houston','New York'):
    with patch.object(planner,'_get_json',side_effect=AssertionError('Network access during evidence check')) as calls:
        result=planner.plan_from_brief('Concert in '+city,online=False,
            inputs={'city_query':city,'attendance':50000,'budget_usd':100000,'fleet_limit':100})
    calls.assert_not_called()
    plan=result['simulation']
    rows=plan['recommended']['routes']
    if any('screening' in r['source'] or 'Assumed' in r['return_source'] for r in rows):
        raise SystemExit('Missing or expired road snapshots; synchronize the database before validating.')
    pdf=output/('EventFlow-'+city.replace(' ','-')+'-model-report.pdf')
    pdf.write_bytes(build_pdf(result))
    summary.append({'city':city,'sites':[s['name'] for s in result['candidate_sites']],
        'road_routes':len(rows),'fleet':plan['recommended']['fleet'],
        'cost_usd':plan['recommended']['cost_usd'],
        'baseline_clearance_minutes':plan['baseline']['clearance_minutes'],
        'plan_clearance_minutes':plan['recommended']['clearance_minutes'],
        'baseline_queue_person_hours':plan['baseline']['queue_person_hours'],
        'plan_queue_person_hours':plan['recommended']['queue_person_hours'],
        'allocation':[{'site':r['name'],'buses':r['buses'],'outbound_minutes':r['outbound_minutes'],'return_minutes':r['return_minutes']} for r in rows],
        'stress_tests':plan['stress_tests'],'data_access':result['data_access']})

dataset=load_dataset()
current=simulate_all(dataset)
previous=simulate_all(replace(dataset,routes=load_routes()))
report={'scope':'Reproducible screening scenarios, not observed performance validation',
        'shared_inputs':{'attendance':50000,'budget_usd':100000,'cohort_pct':40,'baseline_service_pph':12000,'road_delay_factor':1.3},
        'cities':summary,'houston_intro':{'public_road_routes':dataset.evidence['road_routes'],
        'survey_locations':dataset.evidence['traffic_survey_sites'],
        'old_baseline_average_trip_minutes':previous['scenarios'][0]['kpis']['avg_travel_minutes'],
        'new_baseline_average_trip_minutes':current['scenarios'][0]['kpis']['avg_travel_minutes']}}
(ROOT/'docs/city_model_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'cities':[{k:v for k,v in row.items() if k not in ('allocation','stress_tests','data_access')} for row in summary],'houston_intro':report['houston_intro']},ensure_ascii=False,indent=2))
