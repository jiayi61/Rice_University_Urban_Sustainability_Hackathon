(() => {
  'use strict';

  const state = {
    catalog: null,
    payload: null,
    selectedPlanId: 'balanced',
    timeIndex: 4,
    focusRouteIndex: 0,
    map: null,
    groups: {},
    routeLines: new Map(),
    demandCircles: new Map(),
    heatCircles: new Map(),
    playing: null,
  };

  const $ = (id) => document.getElementById(id);
  const fmt = (value) => new Intl.NumberFormat('en-US').format(Math.round(value));
  const money = (value, compact = false) => {
    const currency = state.payload?.currency?.code || 'USD';
    return compact
      ? new Intl.NumberFormat(undefined, { style: 'currency', currency, notation: 'compact', maximumFractionDigits: 1 }).format(value)
      : new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value);
  };
  const pct = (value) => `${Math.round(value)}%`;
  const plan = () => state.payload.plans.find((item) => item.plan_id === state.selectedPlanId) || state.payload.plans[0];
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);

  async function api(path, options = {}) {
    const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  function showError(message) {
    const banner = $('errorBanner');
    banner.textContent = message;
    banner.hidden = false;
    window.setTimeout(() => { banner.hidden = true; }, 7000);
  }

  function pressureColor(value) {
    if (value < 0.68) return '#24a777';
    if (value < 0.9) return '#d7a222';
    if (value < 1.08) return '#ee7b37';
    if (value < 1.25) return '#d9485f';
    return '#7f1d35';
  }

  function pressureClass(value) {
    return value < 0.8 ? 'good' : value < 1 ? 'busy' : 'hot';
  }

  function minuteLabel(minute) {
    if (minute === 0) return 'Kickoff';
    const amount = Math.abs(minute);
    return `${amount} minute${amount === 1 ? '' : 's'} ${minute < 0 ? 'before' : 'after'} start`;
  }

  function shortMinute(minute) {
    if (minute === 0) return 'Kickoff';
    return `T${minute < 0 ? '−' : '+'}${Math.abs(minute)} min`;
  }

  function initMap() {
    if (!window.L) throw new Error('The map library could not load. Check the internet connection and reload.');
    state.map = L.map('map', { zoomControl: false, preferCanvas: true }).setView([29.716, -95.397], 11);
    L.control.zoom({ position: 'bottomright' }).addTo(state.map);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(state.map);
    state.groups = {
      traffic: L.layerGroup(), demand: L.layerGroup(), rail: L.layerGroup(), bus: L.layerGroup(),
      shuttle: L.layerGroup(), parkRide: L.layerGroup(), gaps: L.layerGroup(), heat: L.layerGroup(),
    };
    document.querySelectorAll('[data-layer]').forEach((input) => {
      input.addEventListener('change', syncLayerVisibility);
    });
    $('layerButton').addEventListener('click', () => {
      const panel = $('layerPanel');
      panel.hidden = !panel.hidden;
      $('layerButton').setAttribute('aria-expanded', String(!panel.hidden));
    });
    $('recenterBtn').addEventListener('click', recenterMap);
  }

  function recenterMap() {
    if (!state.payload) return;
    const points = [[state.payload.venue.lat, state.payload.venue.lon], ...state.payload.zones.map((zone) => [zone.lat, zone.lon])];
    state.map.fitBounds(points, { padding: [35, 35], maxZoom: 12 });
  }

  function syncLayerVisibility() {
    let count = 0;
    document.querySelectorAll('[data-layer]').forEach((input) => {
      const group = state.groups[input.dataset.layer];
      if (!group) return;
      if (input.checked) {
        if (!state.map.hasLayer(group)) group.addTo(state.map);
        count += 1;
      } else if (state.map.hasLayer(group)) {
        state.map.removeLayer(group);
      }
    });
    $('layerCount').textContent = count;
  }

  function lineTooltip(route, snapshot) {
    return `<b>${escapeHtml(route.origin)} → ${escapeHtml(route.destination)}</b><br>${escapeHtml(route.primary_mode)} · ${route.distance_km} km<br>Pressure ${snapshot.pressure.toFixed(2)}× · ${snapshot.travel_minutes.toFixed(0)} min`;
  }

  function buildMapLayers() {
    Object.values(state.groups).forEach((group) => group.clearLayers());
    state.routeLines.clear();
    state.demandCircles.clear();
    state.heatCircles.clear();
    const selected = plan();

    const markerIcon = state.payload.event.event_type?.includes('concert') ? '♪' : state.payload.event.event_type === 'convention' ? '◆' : '●';
    L.marker([state.payload.venue.lat, state.payload.venue.lon], {
      icon: L.divIcon({ className: '', html: `<div class="event-marker">${markerIcon}</div>`, iconSize: [34, 34], iconAnchor: [17, 17] }),
      zIndexOffset: 1000,
    }).bindTooltip(`${escapeHtml(state.payload.venue.name)}<br>${fmt(state.payload.event.attendance)} expected attendees`, { className: 'event-tooltip', direction: 'top' }).addTo(state.groups.demand);

    state.payload.transit.routes.forEach((route) => {
      const geometry = route.geometry.map((point) => [point[0], point[1]]);
      const style = route.mode === 'rail'
        ? { color: route.color, weight: route.venue_access ? 5 : 3.2, opacity: route.venue_access ? .92 : .62 }
        : { color: route.venue_access ? '#245fb8' : '#4e86cf', weight: route.venue_access ? 3.1 : 1.15, opacity: route.venue_access ? .82 : .17 };
      L.polyline(geometry, { ...style, interactive: true })
        .bindTooltip(`<b>${escapeHtml(route.short_name)} ${escapeHtml(route.name)}</b>${route.venue_access ? '<br>Direct venue-access service' : ''}`, { className: 'event-tooltip', sticky: true })
        .addTo(state.groups[route.mode]);
    });

    (state.payload.transit.stations || []).forEach((station) => {
      const layer = station.mode === 'bus' ? 'bus' : station.mode === 'parking' ? 'parkRide' : 'rail';
      L.marker([station.lat, station.lon], {
        icon: L.divIcon({ className: '', html: `<div class="transit-marker ${escapeHtml(station.mode)}"></div>`, iconSize: [17, 17], iconAnchor: [8, 8] }),
      }).bindTooltip(`<b>${escapeHtml(station.name)}</b><br>${escapeHtml(station.mode)} · wheelchair: ${escapeHtml(station.wheelchair || 'unknown')}`, { className: 'event-tooltip' }).addTo(state.groups[layer]);
    });

    selected.routes.forEach((route) => {
      const snapshot = route.timeline[state.timeIndex];
      const line = L.polyline(route.geometry, {
        color: pressureColor(snapshot.pressure), weight: 3.5 + Math.min(7, snapshot.pressure * 3.7),
        opacity: .88, dashArray: '8 8', className: 'route-flow', lineCap: 'round',
      }).bindTooltip(lineTooltip(route, snapshot), { className: 'event-tooltip', sticky: true });
      line.on('click', () => {
        const sorted = [...selected.routes].sort((a, b) => b.peak_pressure - a.peak_pressure);
        state.focusRouteIndex = Math.max(0, sorted.findIndex((item) => item.route_id === route.route_id));
        renderFocusRoute();
      });
      line.addTo(state.groups.traffic);
      state.routeLines.set(route.route_id, line);
    });

    state.payload.zones.forEach((zone) => {
      const active = zone.timeline[state.timeIndex].people;
      const circle = L.circleMarker([zone.lat, zone.lon], {
        radius: 6 + Math.sqrt(active) / 8.8, fillColor: '#3977db', fillOpacity: .40,
        color: '#1f5ebc', opacity: .85, weight: 1.5,
      }).bindTooltip(`<b>${escapeHtml(zone.name)}</b><br>${fmt(active)} projected people now<br>${fmt(zone.visitors)} event total`, { className: 'event-tooltip', direction: 'top' });
      circle.addTo(state.groups.demand);
      state.demandCircles.set(zone.zone_id, circle);

      const gapRadius = 230 + zone.first_mile_gap * .45;
      L.circle([zone.lat, zone.lon], { radius: gapRadius, color: '#d9485f', weight: 1.4, dashArray: '5 5', fill: false, opacity: .72 })
        .bindTooltip(`${escapeHtml(zone.name)}<br>First-mile gap ${zone.first_mile_gap} m`, { className: 'event-tooltip' }).addTo(state.groups.gaps);
      const heatCircle = L.circle([zone.lat, zone.lon], {
        radius: 180 + Math.sqrt(active) * 7 * zone.vulnerability, stroke: false,
        fillColor: '#f0783b', fillOpacity: .12 + zone.vulnerability * .13,
      }).addTo(state.groups.heat);
      state.heatCircles.set(zone.zone_id, heatCircle);
    });

    const shuttleRoutes = selected.routes.filter((route) => route.primary_mode.includes('shuttle'));
    shuttleRoutes.forEach((route) => {
      L.polyline(route.geometry, { color: '#7957d5', weight: 4.5, opacity: .82, dashArray: '3 7', lineCap: 'round' })
        .bindTooltip(`<b>${escapeHtml(route.origin)} shuttle</b><br>${fmt(route.people_covered)} people covered`, { className: 'event-tooltip', sticky: true })
        .addTo(state.groups.shuttle);
    });

    state.payload.zones.filter((zone) => zone.kind === 'park_ride').forEach((zone) => {
      L.marker([zone.lat, zone.lon], {
        icon: L.divIcon({ className: '', html: '<div class="park-marker">P</div>', iconSize: [20, 20], iconAnchor: [10, 10] }),
      }).bindTooltip(`${escapeHtml(zone.name)}<br>${fmt(zone.visitors)} projected users`, { className: 'event-tooltip' }).addTo(state.groups.parkRide);
    });
    syncLayerVisibility();
    recenterMap();
  }

  function updateMapTime() {
    const selected = plan();
    selected.routes.forEach((route) => {
      const snapshot = route.timeline[state.timeIndex];
      const line = state.routeLines.get(route.route_id);
      if (!line) return;
      line.setStyle({ color: pressureColor(snapshot.pressure), weight: 3.2 + Math.min(7.2, snapshot.pressure * 4) });
      line.setTooltipContent(lineTooltip(route, snapshot));
    });
    state.payload.zones.forEach((zone) => {
      const active = zone.timeline[state.timeIndex].people;
      state.demandCircles.get(zone.zone_id)?.setRadius(5.5 + Math.sqrt(active) / 8.8);
      state.heatCircles.get(zone.zone_id)?.setRadius(160 + Math.sqrt(active) * 7 * zone.vulnerability);
    });
  }

  function renderPlanCards() {
    $('planCards').innerHTML = state.payload.plans.map((item) => `
      <button class="plan-card ${item.plan_id === state.selectedPlanId ? 'selected' : ''}" data-plan="${item.plan_id}">
        <div class="plan-top"><strong>${escapeHtml(item.name)}</strong><span class="plan-badge">${escapeHtml(item.label)}</span></div>
        <p>${escapeHtml(item.description)}</p>
        <div class="plan-metrics"><span>Planning cost<b>${money(item.cost.mid, true)}</b></span><span>Coverage<b>${item.metrics.coverage_pct}%</b></span><span>Max pressure<b>${item.metrics.max_pressure.toFixed(2)}×</b></span></div>
      </button>`).join('');
    $('planCards').querySelectorAll('[data-plan]').forEach((button) => button.addEventListener('click', () => selectPlan(button.dataset.plan)));
  }

  function renderSelectedSummary() {
    const selected = plan();
    $('selectedPlanSummary').innerHTML = `
      <h3>${escapeHtml(selected.name)} deploys ${selected.actions.length} coordinated actions</h3>
      <ul>${selected.actions.slice(0, 4).map((action, index) => `<li><i>${index + 1}</i><span><b>${escapeHtml(action.title)}</b><br>${escapeHtml(action.corridor)}</span></li>`).join('')}</ul>
      <button class="all-actions" id="openActionsButton">Inspect all routes, infrastructure and costs →</button>`;
    $('openActionsButton').addEventListener('click', () => showView('routes'));
  }

  function renderKpis() {
    const selected = plan();
    const snapshots = selected.routes.map((route) => route.timeline[state.timeIndex]);
    const maxPressure = Math.max(...snapshots.map((item) => item.pressure));
    const activePeople = state.payload.zones.reduce((sum, zone) => sum + zone.timeline[state.timeIndex].people, 0);
    const avgSpeed = snapshots.reduce((sum, item) => sum + item.speed_pct_freeflow, 0) / snapshots.length;
    const avgTravel = snapshots.reduce((sum, item) => sum + item.travel_minutes, 0) / snapshots.length;
    const avgFreeflow = selected.routes.reduce((sum, item) => sum + item.freeflow_minutes, 0) / selected.routes.length;
    const items = [
      ['People in motion', fmt(activePeople), `${Math.round(activePeople / state.payload.event.attendance * 100)}% of event demand`],
      ['Worst route pressure', `${maxPressure.toFixed(2)}×`, maxPressure > 1 ? 'above modeled capacity' : 'within modeled capacity'],
      ['Network speed', `${Math.round(avgSpeed)}%`, 'of free-flow speed'],
      ['Average route time', `${Math.round(avgTravel)} min`, `${Math.max(0, Math.round(avgTravel - avgFreeflow))} min above free flow`],
      ['Plan coverage', pct(selected.metrics.coverage_pct), `${fmt(selected.metrics.people_covered)} people`],
      ['Vehicles avoided', fmt(selected.metrics.vehicles_avoided), `${selected.metrics.emissions_reduction_pct}% emissions reduction`],
    ];
    $('kpiGrid').innerHTML = items.map(([label, value, note]) => `<div class="kpi"><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`).join('');
  }

  function renderPressureChart() {
    const svg = $('pressureChart');
    const width = 760, height = 210, left = 42, right = 15, top = 14, bottom = 31;
    const innerW = width - left - right, innerH = height - top - bottom;
    const minY = 0, maxY = 1.5;
    const x = (index) => left + index / (state.payload.time_points.length - 1) * innerW;
    const y = (value) => top + (maxY - value) / (maxY - minY) * innerH;
    const colors = { efficient: '#f0783b', balanced: '#0f9f91', resilient: '#7957d5' };
    let html = '';
    [0, .5, 1, 1.5].forEach((value) => {
      html += `<line x1="${left}" y1="${y(value)}" x2="${width - right}" y2="${y(value)}" stroke="${value === 1 ? '#d9485f' : '#dfe5eb'}" stroke-width="${value === 1 ? 1.4 : 1}" stroke-dasharray="${value === 1 ? '5 5' : '0'}"/>`;
      html += `<text x="${left - 9}" y="${y(value) + 4}" text-anchor="end" font-size="10" fill="#748196">${value.toFixed(1)}</text>`;
    });
    state.payload.time_points.forEach((minute, index) => {
      if (index % 2 === 0 || minute === 0) html += `<text x="${x(index)}" y="${height - 8}" text-anchor="middle" font-size="9" fill="#748196">${minute === 0 ? 'Start' : `T${minute > 0 ? '+' : '−'}${Math.abs(minute)}`}</text>`;
    });
    state.payload.plans.forEach((item) => {
      const values = state.payload.time_points.map((_, timeIndex) => Math.max(...item.routes.map((route) => route.timeline[timeIndex].pressure)));
      const points = values.map((value, index) => `${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(' ');
      html += `<polyline points="${points}" fill="none" stroke="${colors[item.plan_id]}" stroke-width="${item.plan_id === state.selectedPlanId ? 4 : 2.2}" opacity="${item.plan_id === state.selectedPlanId ? 1 : .58}" stroke-linejoin="round" stroke-linecap="round"/>`;
      if (item.plan_id === state.selectedPlanId) values.forEach((value, index) => { html += `<circle cx="${x(index)}" cy="${y(value)}" r="2.6" fill="#fff" stroke="${colors[item.plan_id]}" stroke-width="2"/>`; });
    });
    html += `<line x1="${x(state.timeIndex)}" y1="${top}" x2="${x(state.timeIndex)}" y2="${height - bottom}" stroke="#0c1524" stroke-width="1.5" opacity=".65"/>`;
    html += `<rect x="${x(state.timeIndex) - 24}" y="${top + 2}" width="48" height="18" rx="5" fill="#0c1524"/><text x="${x(state.timeIndex)}" y="${top + 15}" text-anchor="middle" font-size="9" font-weight="700" fill="#fff">${shortMinute(state.payload.time_points[state.timeIndex]).replace(' min', '')}</text>`;
    svg.innerHTML = html;
    $('chartLegend').innerHTML = state.payload.plans.map((item) => `<span><i style="background:${colors[item.plan_id]}"></i>${escapeHtml(item.name)}</span>`).join('') + '<span><i style="background:#d9485f;height:1px"></i>Capacity threshold</span>';
  }

  function renderFocusRoute() {
    const routes = [...plan().routes].sort((a, b) => b.peak_pressure - a.peak_pressure);
    state.focusRouteIndex %= routes.length;
    const route = routes[state.focusRouteIndex];
    const snapshot = route.timeline[state.timeIndex];
    $('focusRouteName').textContent = route.origin;
    $('focusRouteBody').innerHTML = `
      <div class="route-metrics"><div><span>Projected pressure</span><b>${snapshot.pressure.toFixed(2)}×</b></div><div><span>Travel time</span><b>${snapshot.travel_minutes.toFixed(0)} min</b></div><div><span>People covered</span><b>${fmt(route.people_covered)}</b></div></div>
      <div class="pressure-meter"><i style="width:${Math.min(100, snapshot.pressure / 1.4 * 100)}%;background:${pressureColor(snapshot.pressure)}"></i></div>
      <p class="route-note"><b>${escapeHtml(route.primary_mode)}</b> · ${route.distance_km} km · ${escapeHtml(route.geometry_source)}. First-mile gap ${route.first_mile_gap_m} m; last-mile gap ${route.last_mile_gap_m} m.</p>`;
  }

  function renderRoutesView() {
    const selected = plan();
    $('routesPlanPicker').innerHTML = state.payload.plans.map((item) => `<button data-plan-route="${item.plan_id}" class="${item.plan_id === state.selectedPlanId ? 'active' : ''}">${escapeHtml(item.name)}</button>`).join('');
    $('routesPlanPicker').querySelectorAll('[data-plan-route]').forEach((button) => button.addEventListener('click', () => selectPlan(button.dataset.planRoute)));
    const summary = [
      ['Planning midpoint', money(selected.cost.mid), `${money(selected.cost.low)}–${money(selected.cost.high)}`],
      ['People covered', fmt(selected.metrics.people_covered), `${selected.metrics.coverage_pct}% of attendance`],
      ['Vehicle trips avoided', fmt(selected.metrics.vehicles_avoided), 'private vehicles'],
      ['Delay reduction', pct(selected.metrics.delay_reduction_pct), 'network estimate'],
      ['Robustness', `${selected.metrics.robustness_score}/100`, 'stress-test score'],
    ];
    $('costSummaryBand').innerHTML = summary.map(([label, value, note]) => `<div><span>${label}</span><b>${value}</b><small>${note}</small></div>`).join('');
    $('routeCountLabel').textContent = `${selected.routes.length} demand corridors · street-routed`;
    $('routeTableBody').innerHTML = [...selected.routes].sort((a, b) => b.peak_pressure - a.peak_pressure).map((route) => `
      <tr><td><b>${escapeHtml(route.origin)}</b><small>${escapeHtml(route.primary_mode)}</small></td><td>${fmt(route.people)}</td><td>${route.distance_km} km</td><td>${route.baseline_minutes.toFixed(0)} min</td><td><b>${route.plan_minutes.toFixed(0)} min</b><small>${Math.max(0, Math.round(route.baseline_minutes - route.plan_minutes))} min saved</small></td><td><span class="pressure-pill ${pressureClass(route.peak_pressure)}">${route.peak_pressure.toFixed(2)}×</span></td><td>${fmt(route.people_covered)}</td><td>${route.first_mile_gap_m} m / ${route.last_mile_gap_m} m</td></tr>`).join('');
    $('actionCards').innerHTML = selected.actions.map((action) => `
      <article class="action-card"><div class="action-title"><b>${escapeHtml(action.title)}</b><span class="mode-tag">${escapeHtml(action.mode)}</span></div><p>${escapeHtml(action.corridor)}</p><div class="action-stats"><span>Units<b>${escapeHtml(action.units)}</b></span><span>Added capacity<b>${fmt(action.added_capacity)}</b></span><span>Mid cost<b>${money(action.cost_mid, true)}</b></span></div><div class="action-meta"><span><b>Range:</b> ${money(action.cost_low)}–${money(action.cost_high)}</span><span><b>Owner:</b> ${escapeHtml(action.owner)} · ${escapeHtml(action.timeline)}</span><span><b>Dependency:</b> ${escapeHtml(action.dependency)}</span><span><b>Basis:</b> ${escapeHtml(action.basis)}</span></div></article>`).join('');
    renderCostBars(selected);
  }

  function renderCostBars(selected) {
    const buckets = {};
    selected.actions.forEach((action) => { buckets[action.mode] = (buckets[action.mode] || 0) + action.cost_mid; });
    buckets['delivery + contingency'] = selected.cost.program_delivery_and_contingency;
    const max = Math.max(...Object.values(buckets));
    $('costBreakdownTitle').textContent = `${selected.name} · ${money(selected.cost.mid, true)}`;
    $('costBars').innerHTML = Object.entries(buckets).sort((a, b) => b[1] - a[1]).map(([name, value]) => `<div class="cost-row"><div><span>${escapeHtml(name.replace('_', ' '))}</span><b>${money(value, true)}</b></div><div class="cost-track"><i style="width:${value / max * 100}%"></i></div></div>`).join('');
  }

  function renderCities() {
    const cities = [...state.catalog.cities].sort((a, b) => b.scores.readiness - a.scores.readiness);
    $('cityRanking').innerHTML = cities.map((city, index) => `<div class="city-row ${city.city_id === 'houston' ? 'selected' : ''}" data-city="${city.city_id}"><span class="rank">${index + 1}</span><span class="city-name"><b>${escapeHtml(city.city)}</b><small>${escapeHtml(city.venue)}</small></span><span class="score-track"><i style="width:${city.scores.readiness}%"></i></span><span class="city-score">${city.scores.readiness}</span><span class="gap-label">Gap: ${escapeHtml(city.priority_gap)}</span></div>`).join('');
    $('cityRanking').querySelectorAll('[data-city]').forEach((row) => row.addEventListener('click', () => {
      $('cityRanking').querySelectorAll('[data-city]').forEach((item) => item.classList.toggle('selected', item === row));
      renderCityDetail(cities.find((city) => city.city_id === row.dataset.city));
    }));
    renderCityDetail(cities.find((city) => city.city_id === 'houston'));
  }

  function renderCityDetail(city) {
    const values = [city.scores.transit_access, city.scores.road_redundancy, city.scores.last_mile, city.scores.climate_resilience, city.scores.data_maturity];
    const labels = ['Transit', 'Roads', 'Last mile', 'Climate', 'Data'];
    const center = 130, radius = 85;
    const vertices = values.map((value, index) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / values.length;
      return [center + Math.cos(angle) * radius * value / 100, 116 + Math.sin(angle) * radius * value / 100];
    });
    const outer = labels.map((_, index) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / labels.length;
      return [center + Math.cos(angle) * radius, 116 + Math.sin(angle) * radius];
    });
    const radar = `<svg class="radar" viewBox="0 0 260 240"><polygon points="${outer.map((p) => p.join(',')).join(' ')}" fill="#f3f6f9" stroke="#d7dfe8"/><polygon points="${vertices.map((p) => p.join(',')).join(' ')}" fill="rgba(15,159,145,.18)" stroke="#0f9f91" stroke-width="2"/>${outer.map((point, index) => `<line x1="${center}" y1="116" x2="${point[0]}" y2="${point[1]}" stroke="#e2e7ed"/><text x="${center + (point[0] - center) * 1.18}" y="${116 + (point[1] - 116) * 1.14}" text-anchor="middle" font-size="10" fill="#637084">${labels[index]}</text>`).join('')}${vertices.map((point) => `<circle cx="${point[0]}" cy="${point[1]}" r="3" fill="#0f9f91"/>`).join('')}</svg>`;
    $('cityDetail').innerHTML = `<p class="eyebrow">READINESS ${city.scores.readiness}/100</p><h2>${escapeHtml(city.city)}</h2><p>${escapeHtml(city.venue)} · primary gap: <b>${escapeHtml(city.priority_gap)}</b></p>${radar}<div class="city-dimensions">${labels.map((label, index) => `<div><span>${label}</span><b>${values[index]}/100</b></div>`).join('')}</div><div class="screening-note">Comparable screening score, not an official city ranking. Replace each dimension with the same agency-level ingestion pipeline before procurement decisions.</div>`;
  }

  function renderEvidence() {
    const freshness = state.payload.data_freshness;
    $('freshnessGrid').innerHTML = Object.entries(freshness).map(([key, value]) => `<div class="fresh-card"><span><i></i>${escapeHtml(key.replace('_', ' '))}</span><b>${escapeHtml(value)}</b></div>`).join('');
    $('sourceCards').innerHTML = state.catalog.sources.map((source) => `<a class="source-card" href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer"><small>${escapeHtml(source.kind)}</small><b>${escapeHtml(source.name)} ↗</b><p>${escapeHtml(source.use)}</p></a>`).join('');
    $('limitsCard').innerHTML = `<p class="eyebrow">MODEL BOUNDARIES</p><h3>What the platform does not claim</h3><ul>${state.payload.model_limits.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
  }

  function renderAssumptions() {
    const panel = $('assumptionPanel');
    const assumptions = state.payload.brief?.assumptions || [];
    if (!assumptions.length) { panel.hidden = true; return; }
    panel.hidden = false;
    panel.innerHTML = `<div class="assumption-title"><b>Check the assumptions</b><span>Transparent, editable through your next prompt</span></div>${assumptions.slice(0, 4).map((item) => `<div class="assumption-item" title="${escapeHtml(item.basis)}"><span><i class="confidence-dot ${escapeHtml(item.confidence)}"></i>${escapeHtml(item.field)} · ${escapeHtml(item.confidence)}</span><b>${escapeHtml(item.value)}</b><small>${escapeHtml(item.basis)}</small></div>`).join('')}`;
  }

  function renderEventContext() {
    const event = state.payload.event;
    const weather = event.weather || {};
    const weatherText = weather.temperature_c != null ? `${weather.temperature_c}°C climate normal` : `${weather.temperature_f}°F scenario`;
    $('plannerHeading').textContent = `${event.short_name} · ${state.payload.venue.name}`;
    $('eventMeta').textContent = `${fmt(event.attendance)} people · ${event.date} at ${event.start_time} · ${weatherText}. Street, transit, cost and demand inputs are selected automatically.`;
    $('freshnessLabel').textContent = `${state.payload.venue.city || 'Houston'} · ${state.payload.transit.feed.snapshot}`;
    $('routesHeading').textContent = `${state.payload.venue.city || 'City'} routes, capacity and full cost stack`;
  }

  function updateTime(index) {
    state.timeIndex = Number(index);
    $('timeSlider').value = state.timeIndex;
    const minute = state.payload.time_points[state.timeIndex];
    $('timeTitle').textContent = minuteLabel(minute);
    $('projectionLabel').textContent = shortMinute(minute);
    updateMapTime();
    renderKpis();
    renderPressureChart();
    renderFocusRoute();
  }

  function selectPlan(planId) {
    state.selectedPlanId = planId;
    state.focusRouteIndex = 0;
    renderPlanCards();
    renderSelectedSummary();
    buildMapLayers();
    renderKpis();
    renderPressureChart();
    renderFocusRoute();
    renderRoutesView();
  }

  function showView(viewId) {
    document.querySelectorAll('.view').forEach((view) => view.classList.toggle('active', view.id === `${viewId}View`));
    document.querySelectorAll('.view-tab').forEach((button) => button.classList.toggle('active', button.dataset.view === viewId));
    if (viewId === 'planner') window.setTimeout(() => state.map?.invalidateSize(), 30);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function bindControls() {
    document.querySelectorAll('.view-tab').forEach((button) => button.addEventListener('click', () => showView(button.dataset.view)));
    $('timeSlider').addEventListener('input', (event) => updateTime(event.target.value));
    $('playButton').addEventListener('click', () => {
      if (state.playing) {
        clearInterval(state.playing); state.playing = null; $('playButton').textContent = '▶'; return;
      }
      $('playButton').textContent = 'Ⅱ';
      state.playing = setInterval(() => {
        const next = (state.timeIndex + 1) % state.payload.time_points.length;
        updateTime(next);
      }, 950);
    });
    $('nextRouteBtn').addEventListener('click', () => { state.focusRouteIndex += 1; renderFocusRoute(); });
    $('eventSelect').addEventListener('change', (event) => loadPlan(event.target.value));
    $('briefForm').addEventListener('submit', (event) => {
      event.preventDefault();
      loadBrief($('briefInput').value.trim());
    });
    document.querySelectorAll('[data-example]').forEach((button) => button.addEventListener('click', () => {
      $('briefInput').value = button.dataset.example;
      $('briefInput').focus();
    }));
  }

  async function loadPlan(eventId) {
    $('loadingOverlay').classList.remove('hidden');
    try {
      state.payload = await api('/api/v2/plan', { method: 'POST', body: JSON.stringify({ event_id: eventId }) });
      state.selectedPlanId = state.payload.recommended_plan_id;
      state.timeIndex = 4;
      state.focusRouteIndex = 0;
      renderEventContext();
      renderPlanCards();
      renderSelectedSummary();
      buildMapLayers();
      updateTime(4);
      renderRoutesView();
      renderCities();
      renderEvidence();
      renderAssumptions();
    } catch (error) {
      showError(error.message);
    } finally {
      $('loadingOverlay').classList.add('hidden');
    }
  }

  function setDiscovery(active, step = 0) {
    const labels = ['Understanding event', 'Finding venue', 'Discovering transport', 'Routing demand', 'Estimating climate + costs', 'Ranking plans'];
    const progress = $('discoveryProgress');
    progress.hidden = !active;
    progress.innerHTML = active ? labels.map((label, index) => `<span>${index <= step ? '✓' : '·'} ${label}</span>`).join('') : '';
    $('briefSubmit').disabled = active;
    $('loadingTitle').textContent = active ? labels[Math.min(step, labels.length - 1)] : 'Building the event plan';
    $('loadingDetail').textContent = active ? 'Public sources are cached so repeat runs are faster.' : 'Routing demand · testing portfolios · pricing operations';
  }

  async function loadBrief(prompt) {
    $('loadingOverlay').classList.remove('hidden');
    setDiscovery(true, 0);
    let step = 0;
    const ticker = window.setInterval(() => { step = Math.min(5, step + 1); setDiscovery(true, step); }, 1600);
    try {
      state.payload = await api('/api/v3/brief', { method: 'POST', body: JSON.stringify({ prompt, online: true }) });
      state.selectedPlanId = state.payload.recommended_plan_id;
      state.timeIndex = 4;
      state.focusRouteIndex = 0;
      renderEventContext();
      renderPlanCards();
      renderSelectedSummary();
      buildMapLayers();
      updateTime(4);
      renderRoutesView();
      renderCities();
      renderEvidence();
      renderAssumptions();
      $('eventSelect').value = '';
      setDiscovery(true, 5);
    } catch (error) {
      showError(error.message);
    } finally {
      window.clearInterval(ticker);
      window.setTimeout(() => setDiscovery(false), 900);
      $('loadingOverlay').classList.add('hidden');
    }
  }

  async function init() {
    try {
      initMap();
      bindControls();
      state.catalog = await api('/api/v2/catalog');
      $('eventSelect').innerHTML = '<option value="" disabled>Custom brief active</option>' + state.catalog.events.map((event) => `<option value="${escapeHtml(event.event_id)}">${escapeHtml(event.name)}</option>`).join('');
      $('eventSelect').value = state.catalog.default_event_id;
      await loadPlan(state.catalog.default_event_id);
    } catch (error) {
      $('loadingOverlay').classList.add('hidden');
      showError(error.message);
    }
  }

  window.addEventListener('DOMContentLoaded', init);
})();
