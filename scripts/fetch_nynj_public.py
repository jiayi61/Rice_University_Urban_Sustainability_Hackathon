"""Acquire public NY/NJ geometry and aggregate evidence, recording failures explicitly."""
import csv, hashlib, io, json, math, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data/nynj';OUT.mkdir(parents=True,exist_ok=True)
def get(url):
    with urlopen(Request(url,headers={'User-Agent':'EventFlow university research prototype; reproducible public data snapshot'}),timeout=60) as r:return r.read()
def save(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2)+'\n')
status=[]
gtfs_url='https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip'
try:
    raw=get(gtfs_url);z=zipfile.ZipFile(io.BytesIO(raw))
    def rows(name):return list(csv.DictReader(io.TextIOWrapper(z.open(name),encoding='utf-8-sig')))
    stops=[{'id':r['stop_id'],'name':r['stop_name'],'lat':float(r['stop_lat']),'lon':float(r['stop_lon'])} for r in rows('stops.txt') if r.get('location_type')=='1']
    trips=rows('trips.txt');wanted={}
    for t in trips:wanted.setdefault(t['route_id'],t['shape_id'])
    shapes={v:[] for v in wanted.values()}
    for r in rows('shapes.txt'):
        if r['shape_id'] in shapes:shapes[r['shape_id']].append((int(r['shape_pt_sequence']),float(r['shape_pt_lat']),float(r['shape_pt_lon'])))
    lines=[]
    for r in rows('routes.txt'):
        if r['route_id'] in wanted:
            pts=sorted(shapes[wanted[r['route_id']]]);step=max(1,len(pts)//160)
            geom=[[p[1],p[2]] for p in pts[::step]]
            if pts and geom[-1]!=list(pts[-1][1:]):geom.append(list(pts[-1][1:]))
            lines.append({'id':r['route_id'],'name':r['route_short_name'],'color':'#'+r.get('route_color','557c8c'),'geometry':geom})
    save('mta_subway.json',{'source_url':gtfs_url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(raw).hexdigest(),'class':'Observed public data','scope':'Current regular subway GTFS geometry only, not historical FIFA service or a connection into New Jersey.','stations':stops,'routes':lines})
    status.append({'source':'MTA regular subway GTFS','status':'ingested','stations':len(stops),'routes':len(lines),'url':gtfs_url})
except Exception as e:status.append({'source':'MTA regular subway GTFS','status':'unavailable','error':str(e),'url':gtfs_url})

acs=[]
for state,counties in [('36',['005','047','061','081','085']),('34',['003','013','017','031','039'])]:
    url='https://api.census.gov/data/2024/acs/acs5?'+urlencode({'get':'NAME,B08201_001E,B08201_002E,B08201_001M,B08201_002M','for':'county:*','in':'state:'+state})
    try:
        table=json.loads(get(url))
        for row in table[1:]:
            r=dict(zip(table[0],row))
            if r['county'] in counties:
                total=int(r['B08201_001E']);zero=int(r['B08201_002E'])
                acs.append({'name':r['NAME'],'fips':r['state']+r['county'],'households':total,'zero_vehicle_households':zero,'zero_vehicle_share':zero/total,'total_moe':int(r['B08201_001M']),'zero_vehicle_moe':int(r['B08201_002M']),'source_url':url})
        status.append({'source':'ACS 2024 5-year state '+state,'status':'ingested','url':url})
    except Exception as e:status.append({'source':'ACS 2024 5-year state '+state,'status':'unavailable','error':str(e),'url':url})
save('acs_context.json',{'class':'Derived estimate from ACS survey estimates','scope':'Resident county context, not visitor characteristics or an ADA audit. ACS margins of error retained.','counties':acs})

anchors=[('penn','New York Penn Station',40.7506,-73.9935),('secaucus','Secaucus Junction',40.7612,-74.0754),('stadium','MetLife Stadium',40.8135,-74.0745),('newark','Newark Penn Station',40.7347,-74.1647),('hoboken','Hoboken Terminal',40.7359,-74.0303),('american_dream','American Dream',40.8095,-74.0669),('racetrack','Meadowlands Racetrack',40.8195,-74.0706)]
resolved=[]
for key,name,lat,lon in anchors:
    url='https://nominatim.openstreetmap.org/search?'+urlencode({'q':name+' New York New Jersey USA','format':'jsonv2','limit':1})
    try:
        hits=json.loads(get(url));h=hits[0] if hits else None
        if h and 40.45<float(h['lat'])<41.2 and -74.5<float(h['lon'])<-73.5:lat,lon=float(h['lat']),float(h['lon']);source='OpenStreetMap Nominatim';evidence='Observed public geometry'
        else:source='Approximate planning anchor';evidence='Scenario assumption'
    except Exception:source='Approximate planning anchor';evidence='Scenario assumption'
    resolved.append({'id':key,'name':name,'lat':lat,'lon':lon,'source':source,'class':evidence,'source_url':url});time.sleep(1)
save('anchors.json',resolved)
routes=[];dest=next(x for x in resolved if x['id']=='stadium')
for a in resolved:
    if a['id']=='stadium':continue
    url=f"https://router.project-osrm.org/route/v1/driving/{a['lon']},{a['lat']};{dest['lon']},{dest['lat']}?overview=full&geometries=geojson"
    try:
        r=json.loads(get(url))['routes'][0]
        routes.append({'id':a['id'],'name':a['name'],'geometry':[[p[1],p[0]] for p in r['geometry']['coordinates']],'distance_km':round(r['distance']/1000,2),'freeflow_minutes':round(r['duration']/60,1),'source_url':url,'class':'Derived estimate','basis':'OSRM driving route over OSM roads; not a transit route, live traffic or a verified event detour.'})
    except Exception as e:status.append({'source':'OSRM '+a['name'],'status':'unavailable','error':str(e)})
save('road_routes.json',routes)
save('public_status.json',status)
print(json.dumps(status,indent=2));print('anchors',len(resolved),'road routes',len(routes))
