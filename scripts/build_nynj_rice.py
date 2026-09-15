"""Stream every organizer shard into auditable NY/NJ aggregates; never invent missing joins."""
import argparse, concurrent.futures, hashlib, json, time
from collections import Counter
from pathlib import Path
import pandas as pd

DATASETS = {
    'poi': ('core-poi-geometry-rice', ['MARKET','LATITUDE','LONGITUDE','STORE_ID','PLACEKEY','TOP_CATEGORY']),
    'uhi': ('urban-heat-index-rice', ['MARKET','LATITUDE','LONGITUDE','UHI']),
    'visits': ('store-visits-rice', ['MARKET','LOCAL_DATE','STORE_ID','DAILY_VISITS']),
    'spend': ('spend-patterns-rice', ['MARKET','SPEND_DATE_RANGE_START','RAW_NUM_CUSTOMERS','RAW_TOTAL_SPEND']),
    'daily_spend': ('daily-spend-brand-and-state-rice', ['MARKET','TRANS_DATE','SPEND_AMOUNT','TRANS_COUNT']),
    'weather': ('daily-weather-rice', ['CITY_LOCATION_IDENTIFIER__UP_TO_9_ALPHANUMERIC_CHARACTERS_','VALID_DATE_AS_YYYYMMDD','MAXIMUM_TEMPERATURE_C___FLOAT_VALUE_TO_NEAREST_HUNDREDTHS_PLACE','AVERAGE_RELATIVE_HUMIDITY_____FLOAT_VALUE_TO_NEAREST_HUNDREDTHS_PLACE']),
}

def process(args):
    key,path=args
    columns=DATASETS[key][1]; rows=matched=geo_valid=0; totals=Counter(); months=Counter(); categories=Counter(); dates=[]; uhi=Counter(); cells=Counter(); stations=Counter(); temps=[]
    for frame in pd.read_csv(path,usecols=columns,dtype=str,chunksize=200000,keep_default_na=False):
        rows+=len(frame)
        if key=='weather':
            f=frame[frame[columns[0]].str.upper().isin(['KTEB','KEWR','KNYC','KLGA','KJFK','KCDW','KLDJ'])]
        else:f=frame[frame.MARKET.str.replace(' ','',regex=False).str.lower().eq('newyork/newjersey')]
        matched+=len(f)
        if f.empty:continue
        if key in ('poi','uhi'):
            lat=pd.to_numeric(f.LATITUDE,errors='coerce');lon=pd.to_numeric(f.LONGITUDE,errors='coerce')
            valid=lat.between(40.45,41.2)&lon.between(-74.5,-73.5);geo_valid+=int(valid.sum())
            g=f.loc[valid].copy();g['cell']=((lat[valid]*20).round()/20).astype(str)+','+((lon[valid]*20).round()/20).astype(str)
            cells.update(g['cell'].value_counts().to_dict())
            if key=='poi':
                totals['store_id_present']+=int(f.STORE_ID.ne('').sum());categories.update(f.TOP_CATEGORY.value_counts().to_dict())
            else:uhi.update(pd.to_numeric(g.UHI,errors='coerce').dropna().value_counts().to_dict())
        elif key=='weather':
            stations.update(f[columns[0]].value_counts().to_dict());d=f[columns[1]].str[:10];dates.extend([d.min(),d.max()])
            s=f[d.str[5:7].isin(['06','07'])]
            t=pd.to_numeric(s[columns[2]],errors='coerce');temps.extend(t[t.between(-20,60)].tolist())
        else:
            field={'visits':'LOCAL_DATE','spend':'SPEND_DATE_RANGE_START','daily_spend':'TRANS_DATE'}[key]
            d=f[field].str[:10];dates.extend([d.min(),d.max()]);months.update(d.str[:7].value_counts().to_dict())
            nums={'visits':['DAILY_VISITS'],'spend':['RAW_NUM_CUSTOMERS','RAW_TOTAL_SPEND'],'daily_spend':['SPEND_AMOUNT','TRANS_COUNT']}[key]
            for col in nums:totals[col]+=float(pd.to_numeric(f[col],errors='coerce').fillna(0).clip(lower=0).sum())
            if key=='visits':
                values=pd.to_numeric(f.DAILY_VISITS,errors='coerce').fillna(0).clip(lower=0)
                for m,v in values.groupby(d.str[:7]).sum().items():totals['month_visits:'+m]+=float(v)
    return {'key':key,'file':Path(path).name,'rows':rows,'matched':matched,'geo_valid':geo_valid,'totals':dict(totals),'months':dict(months),'categories':dict(categories),'cells':dict(cells),'uhi':dict(uhi),'stations':dict(stations),'temps':temps,'date_min':min(dates) if dates else None,'date_max':max(dates) if dates else None}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);ap.add_argument('--output',type=Path,default=Path('data/nynj/rice_aggregate.json'));ap.add_argument('--workers',type=int,default=3);args=ap.parse_args()
    jobs=[(key,str(p)) for key,(folder,_) in DATASETS.items() for p in sorted((args.root/folder).glob('*.csv.gz'))]
    by={k:[] for k in DATASETS};started=time.time()
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i,r in enumerate(pool.map(process,jobs),1):
            by[r['key']].append(r);print(i,len(jobs),r['key'],r['file'],r['rows'],r['matched'],flush=True)
    result={'schema_version':1,'market':'New York/New Jersey','coverage':'Full scan of all available compressed shards; no row cap. Market labels and coordinates are organizer-transformed.','data_class':'Organizer sample data','limitations':['Not actual urban conditions or a FIFA visitor OD matrix.','Visitation totals are perturbed visits, not unique people.','Spatial cells are approximately 5 km and jittered; they are not street-level evidence.','UHI is retained as a 1–11 sample index, never converted to degrees.','Weather values are transformed historical observations, not a 2026 forecast.'],'datasets':{}}
    for key,items in by.items():
        d={'files_scanned':len(items),'rows_read':sum(r['rows'] for r in items),'rows_matched_market_or_station':sum(r['matched'] for r in items),'rows_within_nynj_bbox':sum(r['geo_valid'] for r in items),'date_min':min([r['date_min'] for r in items if r['date_min']] or ['']),'date_max':max([r['date_max'] for r in items if r['date_max']] or [''])}
        for field in ['totals','months','categories','cells','uhi','stations']:
            c=Counter()
            for r in items:c.update(r[field])
            d[field]=dict(sorted(c.items()))
        ts=[t for r in items for t in r['temps']]
        if ts:d['summer_max_temperature_c_quantiles']={str(q):round(float(pd.Series(ts).quantile(q)),2) for q in [.5,.9,.95]}
        d['shards']=[{k:r[k] for k in ['file','rows','matched']} for r in items]
        result['datasets'][key]=d
    result['runtime_seconds']=round(time.time()-started);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print('WROTE',args.output,flush=True)

if __name__=='__main__':main()
