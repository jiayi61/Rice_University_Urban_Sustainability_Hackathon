(()=>{'use strict';
 const $=id=>document.getElementById(id),fmt=n=>new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(n),money=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(n),short=n=>'$'+Math.round(n/1000)+'k',esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let context;
 const labels={rail:'Rail / NJ TRANSIT',shuttle:'Host shuttles',rideshare:'Rideshare',walk:'Walking',park:'Park & ride',normal:'Normal',rail_outage:'Rail disruption',heat_wave:'Heat wave',demand_surge:'Demand +25%'};
 const badge=(name,type='modeled')=>`<span class="pill ${type}">${esc(name)}</span>`;
 /* === SHARED MAP ENCODING === */
 // Standard OSM tiles, muted in CSS (.leaflet-tile-pane) so the model overlays stay legible on top.
 const BASEMAP='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',BASEMAP_ATTR='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
 const MODE_COLOR={rail:'#176d60',shuttle:'#356899',rideshare:'#c45b2d',walk:'#7a5ea8',park:'#6b7a86'};
 const PRESSURE_RAMP=[[.60,'#2f8f5b'],[.85,'#8ea832'],[1.00,'#d9a021'],[1.15,'#d5762c'],[Infinity,'#b23b2b']];
 const WAIT_RAMP=[[30,'#2f8f5b'],[60,'#8ea832'],[90,'#d9a021'],[120,'#d5762c'],[Infinity,'#b23b2b']];
 const ramp=(stops,value)=>(stops.find(([edge])=>value<edge)||stops[stops.length-1])[1];
 const pressureColor=v=>ramp(PRESSURE_RAMP,v),waitColor=v=>ramp(WAIT_RAMP,v);
 const deltaColor=d=>d<-.015?'#176d60':d>.015?'#b23b2b':'#a8b3ac';
 const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
 const signed=(v,unit='',digits=0)=>`${v>0?'+':v<0?'−':'±'}${Math.abs(v).toFixed(digits)}${unit}`;
 // Quadratic curve between two lat/lon points so overlapping corridors stay separable.
 function arc(from,to,bend=.17,steps=26){const[y1,x1]=from,[y2,x2]=to,k=Math.cos(y1*Math.PI/180)||1;
  const cx=(x1+x2)/2-(y2-y1)*bend/k,cy=(y1+y2)/2+(x2-x1)*bend*k,out=[];
  for(let i=0;i<=steps;i++){const t=i/steps,u=1-t;out.push([u*u*y1+2*u*t*cy+t*t*y2,u*u*x1+2*u*t*cx+t*t*x2]);}
  return out;}
 const rampSwatch=stops=>`<div class="ramp">${stops.map(([,color])=>`<i style="background:${color}"></i>`).join('')}</div>`;
 const legendBox=(title,body)=>`<h4>${title}</h4>${body}`;
 function bindLayerChips(containerId,onToggle){const box=$(containerId);if(!box)return;
  for(const label of box.querySelectorAll('label[data-layer]')){const input=label.querySelector('input');
   input.addEventListener('change',()=>{label.classList.toggle('on',input.checked);onToggle(label.dataset.layer,input.checked);});}}
 function applyLayerChips(containerId,map,groups){const box=$(containerId);if(!box||!map)return;
  for(const label of box.querySelectorAll('label[data-layer]')){const group=groups[label.dataset.layer];if(!group)continue;
   const on=label.querySelector('input').checked;label.classList.toggle('on',on);
   if(on&&!map.hasLayer(group))group.addTo(map);else if(!on&&map.hasLayer(group))map.removeLayer(group);}}
 const table=(heads,rows)=>`<table><thead><tr>${heads.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(x=>`<td>${x}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
 const modeTotal=r=>r.rail+r.shuttle+r.rideshare;
 function chartAxes(xMax,yMax,xLabel,yLabel){let s='';for(let i=0;i<=4;i++){let y=210-i*45;s+=`<line x1="55" y1="${y}" x2="580" y2="${y}" stroke="#e6ebe5"/><text x="45" y="${y+4}" text-anchor="end">${fmt(yMax*i/4)}</text>`;}s+=`<text x="55" y="17">${yLabel}</text><text x="315" y="252" text-anchor="middle">${xLabel}</text>`;for(let i=0;i<=4;i++)s+=`<text x="${55+i*131.25}" y="232" text-anchor="middle">${fmt(xMax*i/4)}</text>`;return s;}
 let houstonMap,houstonGroups={},houstonView='plan';
 function houstonScenarios(){const h=context.houston;return{base:h.scenarios.find(x=>x.name==='Baseline'),plan:h.scenarios.find(x=>x.name==='Mixed Optimized')};}
 function houstonAssets(scenario){const out={};
  for(const r of scenario.resources||[]){const key=r.candidate_id;
   const entry=out[key]||(out[key]={name:r.name,lat:r.lat,lon:r.lon,category:r.category,units:{},total:0,rationale:r.rationale});
   entry.units[r.resource_type]=(entry.units[r.resource_type]||0)+r.units;entry.total+=r.units;}
  return out;}
 function houstonModeRing(zone){const total=Object.values(zone.mode_visitors).reduce((s,v)=>s+v,0)||1;let at=0;
  const stops=Object.entries(zone.mode_visitors).filter(([,v])=>v>0).map(([mode,v])=>{const from=at/total*360;at+=v;return `${MODE_COLOR[mode]} ${from.toFixed(1)}deg ${(at/total*360).toFixed(1)}deg`;});
  return stops.length?stops.join(','):'#b9c2bb 0deg 360deg';}
 function houstonModeText(zone,other){return Object.keys(MODE_COLOR).filter(m=>zone.mode_visitors[m]||other?.mode_visitors[m])
  .map(m=>`<em><i style="display:inline-block;width:8px;height:3px;background:${MODE_COLOR[m]};vertical-align:middle;margin-right:5px"></i>${labels[m]||m}</em><b>${fmt(zone.mode_visitors[m]||0)}${other?` <span class="tip-delta ${(zone.mode_visitors[m]||0)>=(other.mode_visitors[m]||0)?'better':'worse'}">${signed((zone.mode_visitors[m]||0)-(other.mode_visitors[m]||0))}</span>`:''}</b>`).join('');}
 // Most demand sits within a few km of NRG; the airport cohort is 34 km out and would flatten the last mile.
 const KM=(a,b)=>Math.hypot((a[0]-b[0])*111,(a[1]-b[1])*97);
 function fitHouston(scope){if(!houstonMap)return;
  const{plan}=houstonScenarios(),stadium=[context.houston.metadata.stadium.lat,context.houston.metadata.stadium.lon];
  const points=scope==='approach'
   ?Object.values(houstonAssets(plan)).map(asset=>[asset.lat,asset.lon]).filter(p=>KM(p,stadium)<=4)// the off-site fan-zone asset would stretch this view back to the whole city
   :plan.zones.map(z=>[z.lat,z.lon]).filter(p=>scope==='region'||KM(p,stadium)<=18);
  houstonMap.fitBounds([stadium,...points],{padding:scope==='approach'?[70,70]:[46,46]});
  for(const[id,name]of[['houstonZoomApproach','approach'],['houstonZoomCore','core'],['houstonZoomRegion','region']])$(id).classList.toggle('active',scope===name);}
 function renderHouston(view){
  if(view)houstonView=view;
  const{base,plan}=houstonScenarios(),shown=houstonView==='baseline'?base:plan,other=houstonView==='baseline'?plan:base;
  for(const[id,name]of[['houstonBefore','baseline'],['houstonAfter','plan'],['houstonDelta','delta']])$(id)&&$(id).classList.toggle('active',houstonView===name);
  const metrics=[['Modelled visitors',fmt(base.kpis.total_visitors),'Synthetic event demand'],['Peak route pressure',`${base.kpis.max_route_pressure.toFixed(2)} → ${plan.kpis.max_route_pressure.toFixed(2)}×`,'Demand relative to assumed capacity'],['Transit + shuttle share',`${base.kpis.transit_shuttle_share_pct} → ${plan.kpis.transit_shuttle_share_pct}%`,'Modelled mode mix'],['Routes over capacity',`${base.kpis.over_capacity_route_count} → ${plan.kpis.over_capacity_route_count}`,'Baseline → mixed plan']];
  $('houstonKpis').innerHTML=metrics.map(([a,b,c])=>`<article class="kpi"><span class="label">${a}</span><strong>${b}</strong><small>${c}</small><div style="margin-top:10px">${badge('Houston model projection')}</div></article>`).join('');
  if(!window.L){$('houstonMap').textContent='Map unavailable. The Houston comparison remains available above.';return;}
  if(!houstonMap){houstonMap=L.map('houstonMap',{scrollWheelZoom:false});
   L.tileLayer(BASEMAP,{attribution:BASEMAP_ATTR,maxZoom:19}).addTo(houstonMap);
   houstonGroups={rail:L.layerGroup(),shuttle:L.layerGroup(),rideshare:L.layerGroup(),park:L.layerGroup(),walk:L.layerGroup(),zones:L.layerGroup(),heat:L.layerGroup(),assets:L.layerGroup()};
   bindLayerChips('houstonLayers',()=>applyLayerChips('houstonLayers',houstonMap,houstonGroups));
   for(const[id,scope]of[['houstonZoomApproach','approach'],['houstonZoomCore','core'],['houstonZoomRegion','region']])$(id).addEventListener('click',()=>fitHouston(scope));
   fitHouston('core');}
  for(const group of Object.values(houstonGroups))group.clearLayers();
  const stadium=[context.houston.metadata.stadium.lat,context.houston.metadata.stadium.lon];
  const byId=Object.fromEntries(other.routes.map(r=>[r.route_id,r]));
  const maxVisitors=Math.max(...base.routes.map(r=>r.visitors),1);
  /* One curved corridor per arrival zone and mode, coloured by modelled pressure */
  for(const route of shown.routes){
   const twin=byId[route.route_id],group=houstonGroups[route.mode];if(!group)continue;
   const planRoute=houstonView==='baseline'?twin:route,baseRoute=houstonView==='baseline'?route:twin;
   const deltaPressure=(planRoute?.pressure??0)-(baseRoute?.pressure??0);
   // Each mode fans out on its own curve so corridors sharing an origin stay separable.
   const bend=({rail:.04,shuttle:.26,rideshare:-.24,park:.46,walk:-.44})[route.mode]??.15;
   const geometry=arc([route.lat1,route.lon1],stadium,bend);
   const weight=1.4+6.4*Math.sqrt(route.visitors/maxVisitors);
   const color=houstonView==='delta'?deltaColor(deltaPressure):pressureColor(route.pressure);
   const tip=`<span class="tip-title">${esc(route.zone_name)} → NRG Stadium</span><div class="tip-grid">`
    +`<em>Mode</em><b style="color:${MODE_COLOR[route.mode]}">${esc(labels[route.mode]||route.mode)}</b>`
    +`<em>Modelled visitors</em><b>${fmt(route.visitors)}${twin?` <span class="tip-delta ${route.visitors>=twin.visitors?'better':'worse'}">${signed(route.visitors-twin.visitors)}</span>`:''}</b>`
    +`<em>Route pressure</em><b style="color:${pressureColor(route.pressure)}">${route.pressure.toFixed(2)}×${baseRoute&&planRoute?` <span class="tip-delta ${deltaPressure<=0?'better':'worse'}">${signed(deltaPressure,'×',2)}</span>`:''}</b>`
    +`<em>Peak demand</em><b>${fmt(route.peak_visitors_per_hour)}/h vs ${fmt(route.capacity_per_hour)}/h capacity</b>`
    +`<em>Travel time</em><b>${fmt(route.adjusted_minutes)} min · ${route.distance_km} km</b>`
    +`<em>First/last-mile gap</em><b>${fmt(route.gap_m)} m</b>`
    +`</div><p class="fine" style="margin:6px 0 0">Curved schematic link, not a verified road path.</p>`;
   // Baseline width is drawn first as a grey shadow; corridors are never over-painted by a later route.
   if(houstonView!=='baseline'&&baseRoute&&baseRoute.visitors>route.visitors)
    L.polyline(geometry,{color:'#9aa49d',weight:1.4+6.4*Math.sqrt(baseRoute.visitors/maxVisitors),opacity:.24,lineCap:'round'}).addTo(group);
   L.polyline(geometry,{color,weight,opacity:.95,lineCap:'round',dashArray:'10 14',className:route.pressure>1?'flow':'flow flow-slow'}).bindTooltip(tip,{sticky:true}).addTo(group);}
  /* Arrival zones: ring shows the modelled mode split, size shows demand */
  for(const zone of shown.zones){
   const twin=other.zones.find(z=>z.zone_id===zone.zone_id);
   const size=Math.round(13+Math.sqrt(zone.visitors)/7.5);
   L.marker([zone.lat,zone.lon],{icon:L.divIcon({className:'',html:`<div class="mode-ring" style="width:${size}px;height:${size}px;background:conic-gradient(${houstonModeRing(zone)})"><span>${size>24?Math.round(zone.visitors/1000)+'k':''}</span></div>`,iconSize:[size,size],iconAnchor:[size/2,size/2]}),zIndexOffset:400})
    .bindTooltip(`<span class="tip-title">${esc(zone.name)}</span><div class="tip-grid"><em>Modelled visitors</em><b>${fmt(zone.visitors)}</b><em>Average trip</em><b>${fmt(zone.avg_minutes)} min</b>${houstonModeText(zone,houstonView==='baseline'?null:twin)}</div><p class="fine" style="margin:6px 0 0">${esc(zone.notes||'')}</p>`,{direction:'top'}).addTo(houstonGroups.zones);
   L.circle([zone.lat,zone.lon],{radius:900+Math.sqrt(zone.heat_exposure)*15*zone.vulnerability,weight:1,color:'#c45b2d',opacity:.45,fillColor:'#e07a3c',fillOpacity:.15+zone.vulnerability*.2,className:'breathe'})
    .bindTooltip(`<span class="tip-title">${esc(zone.name)} · heat exposure</span>Relative exposure index ${fmt(zone.heat_exposure)} · vulnerability ${zone.vulnerability.toFixed(2)}<br><em>Relative scenario weighting, not a measured temperature.</em>`).addTo(houstonGroups.heat);}
  /* Heat-safety assets: literally what the plan buys and where it lands */
  const shownAssets=houstonAssets(shown),otherAssets=houstonAssets(other);
  for(const[id,asset]of Object.entries(shownAssets)){const twin=otherAssets[id],diff=asset.total-(twin?.total||0);
   const size=Math.round(18+Math.min(12,asset.total*1.6));
   L.marker([asset.lat,asset.lon],{icon:L.divIcon({className:'',html:`<div class="asset-pin asset${houstonView!=='baseline'&&diff>0?' up':''}" style="width:${size}px;height:${size}px">${asset.total}</div>`,iconSize:[size,size],iconAnchor:[size/2,size/2]}),zIndexOffset:600})
    .bindTooltip(`<span class="tip-title">${esc(asset.name)}</span><div class="tip-grid"><em>Site type</em><b>${esc(String(asset.category).replace(/_/g,' '))}</b>${Object.entries(asset.units).map(([type,units])=>`<em>${type}</em><b>${units} unit${units===1?'':'s'}${twin?` <span class="tip-delta ${units>=(twin.units[type]||0)?'better':'worse'}">${signed(units-(twin.units[type]||0))}</span>`:''}</b>`).join('')}</div><p class="fine" style="margin:6px 0 0">${esc(asset.rationale||'')}</p>`,{direction:'top'}).addTo(houstonGroups.assets);}
  L.marker(stadium,{icon:L.divIcon({className:'',html:'<div class="venue-pin">◆</div>',iconSize:[34,34],iconAnchor:[17,17]}),zIndexOffset:900})
   .bindTooltip(`<span class="tip-title">NRG Stadium</span>${fmt(context.houston.metadata.total_visitors)} modelled arrivals`,{direction:'top'}).addTo(houstonGroups.zones);
  renderHoustonReadout(base,plan);renderHoustonLegend();applyLayerChips('houstonLayers',houstonMap,houstonGroups);
 }
 function renderHoustonReadout(base,plan){
  const shown=houstonView==='baseline'?base:plan,over=shown.kpis.over_capacity_route_count;
  const rows=Object.entries(plan.mode_totals).map(([mode,value])=>{const from=base.mode_totals[mode],to=value,now=houstonView==='baseline'?from:to,diff=to-from;
   return `<div><em><i style="display:inline-block;width:8px;height:3px;background:${MODE_COLOR[mode]};vertical-align:middle;margin-right:5px"></i>${labels[mode]||mode}</em>`
    +(houstonView==='baseline'?`<b>${fmt(now)}</b>`:`<b class="tip-delta ${diff>=0===(mode==='rail'||mode==='shuttle'||mode==='walk')?'better':'worse'}">${fmt(now)} <span style="font-weight:400;color:#6a7a72">(${signed(diff)})</span></b>`)+'</div>';}).join('');
  const headline=houstonView==='delta'
   ?`<b style="font-size:17px">${base.kpis.max_route_pressure.toFixed(2)}× → ${plan.kpis.max_route_pressure.toFixed(2)}×</b>`
   :`<b>${shown.kpis.max_route_pressure.toFixed(2)}×</b>`;
  const note=houstonView==='delta'
   ?`peak route pressure · ${base.kpis.over_capacity_route_count} → ${plan.kpis.over_capacity_route_count} routes over capacity`
   :`peak route pressure · ${over} route${over===1?'':'s'} over capacity`;
  $('houstonReadout').innerHTML=`<span>${houstonView==='baseline'?'Before · today’s matchday':houstonView==='delta'?'After vs before':'After · mixed plan'}</span>${headline}<span style="letter-spacing:.2px;text-transform:none;font-size:9.5px;margin:2px 0 0">${note}</span><div class="readout-rows">${rows}</div>`;
 }
 function renderHoustonLegend(){
  const modes=`<div class="legend-keys">${Object.entries(MODE_COLOR).map(([mode,color])=>`<span><i style="background:${color}"></i>${labels[mode]||mode}</span>`).join('')}<span><i class="dot" style="background:#b5377e"></i>Heat-safety asset · number = units</span></div>`;
  $('houstonLegend').innerHTML=houstonView==='delta'
   ?legendBox('Plan vs baseline pressure',`<div class="ramp"><i style="background:#176d60"></i><i style="background:#a8b3ac"></i><i style="background:#b23b2b"></i></div><div class="ramp-labels"><b>Relieved</b><b>Unchanged</b><b>Worse</b></div>${modes}<p class="legend-note">Corridor width still shows modelled demand; the grey shadow is the baseline width where the plan moved people off that corridor.</p>`)
   :legendBox('Modelled route pressure',`${rampSwatch(PRESSURE_RAMP)}<div class="ramp-labels"><b>0.6×</b><b>0.85</b><b>1.0</b><b>1.15×+</b></div><div class="ramp-labels" style="margin-top:2px"><b>Demand ÷ assumed capacity</b></div>${modes}<p class="legend-note">Ring segments show each zone’s modelled mode split; width shows demand. Flow animation marks direction only.</p>`);
 }
 let liveMap, livePayload;
 function setupLivePlanner(){
  const form=$('eventRequest'), submit=form.querySelector('button[type="submit"]')||form.querySelector('button');
  submit.textContent='Build my event plan ↗';
  const note=form.querySelector('.request-bottom span');if(note)note.textContent='Public place data + reproducible scenario calculation';
  const fields=document.createElement('div');fields.className='live-fields';
  fields.innerHTML=`<p id="apiState" role="status">Checking API configuration…</p><p>Enter city and venue below to use structured input without AI. Leave city blank to let the configured API interpret your brief.</p>
  <div class="live-inputs"><label>City / country<input id="liveCity" maxlength="200" placeholder="New York, USA"></label><label>Venue<input id="liveVenue" maxlength="200" placeholder="MetLife Stadium"></label><label>Event date<input id="liveDate" type="text" inputmode="numeric" autocomplete="off" pattern="[0-9]{4}-[0-9]{2}-[0-9]{2}" placeholder="YYYY-MM-DD" title="Use YYYY-MM-DD, for example 2027-06-08"></label><label>Attendance<input id="liveAttendance" type="number" min="500" max="500000" placeholder="50000"></label><label>Budget (USD)<input id="liveBudget" type="number" min="0" max="100000000" placeholder="500000"></label></div>
  <details><summary>Review operating assumptions before running</summary><p>These are editable planning assumptions, not measured local capacity. The model simulates the selected share of attendees using shared transport and added shuttles.</p><div class="live-inputs">
  <label>Modeled share of attendees (%)<input id="liveCohort" type="number" min="1" max="100" value="40"></label>
  <label>Existing service (people/hour)<input id="liveService" type="number" min="100" max="200000" value="12000"></label>
  <label>Maximum extra buses<input id="liveFleet" type="number" min="0" max="500" value="100"></label>
  <label>Charter cost / bus (USD)<input id="liveCost" type="number" min="100" max="100000" value="2500"></label></div></details>`;
  form.insertBefore(fields,form.querySelector('.request-bottom'));
  const section=document.createElement('section');section.id='liveResult';section.className='card';section.hidden=true;section.setAttribute('aria-live','polite');$('new-event').after(section);
  fetch('/api/config').then(r=>{if(!r.ok)throw Error();return r.json();}).then(c=>{$('apiState').textContent=c.configured?'API configured · '+c.model:'API key not configured · fill in city and venue to run, or set OPENAI_API_KEY in .env.';}).catch(()=>{$('apiState').textContent='Start the Python server to enable live planning.';});
 }
 function renderLive(p){
  livePayload=p;const s=p.simulation,b=s.baseline,r=s.recommended;
  if(liveMap){liveMap.remove();liveMap=null;}
  const section=$('liveResult');section.hidden=false;
  const cash=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(v);
  const maxMinute=Math.max(b.clearance_minutes,r.clearance_minutes,120),maxPeople=b.cohort;
  const line=(v,color)=>`<polyline fill="none" stroke="${color}" stroke-width="3" points="${v.timeline.filter(t=>t.minute<=maxMinute).map(t=>`${55+t.minute/maxMinute*525},${210-t.remaining/maxPeople*180}`).join(' ')}"/>`;
  section.innerHTML=`<p class="eyebrow">03 / YOUR EVENT · LIVE CALCULATION</p><h2 tabindex="-1" id="liveTitle">${esc(p.venue.city)} · ${esc(p.venue.name)}</h2><p>${esc(p.event.name)} · ${esc(p.event.date)} · ${fmt(p.event.attendance)} attendees</p><p class="fine">${esc(p.brief.parser)} · ${esc(p.brief.generated_at)}. Scenario projection; local operating assumptions require verification.</p>
   <div class="kpis">${[['Modeled transport cohort',fmt(b.cohort)+' people'],['Queue clearance',b.clearance_minutes+' → '+r.clearance_minutes+' min'],['Served within 2 hours',fmt(b.served_120)+' → '+fmt(r.served_120)],['Extra fleet / cost',r.fleet+' buses / '+cash(r.cost_usd)]].map(([a,v])=>`<article class="kpi"><span>${esc(a)}</span><strong>${esc(v)}</strong></article>`).join('')}</div>
   <p>Evaluated ${s.evaluated_portfolios} fleet sizes. Selected the lowest queue burden within ${s.budget_usd===null?'the fleet limit (no budget supplied)':cash(s.budget_usd)}. Cost includes 18% delivery allowance.</p>
   <div id="liveMap" style="height:420px"></div><p class="fine">Public road routes for proposed shuttles. Straight lines indicate unavailable road routing. Catchment demand shares remain assumptions.</p>
   <svg viewBox="0 0 600 255" role="img" aria-label="Baseline and planned passengers remaining">${chartAxes(maxMinute,maxPeople,'Minutes after event end','People remaining')}${line(b,'#999')}${line(r,'#176d60')}</svg><p>Grey: baseline · Green: selected fleet</p>
   <div class="table-wrap">${table(['Catchment','People','Extra buses','Cycle (min)','Clearance (min)','Route basis'],r.routes.map(v=>[esc(v.name),fmt(v.people),v.buses,v.cycle_minutes,v.clearance_minutes,esc(v.source)]))}</div>
   <h3>Sensitivity · demand and service ±15%</h3><div class="table-wrap">${table(['Demand','Service','Baseline (min)','Plan (min)'],s.sensitivity.map(v=>[v.demand_factor+'×',v.service_factor+'×',v.baseline,v.plan]))}</div>
   <h3>Evidence and assumptions</h3><div class="table-wrap">${table(['Input','Value'],Object.entries(s.parameters).map(([k,v])=>[esc(k.replaceAll('_',' ')),esc(v)]))}</div>
   ${p.brief.assumptions.map(a=>`<p class="fine"><b>${esc(a.field)}: ${esc(a.value)}</b> · ${esc(a.basis)}</p>`).join('')}
   ${Object.entries(p.data_freshness).map(([k,v])=>`<p class="fine"><b>${esc(k)}:</b> ${esc(v)}</p>`).join('')}
   <ul>${s.limitations.map(v=>`<li>${esc(v)}</li>`).join('')}</ul><button id="liveDownload" class="primary">Download decision report (PDF) ↓</button>`;
  $('resultsNav').hidden=false;$('resultsNav').href='#liveResult';$('resultsNav').textContent='03 Your results';
  if(window.L){liveMap=L.map('liveMap',{scrollWheelZoom:false});L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors'}).addTo(liveMap);
   const points=[[p.venue.lat,p.venue.lon]];L.marker(points[0]).bindTooltip(esc(p.venue.name)).addTo(liveMap);
   for(const route of r.routes){points.push(...route.geometry);L.polyline(route.geometry,{color:'#176d60',weight:3,dashArray:route.source.includes('screening')?'5 5':null}).bindTooltip(esc(route.name)+' · '+route.buses+' proposed buses').addTo(liveMap);}liveMap.fitBounds(points,{padding:[25,25]});}
  $('liveDownload').addEventListener('click',downloadLivePdf);
  $('liveTitle').focus({preventScroll:true});section.scrollIntoView({behavior:'smooth'});
 }
 async function downloadLivePdf(){
  const button=$('liveDownload');button.disabled=true;button.textContent='Preparing your PDF…';
  try{const response=await fetch('/api/v3/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({report_id:livePayload.report_id})});
   if(!response.ok){const error=await response.json();throw Error(error.detail||'PDF export failed.');}
   const blob=await response.blob();if(!blob.type.includes('application/pdf'))throw Error('The server did not return a PDF.');
   const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='EventFlow-decision-report.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){const message=document.createElement('p');message.setAttribute('role','alert');message.textContent=e.message;button.after(message);}
  finally{button.disabled=false;button.textContent='Download decision report (PDF) ↓';}
 }
 async function submitLiveEvent(event){
  event.preventDefault();const form=$('eventRequest'),button=form.querySelector('button[type="submit"]')||form.querySelector('button');
  const inputs={};for(const[id,key]of[['liveCity','city_query'],['liveVenue','venue_query'],['liveDate','date']])if($(id).value.trim())inputs[key]=$(id).value.trim();
  for(const[id,key]of[['liveAttendance','attendance'],['liveBudget','budget_usd'],['liveCohort','cohort_pct'],['liveService','baseline_service_pph'],['liveFleet','fleet_limit'],['liveCost','bus_cost_usd']])if($(id).value!=='')inputs[key]=Number($(id).value);
  button.disabled=true;button.textContent='Resolving place, fetching routes and calculating…';$('requestError').hidden=true;$('resultsNav').hidden=true;$('liveResult').hidden=true;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),150000);
  try{const response=await fetch('/api/v3/brief',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:$('eventBrief').value,online:true,inputs}),signal:controller.signal});const p=await response.json();if(!response.ok)throw Error(typeof p.detail==='string'?p.detail:'Check the input fields and retry.');renderLive(p);}
  catch(e){$('requestError').textContent=e.name==='AbortError'?'Public data services took too long. Please retry.':e.message;$('requestError').hidden=false;}
  finally{clearTimeout(timer);button.disabled=false;button.textContent='Build my event plan ↗';}
 }
 /* === SCROLL REVEALS: VISUAL PRESENTATION ONLY === */
 if('IntersectionObserver' in window&&!matchMedia('(prefers-reduced-motion: reduce)').matches){const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){entry.target.classList.add('entered');observer.unobserve(entry.target);}},{threshold:.08});for(const element of document.querySelectorAll('.map-layout,.request-panel,.section-title,.two-col'))observer.observe(element);}
 async function init(){setupLivePlanner();$('eventRequest').addEventListener('submit',submitLiveEvent);
 try{const response=await fetch('/competition-data.json');if(!response.ok)throw Error('The Houston introduction could not load.');context=await response.json();renderHouston('plan');
 for(const[id,view]of[['houstonBefore','baseline'],['houstonAfter','plan'],['houstonDelta','delta']])$(id).addEventListener('click',()=>renderHouston(view));
 }catch(e){$('error').hidden=false;$('error').textContent=e.message;}}

 init();
})();
