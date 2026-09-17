(()=>{'use strict';
 const $=id=>document.getElementById(id),fmt=n=>new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(n),money=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(n),short=n=>'$'+Math.round(n/1000)+'k',esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let context,scenarios,current,map,riceGroup,nyGroups={},nyView='plan',egressIndex=0,egressTimer=null,planToken=0;
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
 function renderCharts(){const p=current,front=p.frontier,xMax=Math.max(p.inputs.budget,...front.map(x=>x.cost))/1000,yMax=Math.max(1,...front.map(x=>x.score))*1.12;let svg=chartAxes(xMax,yMax,'Incremental cost ($ thousands)','Policy-weighted score');const xy=x=>[55+x.cost/1000/xMax*525,210-x.score/yMax*180];svg+=`<polyline points="${front.map(x=>xy(x).join(',')).join(' ')}" fill="none" stroke="#176d60" stroke-width="2"/>`;let bx=55+p.inputs.budget/1000/xMax*525;svg+=`<line x1="${bx}" y1="28" x2="${bx}" y2="210" stroke="#c45b2d" stroke-dasharray="5 5"/><text x="${Math.min(515,bx+5)}" y="35">Budget</text>`;for(const point of front){let[x,y]=xy(point),sel=point.cost===p.recommended.cost;svg+=`<circle cx="${x}" cy="${y}" r="${sel?6:3.5}" fill="${sel?'#c45b2d':point.cost>p.inputs.budget?'#bec8c1':'#176d60'}"><title>${money(point.cost)}; score ${point.score.toFixed(1)}; ${point.ids.join(', ')||'baseline'}</title></circle>`;}$('pareto').innerHTML=svg;
 const nearby=front.filter(x=>x.cost<=p.inputs.budget).slice(-3);$('frontierTable').innerHTML=table(['Cost','Policy score','Clears in'],nearby.map(x=>[short(x.cost),x.score.toFixed(1),fmt(x.clearance_minutes)+' min']));
 const xmax=480,ymax=p.baseline.cohort;let q=chartAxes(xmax,ymax,'Minutes after concert end','Modelled people remaining');for(const[key,color]of[['baseline','#9b9f9a'],['recommended','#176d60']]){let points=p[key].timeline.map(r=>`${55+r.minute/xmax*525},${210-modeTotal(r)/ymax*180}`);q+=`<polyline points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="${key==='baseline'?2:3}" ${key==='baseline'?'stroke-dasharray="5 4"':''}/>`;}$('queueChart').innerHTML=q;
 }
 /* === NEW YORK / NEW JERSEY EGRESS MAP === */
 const NY_MODE_ANCHOR={rail:'secaucus',shuttle:'penn',rideshare:'racetrack'};
 const NY_ACTION_PLACE={shuttle:{anchor:'secaucus',mode:'shuttle'},bus_priority:{anchor:'stadium',mode:'shuttle'},rail_overlay:{anchor:'secaucus',mode:'rail'},curb:{anchor:'racetrack',mode:'rideshare'},shade:{anchor:'american_dream',mode:null},accessible:{anchor:'stadium',mode:'rail'},wayfinding:{anchor:'penn',mode:'rail'}};
 const egressPoint=(plan,index)=>plan.timeline[Math.min(index,plan.timeline.length-1)];
 function nyCorridor(mode){const a=Object.fromEntries(context.map.anchors.map(x=>[x.id,[x.lat,x.lon]]));
  const road=id=>{const r=(context.map.roads||[]).find(x=>x.id===id);return r?r.geometry.slice().reverse():null;};
  if(mode==='rail')return{geometry:[a.stadium,a.secaucus,a.penn].filter(Boolean),basis:'Schematic transfer pathway — not a mapped rail alignment'};
  if(mode==='shuttle')return{geometry:road('penn')||[a.stadium,a.penn],basis:'OSRM driving route over OSM roads — not an event detour'};
  return{geometry:road('racetrack')||[a.stadium,a.racetrack],basis:'OSRM driving route to the Racetrack loading area'};}
 function nyCohortState(plan,index,mode){const remaining=egressPoint(plan,index)[mode],rate=plan.rates[mode]||1;
  return{remaining,rate,waitMinutes:remaining/rate*60,start:plan.timeline[0][mode]};}
 function renderMap(){
  for(const[id,view]of[['showBaseline','baseline'],['showPlan','plan'],['showDelta','delta']])$(id)&&$(id).classList.toggle('active',nyView===view);
  if(!map)return;
  for(const group of Object.values(nyGroups))group.clearLayers();
  const a=Object.fromEntries(context.map.anchors.map(x=>[x.id,x]));
  const point=egressPoint(current.recommended,egressIndex),minute=point.minute;
  const peak=Math.max(...['rail','shuttle','rideshare'].map(m=>current.baseline.timeline[0][m]));
  /* Road and subway context */
  for(const r of context.map.roads||[])L.polyline(r.geometry,{color:'#8b9690',weight:r.id==='penn'?2.2:1.4,opacity:.55})
   .bindTooltip(`<span class="tip-title">${esc(r.name)} road context</span>${r.distance_km} km · ${fmt(r.freeflow_minutes)} min free flow<br><em>${esc(r.basis||'Not an event detour')}</em>`).addTo(nyGroups.roads);
  for(const line of context.map.subway.routes||[])L.polyline(line.geometry,{weight:1.3,color:line.color,opacity:.4})
   .bindTooltip(`MTA ${esc(line.name)} · current regular GTFS, context only`).addTo(nyGroups.subway);
  /* One corridor per modelled egress cohort, styled by the queue still waiting at this minute */
  for(const mode of ['rail','shuttle','rideshare']){
   const group=nyGroups[mode],corridor=nyCorridor(mode);if(!corridor.geometry.length)continue;
   const plan=nyCohortState(current.recommended,egressIndex,mode),base=nyCohortState(current.baseline,egressIndex,mode);
   const shown=nyView==='baseline'?base:plan,ghost=nyView==='baseline'?null:base;
   const width=v=>2+9*Math.sqrt(Math.max(0,v)/peak);
   const tip=`<span class="tip-title">${labels[mode]} cohort</span><div class="tip-grid">`
    +`<em>Waiting now</em><b>${fmt(shown.remaining)} people</b>`
    +`<em>Modelled wait</em><b>${fmt(shown.waitMinutes)} min to clear</b>`
    +`<em>Service rate</em><b>${fmt(shown.rate)}/hour</b>`
    +(ghost?`<em>Baseline here</em><span class="tip-delta ${plan.remaining<=base.remaining?'better':'worse'}">${fmt(base.remaining)} people (${signed(plan.remaining-base.remaining)})</span>`:'')
    +`</div><p class="fine" style="margin:6px 0 0">${esc(corridor.basis)}</p>`;
   if(ghost&&base.remaining>0)L.polyline(corridor.geometry,{color:'#9aa49d',weight:width(base.remaining)+3.5,opacity:.28,lineCap:'round'}).addTo(group);
   if(shown.remaining>0)L.polyline(corridor.geometry,{color:nyView==='delta'?deltaColor((plan.remaining-base.remaining)/Math.max(1,base.start)):waitColor(shown.waitMinutes),weight:width(shown.remaining),opacity:.95,lineCap:'round',dashArray:'11 15',className:'flow'}).bindTooltip(tip,{sticky:true}).addTo(group);
   else L.polyline(corridor.geometry,{color:'#2f8f5b',weight:2,opacity:.45,dashArray:'2 6'}).bindTooltip(`<span class="tip-title">${labels[mode]} cohort</span>Cleared by ${fmt(minute)} min`).addTo(group);
   /* Queue marker at the cohort's transfer anchor: filled = shown scenario, dashed ring = baseline */
   const anchor=a[NY_MODE_ANCHOR[mode]];if(!anchor)continue;
   const size=v=>6+Math.sqrt(Math.max(0,v))/5.4;
   const fill=nyView==='delta'?deltaColor((plan.remaining-base.remaining)/Math.max(1,base.start)):waitColor(shown.waitMinutes);
   if(ghost)L.circleMarker([anchor.lat,anchor.lon],{radius:size(base.remaining),weight:1.4,color:'#8b9690',dashArray:'3 3',fill:false,opacity:.8}).addTo(group);
   L.circleMarker([anchor.lat,anchor.lon],{radius:size(shown.remaining),weight:2,color:'#fff',fillColor:fill,fillOpacity:.88})
    .bindTooltip(tip,{direction:'top'})
    .bindPopup(`<b>${esc(anchor.name)}</b><br>${esc(anchor.class)}<br>${labels[mode]} cohort<br>Modelled clearance: ${fmt((nyView==='baseline'?current.baseline:current.recommended).clearance_minutes[mode])} min<br>Modelled service rate: ${fmt(shown.rate)} people/hour`).addTo(group);}
  /* Context anchors without a modelled cohort */
  for(const x of context.map.anchors)if(!Object.values(NY_MODE_ANCHOR).includes(x.id)&&x.id!=='stadium')
   L.circleMarker([x.lat,x.lon],{radius:5,weight:1.5,color:'#fff',fillColor:'#6b7a86',fillOpacity:.85})
    .bindTooltip(`<span class="tip-title">${esc(x.name)}</span>${esc(x.class)} · context anchor`).addTo(nyGroups.roads);
  if(a.stadium)L.marker([a.stadium.lat,a.stadium.lon],{icon:L.divIcon({className:'',html:'<div class="venue-pin">♪</div>',iconSize:[34,34],iconAnchor:[17,17]}),zIndexOffset:900})
   .bindTooltip(`<span class="tip-title">MetLife Stadium</span>${fmt(current.recommended.cohort)} modelled departures at minute 0`,{direction:'top'}).addTo(nyGroups.actions);
  /* What exactly the plan is: every funded action pinned where it is delivered */
  const used={};
  current.implementation.forEach((action,index)=>{const place=NY_ACTION_PLACE[action.id]||{anchor:'stadium'},anchor=a[place.anchor];if(!anchor)return;
   // Always offset off the anchor so an action pin never hides its own queue marker.
   const n=used[place.anchor]=(used[place.anchor]||0)+1,angle=-Math.PI/2+(n-1)*Math.PI/2.4;
   const lat=anchor.lat+Math.cos(angle)*.0085,lon=anchor.lon+Math.sin(angle)*.0115;
   L.marker([lat,lon],{icon:L.divIcon({className:'',html:`<div class="asset-pin action" style="width:24px;height:24px">${String(index+1).padStart(2,'0')}</div>`,iconSize:[24,24],iconAnchor:[12,12]}),zIndexOffset:800})
    .bindTooltip(`<span class="tip-title">${String(index+1).padStart(2,'0')} · ${esc(action.name)}</span><div class="tip-grid"><em>Cost</em><b>${money(action.cost)}</b><em>Where</em><b>${esc(action.location)}</b><em>Owner</em><b>${esc(action.owner)}</b><em>Lead time</em><b>T−${action.lead_days} days</b><em>Affects</em><b>${place.mode?labels[place.mode]:'Queue comfort and safety'}</b></div><p class="fine" style="margin:6px 0 0">${esc(action.basis||'')}</p>`,{direction:'top'}).addTo(nyGroups.actions);});
  renderNyReadout(minute);renderNyLegend();applyLayerChips('nyLayers',map,nyGroups);
 }
 function renderNyReadout(minute){
  // Per-mode deltas stay neutral: a bigger shuttle queue can be a deliberate mode shift, not a failure.
  const rows=['rail','shuttle','rideshare'].map(mode=>{const plan=nyCohortState(current.recommended,egressIndex,mode),base=nyCohortState(current.baseline,egressIndex,mode);
   const shown=nyView==='baseline'?base:plan,diff=plan.remaining-base.remaining;
   return `<div><em><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${MODE_COLOR[mode]};margin-right:5px"></i>${labels[mode].split(' ')[0]}</em>`
    +`<b>${fmt(shown.remaining)}${nyView==='baseline'?'':` <span style="font-weight:400;color:#6a7a72">(${signed(diff)})</span>`}</b></div>`;}).join('');
  const sum=plan=>['rail','shuttle','rideshare'].reduce((s,m)=>s+nyCohortState(plan,egressIndex,m).remaining,0);
  const planTotal=sum(current.recommended),baseTotal=sum(current.baseline),total=nyView==='baseline'?baseTotal:planTotal;
  $('nyReadout').innerHTML=`<span>${nyView==='baseline'?'Before · no added service':nyView==='delta'?'After − before':'After · selected plan'}</span><b>${fmt(total)}</b><span style="letter-spacing:.2px;text-transform:none;font-size:9.5px;margin:2px 0 0">still waiting at +${fmt(minute)} min${nyView==='baseline'?'':` · <b style="display:inline;font-size:9.5px;letter-spacing:0" class="tip-delta ${planTotal<=baseTotal?'better':'worse'}">${signed(planTotal-baseTotal)} vs before</b>`}</span><div class="readout-rows">${rows}</div>`;
 }
 function renderNyLegend(){
  $('nyLegend').innerHTML=nyView==='delta'
   ?legendBox('Plan vs baseline queue',`<div class="ramp"><i style="background:#176d60"></i><i style="background:#a8b3ac"></i><i style="background:#b23b2b"></i></div><div class="ramp-labels"><b>Shorter queue</b><b>Same</b><b>Longer</b></div><div class="legend-keys"><span><i class="ring"></i>Dashed ring / halo = baseline</span><span><i class="dot" style="background:#bd391b"></i>Funded plan action</span></div><p class="legend-note">Corridors, top to bottom: rail to Secaucus and Penn, shuttle to Penn, rideshare to the Racetrack. Width shows the queue still waiting. A longer queue on one cohort can be a deliberate mode shift — read it against the total.</p>`)
   :legendBox('Modelled time left to clear',`${rampSwatch(WAIT_RAMP)}<div class="ramp-labels"><b>&lt;30 min</b><b>60</b><b>90</b><b>2 h+</b></div><div class="legend-keys"><span><i style="background:#176d60"></i>Rail · schematic pathway</span><span><i style="background:#356899"></i>Shuttle · OSM road route</span><span><i style="background:#c45b2d"></i>Rideshare · OSM road route</span>${nyView==='plan'?'<span><i class="ring"></i>Dashed ring / halo = baseline</span>':''}<span><i class="dot" style="background:#bd391b"></i>Funded plan action</span></div><p class="legend-note">Width scales with the queue still waiting. Dashes move toward the transfer point; they do not show vehicle speed.</p>`);
 }
 function setEgress(index,fromSlider){egressIndex=clamp(Number(index)||0,0,current.recommended.timeline.length-1);
  if(!fromSlider)$('egressTime').value=egressIndex;
  $('egressLabel').textContent=`Final whistle + ${fmt(egressPoint(current.recommended,egressIndex).minute)} min`;
  renderMap();}
 function toggleEgressPlay(){const button=$('playEgress');
  if(egressTimer){clearInterval(egressTimer);egressTimer=null;button.textContent='▶';button.setAttribute('aria-label','Play modelled egress');return;}
  button.textContent='❚❚';button.setAttribute('aria-label','Pause modelled egress');
  if(egressIndex>=current.recommended.timeline.length-1)setEgress(0);
  egressTimer=setInterval(()=>{const last=current.recommended.timeline.length-1;
   if(egressIndex>=last){toggleEgressPlay();return;}setEgress(egressIndex+1);},520);}
 function initMap(){if(!window.L){$('map').innerHTML='<p class="fine" style="padding:25px">Map library unavailable. All model comparisons and evidence remain available below.</p>';return;}
  map=L.map('map',{scrollWheelZoom:false}).setView([40.789,-74.04],12);
  L.tileLayer(BASEMAP,{attribution:BASEMAP_ATTR,maxZoom:19}).addTo(map);
  nyGroups={roads:L.layerGroup(),subway:L.layerGroup(),rail:L.layerGroup(),shuttle:L.layerGroup(),rideshare:L.layerGroup(),actions:L.layerGroup(),rice:L.layerGroup()};
  riceGroup=nyGroups.rice;
  for(const[k,n]of Object.entries(context.rice.datasets?.poi?.cells||{})){const[lat,lon]=k.split(',').map(Number);
   L.circle([lat,lon],{radius:Math.min(1800,100+Math.sqrt(n)*20),weight:1,color:'#79549c',fillColor:'#9976ba',fillOpacity:.17})
    .bindTooltip(`${fmt(n)} transformed POI rows in ~5 km cell; not actual facility locations`).addTo(riceGroup);}
  bindLayerChips('nyLayers',()=>applyLayerChips('nyLayers',map,nyGroups));
  $('egressTime').max=String((current?.recommended.timeline.length||33)-1);
  $('egressTime').addEventListener('input',e=>{if(egressTimer)toggleEgressPlay();setEgress(e.target.value,true);});
  $('playEgress').addEventListener('click',toggleEgressPlay);
  const points=context.map.anchors.map(a=>[a.lat,a.lon]);if(points.length)map.fitBounds(points,{padding:[45,45]});}
 function renderEvidence(){const v=context.validation;$('observedSource').href=context.source.source_url;$('validation').innerHTML=`${badge('Observed agency aggregates','observed')}<div class="mae-grid">${Object.entries(v.mae_by_mode).map(([k,val])=>`<div class="mae ${val>20?'warn':''}"><span>${labels[k]} · MAE</span><b>${val}<small> min</small></b></div>`).join('')}</div><p class="validation-note">Train on seven matches; predict the eighth. Rideshare transfers poorly across matches, so its operational forecast needs more evidence.</p>`;$('validationTable').innerHTML=table(['Match','Mode','Observed','Held-out prediction'],v.cases.map(r=>[r.match_id,labels[r.mode],r.observed_minutes+' min',r.predicted_minutes+' min']));
 const names={poi:'POI geometry',visits:'Store visits',spend:'Spend patterns',daily_spend:'Brand / state spending',uhi:'Urban heat index',weather:'Historical weather'};const d=context.rice.datasets||{};$('riceSummary').innerHTML=badge('Organizer sample data','sample')+Object.entries(d).map(([k,x])=>`<div class="dataset-row"><span>${names[k]}<small>${x.files_scanned} files scanned in full</small></span><b>${fmt(x.rows_matched_market_or_station)} matched rows<small>${x.date_min||'Spatial snapshot'}${x.date_max?' – '+x.date_max:''}</small></b></div>`).join('');if(!context.rice.available)$('riceSummary').innerHTML='<p class="fine">Organizer aggregate unavailable. No observed Rice claim is made.</p>';
 $('dataCoverage').innerHTML='<p class="fine">POI cells: method-demo map layer. Visits and spending: historical market context, not assigned FIFA trips. UHI: relative exposure scenarios only. Weather: no verified NY/NJ station match in the supplied files; no weather forecast is inferred.</p>'+context.public_status.map(x=>`<p class="fine"><b>${esc(x.source)}:</b> ${esc(x.status)}${x.stations?` · ${x.stations} stations, ${x.routes} routes`:''} · <a target="_blank" rel="noopener" href="${esc(x.url)}">source ↗</a></p>`).join('');
 $('assumptions').innerHTML=context.assumptions.map(a=>`<div class="assumption">${badge(a.class,a.class.includes('assumption')?'assumed':a.class.includes('Observed')?'observed':'modeled')}<b>${esc(a.name)}</b><p>${esc(a.value)}</p><p>${esc(a.limit)}</p></div>`).join('');$('cityCoverage').innerHTML='<div class="cities">'+['Atlanta','Boston','Dallas','Houston','Kansas City','Los Angeles','Miami','New York / New Jersey','Philadelphia','San Francisco Bay Area','Seattle'].map(c=>`<span class="city ${c.startsWith('New York')?'active':''}">${c}</span>`).join('')+'</div><p class="fine"><a href="https://github.com/HoustonSI/WorldCupUSSpatialData101" target="_blank" rel="noopener">Organizer public-data acquisition catalog ↗</a></p>';
 }
 function render(){const p=current,r=p.recommended,g=p.gains;
 const maxIndex=r.timeline.length-1,slider=$('egressTime');
 if(slider){slider.max=String(maxIndex);egressIndex=clamp(egressIndex,0,maxIndex);slider.value=egressIndex;$('egressLabel').textContent=`Final whistle + ${fmt(egressPoint(r,egressIndex).minute)} min`;}
 $('resultStatus').textContent=`${p.feasible_portfolios} feasible portfolios · ${fmt(r.cohort)} modelled egress trips · 81 sensitivity scenarios · ${labels[p.inputs.stress]}`;$('kpis').innerHTML=[['Maximum clearance',`${fmt(p.baseline.max_clearance_minutes)} → ${fmt(r.max_clearance_minutes)} min`,`${g.clearance_pct}% modelled reduction`],['Queue burden',`${g.queue_pct}% lower`,'Modelled queue-person-hours'],['Served within 2 hours',`${fmt(r.served_in_120)} people`,`${fmt(g.additional_served)} more than baseline`],['Accessible service',`${fmt(r.accessible_service_seats)} seats`,'Planned incremental capacity; verify vehicles']].map(([a,b,c])=>`<article class="kpi"><span class="label">${a}</span><strong>${b}</strong><small class="gain">${c}</small><div style="margin-top:10px">${badge('Model projection')}</div></article>`).join('');$('actionCount').textContent=p.implementation.length;$('portfolio').innerHTML=p.implementation.map((a,i)=>`<div class="portfolio-action"><span class="num">0${i+1}</span><div><b>${esc(a.name)}</b><p>${esc(a.location)}</p></div><strong>${short(a.cost)}</strong></div>`).join('')||'<p class="fine">No additional intervention selected.</p>';$('planTotal').innerHTML=`<span>Incremental planning cost<small>Range ${short(r.cost_low)}–${short(r.cost_high)}${r.cost_high>p.inputs.budget?' · high estimate exceeds budget':''}</small></span><strong>${short(r.cost)}</strong>`;
 $('uncertainty').innerHTML=Object.entries(p.sensitivity.ranges).map(([k,v])=>{const label={clearance_pct:'Clearance reduction',queue_pct:'Queue burden reduction',emissions_pct:'Affected-leg CO₂ reduction',heat_pct:'Relative heat burden reduction'}[k];const left=Math.max(0,Math.min(100,(v.min+30)/130*100)),width=Math.max(1,(v.max-v.min)/130*100),middle=Math.max(0,Math.min(100,(v.median+30)/130*100));return `<div class="range-row"><span>${label}</span><div class="range-track"><i style="left:${left}%;width:${Math.min(width,100-left)}%"></i><b style="left:${middle}%"></b></div><strong>${v.min}–${v.max}%</strong></div>`;}).join('');$('stressTable').innerHTML=table(['Condition','Baseline → plan','Served in 2h'],p.stress_tests.map(s=>[labels[s.id],`${fmt(s.baseline_minutes)} → ${fmt(s.plan_minutes)} min`,`${s.coverage_pct}%`]));$('deliveryTable').innerHTML=table(['Action / lead time','Proposed owner','Dependencies','Verify success'],p.implementation.map(a=>[`<b>${esc(a.name)}</b><p>T−${a.lead_days} days · ${short(a.cost)}</p>`,esc(a.owner),`<p>${esc(a.dependency)}</p>`,`<p>${esc(a.verification)}</p>`]));$('marginal').innerHTML=table(['Action removed','Extra queue-person-hours','Policy score lost'],p.marginal.map(a=>[esc(a.name),fmt(a.queue_person_hours_avoided),a.score_contribution]));renderCharts();renderMap();}
 /* === BUDGET: any amount, solved live, with the exported grid as an offline fallback === */
 const BUDGET_MAX=2000000;
 function readBudget(){return clamp(Math.round((Number($('budget').value)||0)/1000)*1000,0,BUDGET_MAX);}
 function syncBudgetInputs(value){$('budget').value=value;$('budgetRange').value=value;}
 function budgetNote(text,tone){const note=$('budgetNote');note.textContent=text;note.className=`budget-note${tone?' '+tone:''}`;}
 function nearestExported(budget,priority,stress){
  const options=Object.keys(scenarios).map(key=>key.split(':')).filter(([,p,s])=>p===priority&&s===stress).map(([b])=>Number(b));
  if(!options.length)return null;
  const affordable=options.filter(value=>value<=budget);
  return affordable.length?Math.max(...affordable):Math.min(...options);}
 async function choose(){
  const budget=readBudget(),priority=$('priority').value,stress=$('stress').value;
  syncBudgetInputs(budget);
  const exact=scenarios[`${budget}:${priority}:${stress}`];
  if(exact){current=exact;budgetNote(`${money(budget)} · saved model calculation`,'');render();return;}
  const token=++planToken;
  budgetNote(`Solving the portfolio for ${money(budget)}…`,'');
  try{
   const response=await fetch('/api/nynj/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({budget,priority,stress})});
   if(!response.ok)throw Error(`Planner returned ${response.status}`);
   const result=await response.json();
   if(token!==planToken)return;
   current=result;budgetNote(`${money(budget)} · solved live from the same model`,'live');render();
  }catch(error){
   if(token!==planToken)return;
   const fallback=nearestExported(budget,priority,stress);
   if(fallback===null){$('error').hidden=false;$('error').textContent='This control combination is unavailable and no saved scenario matches it.';return;}
   current=scenarios[`${fallback}:${priority}:${stress}`];
   budgetNote(`Live planner unavailable — showing the nearest saved budget, ${money(fallback)}.`,'fallback');render();}}
 /* === HOUSTON ARRIVAL MAP === */
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
 function openPreparedExample(event){event.preventDefault();const brief=$('eventBrief').value.trim();$('requestError').hidden=Boolean(brief);if(!brief){$('eventBrief').focus();return;}
 $('submittedBrief').textContent=brief;$('newYorkResult').hidden=false;$('resultsNav').href='#newYorkResult';
 if(!map)initMap();
 choose().then(()=>{if(map){map.invalidateSize();const points=context.map.anchors.map(a=>[a.lat,a.lon]);if(points.length)map.fitBounds(points,{padding:[45,45]});}});
 $('resultIntro').focus({preventScroll:true});$('newYorkResult').scrollIntoView({behavior:'smooth',block:'start'});
 }
 /* === SCROLL REVEALS: VISUAL PRESENTATION ONLY === */
 if('IntersectionObserver' in window&&!matchMedia('(prefers-reduced-motion: reduce)').matches){const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){entry.target.classList.add('entered');observer.unobserve(entry.target);}},{threshold:.08});for(const element of document.querySelectorAll('.map-layout,.request-panel,.section-title,.two-col'))observer.observe(element);}
 async function init(){try{const r=await Promise.all(['competition-data.json','competition-scenarios.json'].map(x=>fetch(x).then(r=>{if(!r.ok)throw Error('The evidence package could not load.');return r.json();})));[context,scenarios]=r;renderHouston('plan');renderEvidence();$('eventRequest').addEventListener('submit',openPreparedExample);
 for(const[id,view]of[['houstonBefore','baseline'],['houstonAfter','plan'],['houstonDelta','delta']])$(id).addEventListener('click',()=>renderHouston(view));
 $('editRequest').addEventListener('click',()=>{$('eventBrief').focus({preventScroll:true});$('new-event').scrollIntoView({behavior:'smooth'});});
 let budgetDebounce;
 const queueChoose=()=>{clearTimeout(budgetDebounce);budgetDebounce=setTimeout(choose,260);};
 $('budgetRange').addEventListener('input',e=>{syncBudgetInputs(Number(e.target.value));queueChoose();});
 $('budget').addEventListener('input',()=>{$('budgetRange').value=String(clamp(Number($('budget').value)||0,0,BUDGET_MAX));queueChoose();});
 $('budget').addEventListener('change',choose);
 for(const x of ['priority','stress'])$(x).addEventListener('change',choose);
 for(const[id,view]of[['showBaseline','baseline'],['showPlan','plan'],['showDelta','delta']])$(id).addEventListener('click',()=>{nyView=view;renderMap();});$('download').addEventListener('click',()=>{const brief='# Your event brief\n'+$('submittedBrief').textContent+'\n\n'+current.narrative;const blob=new Blob([brief],{type:'text/markdown;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='EventFlow-NYNJ-concert-brief.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});}catch(e){$('error').hidden=false;$('error').textContent=e.message;$('resultStatus').textContent='The decision package is unavailable; no results are being fabricated.';}}
 init();
})();
