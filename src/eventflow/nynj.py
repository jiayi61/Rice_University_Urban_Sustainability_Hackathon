"""Auditable NY/NJ egress portfolio model. No preset improvement percentages.

Agency egress cohorts anchor an aggregate fluid-service model. Proposed service
rates, take-up, costs and emissions factors remain explicit planning assumptions.
This is not a calibrated street traffic model or individual waiting-time forecast.
"""
from __future__ import annotations
import csv, itertools, json, math, statistics
from pathlib import Path
from functools import lru_cache

MODES=('rail','shuttle','rideshare')
PRIORITIES=('balanced','equity','resilience')
STRESSES=('normal','rail_outage','heat_wave','demand_surge')
ACTION_LIST=[
 {'id':'shuttle','name':'Reserve 20 event coaches','cost':140000,'low':105000,'high':185000,'owner':'NYNJ Host Committee + contracted bus operator','lead_days':60,'location':'Secaucus / stadium contingency loading area','units':'20 coaches × 50 seats × 85% usable load; 60-minute cycle','dependency':'Signed charter, driver roster, verified loading and layover capacity','verification':'Actual departures, loads and cycle minutes','basis':'Scenario allowance; fleet arithmetic is explicit; local quotes required.'},
 {'id':'bus_priority','name':'Protect the shuttle operating window','cost':80000,'low':60000,'high':110000,'owner':'NJDOT + NJ TRANSIT + venue traffic operations','lead_days':45,'location':'Approved Meadowlands shuttle approach','units':'Temporary traffic management; assumed 20% shorter coach cycle','dependency':'Traffic-engineering approval, emergency access and police staffing','verification':'Coach cycle time and effect on other road users','basis':'Assumed operational effect; requires a field trial. Does not claim a new road is approved.'},
 {'id':'rail_overlay','name':'Add four train departures','cost':180000,'low':140000,'high':240000,'owner':'NJ TRANSIT rail operations + infrastructure partners','lead_days':90,'location':'Secaucus–Meadowlands service','units':'4 departures × 1,000 planning places × 80% usable load','dependency':'Fleet, train crews, train-path approval and platform control','verification':'Dispatched departures and boarded passengers','basis':'Planning capacity and procurement allowance; train capacity is not agency-certified.'},
 {'id':'curb','name':'Manage rideshare loading and geofencing','cost':65000,'low':45000,'high':95000,'owner':'Venue + rideshare operators + local police','lead_days':30,'location':'Meadowlands Racetrack loading area','units':'Marshals and signed holding areas; assumed 15% service-rate gain','dependency':'Operator agreement, accessible pickup and spillback checks','verification':'Vehicles served per hour and queue spillback','basis':'Unvalidated intervention effect; tested at 50–150% of this assumption.'},
 {'id':'shade','name':'Shade and water at transfer queues','cost':90000,'low':65000,'high':125000,'owner':'Venue + local public-health and emergency-service partners','lead_days':21,'location':'Stadium and American Dream transfer approaches','units':'3,500-person simultaneous shade coverage; assumed 40% exposure reduction within coverage','dependency':'Site permission, water/power, wind limits and replenishment','verification':'Usable shaded space, queue exposure and replenishment','basis':'Rental and operating allowance; exposure proxy is not prevented illness.'},
 {'id':'accessible','name':'Reserve accessible transfer capacity','cost':110000,'low':85000,'high':150000,'owner':'NJ TRANSIT accessibility staff + contracted operator','lead_days':60,'location':'Secaucus and stadium accessible transfer points','units':'8 vehicles × 24 planning seats × 80% load; 60-minute cycle','dependency':'Vehicle certification, continuous accessible path and trained staff','verification':'Accessible trips delivered and requests left unserved','basis':'Planned accessible-service seats, not a claim that all seats are wheelchair spaces.'},
 {'id':'wayfinding','name':'Staff the Penn–Secaucus transfer','cost':40000,'low':30000,'high':60000,'owner':'NJ TRANSIT + Host Committee','lead_days':21,'location':'New York Penn, Secaucus and Meadowlands stations','units':'Multilingual transfer teams; assumed 5% rail processing-rate gain','dependency':'Station approval, language review and accessible information','verification':'Missed transfers, boarding throughput and assistance requests','basis':'Scenario assumption; the agency report supports the need, not this effect size.'},
]
ACTIONS={a['id']:a for a in ACTION_LIST}

def quantile(values,q):
    values=sorted(values);at=(len(values)-1)*q;lo=int(at);hi=math.ceil(at)
    return values[lo]+(values[hi]-values[lo])*(at-lo)

class NYNJEngine:
    def __init__(self,root):
        self.root=Path(root);self.data=self.root/'data/nynj'
        with (self.data/'observed_egress.csv').open() as f:self.observed=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)]
        self.source=self.read('observed_source.json',{})
    def read(self,name,default):
        p=self.data/name
        return json.loads(p.read_text()) if p.exists() else default
    def sample_context(self):
        raw=self.read('rice_aggregate.json',{})
        if not raw:return {'available':False,'label':'Organizer aggregation pending','heat_weight':1.0}
        d=raw['datasets'];uhi=d.get('uhi',{}).get('uhi',{});den=sum(uhi.values());mean=sum(float(k)*v for k,v in uhi.items())/den if den else None
        return {'available':True,'label':'Organizer sample data — transformed; method demonstration only','heat_weight':1+(mean-1)/10 if mean is not None else 1,'uhi_mean':mean,'datasets':d,'limitations':raw['limitations'],'coverage':raw['coverage']}
    def rates(self,exclude=None):
        rows=[r for r in self.observed if r['match_id']!=exclude]
        return {m:statistics.median(r[m+'_passengers']/r[m+'_minutes']*60 for r in rows) for m in MODES}
    def validate(self):
        results=[]
        for row in self.observed:
            rates=self.rates(row['match_id'])
            for mode in MODES:
                pred=row[mode+'_passengers']/rates[mode]*60
                results.append({'match_id':row['match_id'],'mode':mode,'observed_minutes':row[mode+'_minutes'],'predicted_minutes':round(pred,1),'absolute_error_minutes':round(abs(pred-row[mode+'_minutes']),1)})
        return {'method':'Leave one match out: estimate median realized passengers/hour on seven matches; predict the excluded match clearance window. All eight held-out cases shown.','scope':'Tests aggregate baseline transfer only; does not validate an intervention, individual waits, or a street-level model.','mae_by_mode':{m:round(statistics.mean(r['absolute_error_minutes'] for r in results if r['mode']==m),1) for m in MODES},'cases':results,'sample_size':8}
    def simulate(self,ids=(),stress='normal',scale=1.0,demand_factor=1.0,capacity_factor=1.0,effect_factor=1.0,heat_factor=1.0):
        ids=set(ids);reference=self.observed[-1]
        demand_scale=scale*demand_factor*(1.25 if stress=='demand_surge' else 1)
        original={m:reference[m+'_passengers']*demand_scale for m in MODES};demand=original.copy()
        # Reference-match realized rates anchor the retrospective scenario, not theoretical capacities.
        rate={m:reference[m+'_passengers']/reference[m+'_minutes']*60*capacity_factor for m in MODES}
        rail_factor=.15 if stress=='rail_outage' else 1.0
        rate['rail']*=rail_factor
        if stress=='heat_wave':rate={m:r*.9 for m,r in rate.items()}
        cycle=60*(1-.20*min(effect_factor,1.5) if 'bus_priority' in ids else 1)
        hours=2
        extra_coach_hour=20*50*.85*60/cycle if 'shuttle' in ids else 0
        access_hour=8*24*.8*60/cycle if 'accessible' in ids else 0
        added_shuttle_capacity=(extra_coach_hour+access_hour)*hours
        # Voluntary switching is bounded by actual additional seats and a declared take-up assumption.
        shifted=min(original['rideshare']*.20*effect_factor,added_shuttle_capacity)
        demand['rideshare']-=shifted;demand['shuttle']+=shifted
        rate['shuttle']+=extra_coach_hour+access_hour
        if 'bus_priority' in ids:rate['shuttle']*=1+.10*effect_factor
        if 'rail_overlay' in ids:rate['rail']+=4*1000*.8/hours*rail_factor
        if 'wayfinding' in ids:rate['rail']*=1+.05*effect_factor
        if 'curb' in ids:rate['rideshare']*=1+.15*effect_factor
        clear={m:demand[m]/max(1,rate[m])*60 for m in MODES}
        # All modelled cohorts released at final whistle: conservative fluid queue abstraction.
        waiting={m:demand[m]*clear[m]/120 for m in MODES}
        total=sum(demand.values());within=sum(min(demand[m],rate[m]*hours) for m in MODES)
        shade_fraction=min(1,3500/max(1,total)) if 'shade' in ids else 0
        heat_multiplier=heat_factor*(1.5 if stress=='heat_wave' else 1)
        heat=sum(waiting.values())*heat_multiplier*(1-shade_fraction*.4*effect_factor)
        car_km=demand['rideshare']/2.2*18
        new_bus_km=((20 if 'shuttle' in ids else 0)+(8 if 'accessible' in ids else 0))*hours*60/cycle*12*1.5
        emissions=car_km*.192+new_bus_km*1.2
        accessible=access_hour*hours
        cost=sum(ACTIONS[i]['cost'] for i in ids)
        timeline=[{'minute':t,**{m:round(max(0,demand[m]-rate[m]*t/60)) for m in MODES}} for t in range(0,481,15)]
        return {'ids':sorted(ids),'cost':cost,'cost_low':sum(ACTIONS[i]['low'] for i in ids),'cost_high':sum(ACTIONS[i]['high'] for i in ids),'cohort':round(total),'demand':{m:round(v,1) for m,v in demand.items()},'rates':{m:round(v,1) for m,v in rate.items()},'clearance_minutes':{m:round(v,1) for m,v in clear.items()},'max_clearance_minutes':round(max(clear.values()),1),'queue_person_hours':round(sum(waiting.values()),1),'served_in_120':round(within),'coverage_pct':round(within/total*100,1),'shifted_riders':round(shifted),'accessible_service_seats':round(accessible),'heat_exposure_index':round(heat,1),'affected_leg_emissions_kg':round(emissions,1),'timeline':timeline}
    @staticmethod
    def gains(base,plan):
        def reduction(k):return (base[k]-plan[k])/max(1,base[k])*100
        return {'clearance_pct':round(reduction('max_clearance_minutes'),1),'queue_pct':round(reduction('queue_person_hours'),1),'emissions_pct':round(reduction('affected_leg_emissions_kg'),1),'heat_pct':round(reduction('heat_exposure_index'),1),'additional_served':plan['served_in_120']-base['served_in_120']}
    def score(self,base,p,priority,stress,scale):
        gains=self.gains(base,p);value=.45*gains['queue_pct']+.30*gains['clearance_pct']+.15*gains['heat_pct']+.10*gains['emissions_pct']
        if priority=='equity':value=.55*value+.45*min(100,p['accessible_service_seats']/max(1,p['cohort']*.08)*100)
        if priority=='resilience':
            outage=self.simulate(p['ids'],'rail_outage',scale);b=self.simulate((),'rail_outage',scale)
            value=.45*value+.55*self.gains(b,outage)['queue_pct']
        return round(value,5)
    def catalog(self):
        return {'case':'New York / New Jersey — MetLife Stadium','actions':ACTION_LIST,'priorities':list(PRIORITIES),'stresses':list(STRESSES),'source':self.source}
    def plan(self,budget=500000,priority='balanced',stress='normal',scale=1.0):
        budget=float(budget);scale=float(scale)
        if not math.isfinite(budget) or not 0<=budget<=2000000:raise ValueError('Budget must be between $0 and $2,000,000.')
        if not math.isfinite(scale) or not .25<=scale<=1.5:raise ValueError('Demand multiplier must be 0.25–1.5.')
        if priority not in PRIORITIES or stress not in STRESSES:raise ValueError('Unknown priority or disruption.')
        base=self.simulate((),stress,scale);candidates=[]
        for mask in range(2**len(ACTION_LIST)):
            ids=[a['id'] for i,a in enumerate(ACTION_LIST) if mask&(1<<i)]
            p=self.simulate(ids,stress,scale);p['score']=self.score(base,p,priority,stress,scale);candidates.append(p)
        feasible=[p for p in candidates if p['cost']<=budget]
        best=max(feasible,key=lambda p:(p['score'],-p['cost']))
        # A portfolio is dominated only when another costs no more and scores at least as well.
        frontier=[];highest=-float('inf')
        for p in sorted(candidates,key=lambda p:(p['cost'],-p['score'])):
            if p['score']>highest+1e-8:frontier.append({'cost':p['cost'],'score':p['score'],'ids':p['ids'],'coverage_pct':p['coverage_pct'],'clearance_minutes':p['max_clearance_minutes']});highest=p['score']
        ranges={k:[] for k in ['clearance_pct','queue_pct','emissions_pct','heat_pct']}
        sample=self.sample_context();sample_heat=sample.get('heat_weight',1)
        for d,c,e,h in itertools.product([.85,1,1.15],[.85,1,1.15],[.5,1,1.5],[.8,1,1.2]):
            b=self.simulate((),stress,scale,d,c,e,h*sample_heat);p=self.simulate(best['ids'],stress,scale,d,c,e,h*sample_heat)
            g=self.gains(b,p)
            for k in ranges:ranges[k].append(g[k])
        uncertainty={k:{'min':round(min(v),1),'p10':round(quantile(v,.1),1),'median':round(statistics.median(v),1),'p90':round(quantile(v,.9),1),'max':round(max(v),1)} for k,v in ranges.items()}
        marginal=[]
        for i in best['ids']:
            without=self.simulate([a for a in best['ids'] if a!=i],stress,scale)
            marginal.append({'id':i,'name':ACTIONS[i]['name'],'cost':ACTIONS[i]['cost'],'queue_person_hours_avoided':round(without['queue_person_hours']-best['queue_person_hours'],1),'score_contribution':round(best['score']-self.score(base,without,priority,stress,scale),2)})
        stress_results=[]
        for s in STRESSES:
            b=self.simulate((),s,scale);p=self.simulate(best['ids'],s,scale)
            stress_results.append({'id':s,'baseline_minutes':b['max_clearance_minutes'],'plan_minutes':p['max_clearance_minutes'],'coverage_pct':p['coverage_pct'],'queue_pct':self.gains(b,p)['queue_pct']})
        result={'schema_version':'4.0','case':{'city':'New York / New Jersey','venue':'MetLife Stadium · East Rutherford, NJ','type':'Retrospective FIFA 2026 egress case + future-event scenarios','reference_match':104,'date':'2026-07-19','attendance':80663,'cohort_note':'Models the three reported egress cohorts only; excludes other spectators and overlapping pedestrian counts. Time zero is final whistle.'},'inputs':{'budget':budget,'priority':priority,'stress':stress,'demand_scale':scale},'baseline':base,'recommended':best,'gains':self.gains(base,best),'frontier':frontier,'feasible_portfolios':len(feasible),'sensitivity':{'runs':81,'interpretation':'Deterministic assumption scenarios, not a statistical confidence interval; same selected portfolio in all runs.','ranges':uncertainty},'stress_tests':stress_results,'marginal':marginal,'implementation':[ACTIONS[i] for i in best['ids']],'validation':self.validate(),'observed_matches':self.observed,'source':self.source,'rice':sample,'public_status':self.read('public_status.json',[]),'acs':self.read('acs_context.json',{}),'map':{'anchors':self.read('anchors.json',[]),'roads':self.read('road_routes.json',[]),'subway':self.read('mta_subway.json',{})},'assumptions':[
            {'name':'Reference service rates','value':'Reported final-match passengers ÷ reported clearance hours','class':'Derived estimate','limit':'Realized throughput is not maximum capacity; source includes rail contingency operations.'},
            {'name':'Demand release','value':'All three modelled cohorts enter at final whistle','class':'Scenario assumption','limit':'Conservative fluid-queue abstraction; not actual arrival observations.'},
            {'name':'Voluntary mode shift','value':'Up to 20% of rideshare cohort, bounded by added coach seats','class':'Scenario assumption','limit':'Tested at 50–150% effectiveness; no causal evidence.'},
            {'name':'Intervention costs','value':'One-event incremental low / central / high allowances','class':'Scenario assumption','limit':'Costs include planned delivery allowance; require local vendor and agency review.'},
            {'name':'Emissions boundary','value':'Affected rideshare and incremental coach legs only: 2.2 people/car, 18 km car trip, 0.192 kg/car-km; 12 km coach cycle-distance basis, 50% extra deadhead, 1.2 kg/bus-km','class':'Scenario assumption','limit':'Not total tournament emissions; tests can show negative savings.'},
            {'name':'Accessible demand target','value':'Planning target = 8% of the three-cohort demand','class':'Scenario assumption','limit':'Not measured disability prevalence. Equity objective prioritizes accessible-service seats.'},
            {'name':'Heat exposure','value':'Queue-person-hours × relative weather/UHI scenario weight','class':'Model projection','limit':'Organizer UHI contributes only a relative scenario index; no degree conversion or health outcome claim.'},
            {'name':'Street / last-mile conditions','value':'OSM geometry + MTA current regular subway snapshot','class':'Observed public data / derived geometry','limit':'NJ TRANSIT FIFA GTFS, observed road counts and accessible-path audit are not ingested. No street traffic or ADA claims.'}
        ]}
        return result

def narrative(payload):
    p=payload['recommended'];g=payload['gains'];u=payload['sensitivity'];inp=payload['inputs']
    lines=['# EventFlow — From Crowd Forecast to City Action','## New York / New Jersey: FIFA 2026 egress decision case','',f"Budget: ${inp['budget']:,.0f}. Priority: {inp['priority']}. Disruption: {inp['stress']}.",'','## Evidence and scope','NJ TRANSIT reported eight matches of aggregate egress passenger counts and clearance windows. The reference is Match 104, July 19, 2026. This retrospective case models only rail, Host Committee shuttle and rideshare cohorts; their sum is not total attendance. Organizer Rice data are transformed educational samples, retained as separate historical context and relative heat scenarios.','',f"Source: {payload['source']['source_url']}",'','## Scenario result',f"Selected incremental planning cost: ${p['cost']:,.0f} (range ${p['cost_low']:,.0f}–${p['cost_high']:,.0f}).",f"Modelled maximum clearance window: {payload['baseline']['max_clearance_minutes']:.0f} → {p['max_clearance_minutes']:.0f} minutes.",f"Modelled queue-person-hours reduction: {g['queue_pct']}%. Across 81 deterministic scenarios: {u['ranges']['queue_pct']['min']}–{u['ranges']['queue_pct']['max']}% (not a confidence interval).",'','## Selected actions']
    for a in payload['implementation']:lines.append(f"- {a['name']}: ${a['cost']:,.0f}; proposed owner {a['owner']}; planning lead {a['lead_days']} days; dependency: {a['dependency']}; verify: {a['verification']}.")
    lines+=['','## Validation and limitations',payload['validation']['method'],f"Leave-one-match-out mean absolute error (minutes): {payload['validation']['mae_by_mode']}.",'Baseline transfer validation does not validate proposed interventions. Costs, take-up, service effects, emissions factors and accessibility demand remain assumptions. No operational deployment or agency partnership is claimed. Historical GTFS, road counts, pedestrian flow time series and external intervention evaluation remain outstanding.','','## Legacy','Use the same cohort accounting, budget search, uncertainty scenarios and implementation checklist for future stadium events, after replacing event demand and verifying operating constraints.']
    return '\n'.join(lines)+'\n'
