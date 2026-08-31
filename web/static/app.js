let rides = [];
let map;
let route;
let startMarker;
let endMarker;
let speedMarker;
let overviewMap;
let overviewLayers = [];
let selectedId;
let selectionRequest = 0;

const detailCache = new Map();
const detailRequests = new Map();
const $ = (id) => document.getElementById(id);
const fmtDate = (value) => new Date(value).toLocaleDateString(undefined, {weekday:'short', month:'short', day:'numeric', year:'numeric'});
const fmtTime = (seconds) => { if (!seconds) return '—'; const h=Math.floor(seconds/3600), m=Math.floor(seconds%3600/60); return h ? `${h}h ${String(m).padStart(2,'0')}m` : `${m} min`; };
const fmtSpeed = (value) => value == null ? '—' : `${value.toFixed(1)} km/h`;

function detail(id) {
  if (detailCache.has(id)) return Promise.resolve(detailCache.get(id));
  if (!detailRequests.has(id)) {
    const request = fetch(`/api/workouts/${id}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Workout request failed (${response.status})`);
        return response.json();
      })
      .then((data) => {
        detailCache.set(id, data);
        return data;
      })
      .finally(() => detailRequests.delete(id));
    detailRequests.set(id, request);
  }
  return detailRequests.get(id);
}

function preloadDetail(id) {
  detail(id).catch(() => {});
}

async function load() {
  const response = await fetch('/api/workouts');
  if (!response.ok) throw new Error(`Workout list request failed (${response.status})`);
  const data = await response.json();
  rides = data.workouts;
  detailCache.clear();
  $('last-updated').textContent = `${data.count} rides · updated ${new Date(data.updated).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`;
  $('ride-count').textContent = `${data.count} FILES`;
  const totalKm = rides.reduce((sum, ride) => sum + (ride.distance_km || 0), 0);
  const totalHours = rides.reduce((sum, ride) => sum + (ride.moving_seconds || 0), 0) / 3600;
  $('stats').innerHTML = [['RIDES', data.count], ['DISTANCE', `${totalKm.toFixed(1)} km`], ['MOVING TIME', `${totalHours.toFixed(1)} h`], ['AVG RIDE', `${(totalKm / Math.max(data.count,1)).toFixed(1)} km`]].map(([label,value]) => `<div class="stat"><div class="stat-label">${label}</div><div class="stat-value">${value}</div></div>`).join('');
  drawWeeklyChart(rides);

  const currentId = selectedId && rides.some((ride) => ride.id === selectedId) ? selectedId : rides[0]?.id;
  const list = $('ride-list');
  list.innerHTML = rides.map((ride) => {
    const date = new Date(ride.date);
    return `<article class="ride" data-id="${ride.id}" tabindex="0"><div class="ride-date"><strong>${String(date.getDate()).padStart(2,'0')}</strong>${date.toLocaleDateString(undefined,{month:'short'}).toUpperCase()}</div><div><div class="ride-title">${date.toLocaleString(undefined,{month:'short',day:'numeric',year:'numeric',hour:'2-digit',minute:'2-digit'})}</div><div class="ride-sub">${fmtTime(ride.moving_seconds)}</div></div><div class="ride-distance">${(ride.distance_km || 0).toFixed(1)}<small> km</small></div></article>`;
  }).join('');
  list.onclick = (event) => {
    const element = event.target.closest('.ride');
    if (element && list.contains(element)) select(element.dataset.id);
  };
  list.onkeydown = (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const element = event.target.closest('.ride');
    if (element && list.contains(element)) {
      event.preventDefault();
      select(element.dataset.id);
    }
  };
  list.querySelectorAll('.ride').forEach((element) => {
    element.addEventListener('pointerenter', () => preloadDetail(element.dataset.id), {once:true});
    element.addEventListener('focus', () => preloadDetail(element.dataset.id), {once:true});
  });

  if (currentId) await select(currentId);
  loadOverviewData();
}

async function select(id) {
  selectedId = id;
  const request = ++selectionRequest;
  document.querySelectorAll('.ride').forEach((element) => element.classList.toggle('active', element.dataset.id === id));
  try {
    const ride = await detail(id);
    if (request !== selectionRequest) return;
    renderDetail(ride);
  } catch (error) {
    if (request === selectionRequest) $('route-note').textContent = `Could not load this workout: ${error.message}`;
  }
}

function renderDetail(ride) {
  const fullDate = new Date(ride.date).toLocaleString(undefined,{weekday:'short',month:'short',day:'numeric',year:'numeric',hour:'2-digit',minute:'2-digit'});
  const weather = ride.weather;
  const stats = [
    ['Moving time', fmtTime(ride.moving_seconds)],
    ['Average speed', fmtSpeed(ride.average_speed_kmh)],
    ['Top speed', fmtSpeed(ride.max_speed_kmh)],
    ['Ascent', `${ride.ascent_m ?? '—'} m`],
    ['Descent', `${ride.descent_m ?? '—'} m`],
    ['Calories', ride.calories ?? '—'],
  ];
  if (weather) {
    stats.push(
      ['Weather temp', `${weather.temperature_c}°C`],
      ['Feels like', `${weather.feels_like_c}°C`],
      ['Wind', `${weather.wind_kmh} km/h`],
      ['Precipitation', `${weather.precipitation_mm} mm`],
    );
  }
  $('detail-date').textContent = fullDate;
  $('detail-distance').textContent = `${(ride.distance_km || 0).toFixed(2)} km`;
  $('detail-stats').innerHTML = stats.map(([label, value]) => `<div class="detail-stat"><label>${label}</label><b>${value}</b></div>`).join('');
  $('route-note').textContent = `${ride.points.toLocaleString()} GPS points · ${ride.temperature_c ?? '—'}°C computer temperature · ${weather ? 'Historical weather from Open-Meteo' : 'Weather data is being collected for this ride'} · ${ride.file}`;
  $('empty-detail').hidden = true;
  $('detail-content').hidden = false;

  updateMap(ride.track);
  drawSpeedChart(ride.track);
  if (window.matchMedia('(max-width: 800px)').matches && selectedId === ride.id) {
    $('detail').scrollIntoView({behavior:'smooth', block:'start'});
  }
}

function ensureMap() {
  if (map) {
    map.invalidateSize({pan:false});
    return;
  }
  map = L.map('map', {zoomControl:false});
  L.control.zoom({position:'bottomright'}).addTo(map);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution:'© OpenStreetMap contributors'}).addTo(map);
  route = L.polyline([], {color:'#4d6b38', weight:4, opacity:.9}).addTo(map);
  startMarker = L.circleMarker([0, 0], {radius:6, color:'#26332e', fillColor:'#c8e66a', fillOpacity:1}).addTo(map);
  endMarker = L.circleMarker([0, 0], {radius:6, color:'#26332e', fillColor:'#fff', fillOpacity:1}).addTo(map);
}

function updateMap(track) {
  ensureMap();
  if (speedMarker) {
    map.removeLayer(speedMarker);
    speedMarker = null;
  }
  if (!track.length) {
    route.setLatLngs([]);
    return;
  }
  const stride = Math.max(1, Math.ceil(track.length / 1200));
  const points = track.filter((_, index) => index % stride === 0 || index === track.length - 1).map((point) => [point.lat, point.lon]);
  route.setLatLngs(points);
  startMarker.setLatLng(points[0]);
  endMarker.setLatLng(points[points.length - 1]);
  map.fitBounds(route.getBounds(), {padding:[20,20]});
}

function drawLine(canvas, values, labels, fill, onPointHover = null) {
  if (canvas._chart) {
    const chart = canvas._chart;
    chart.data.labels = labels;
    chart.data.datasets[0].data = values;
    chart.data.datasets[0].backgroundColor = fill;
    chart.options.onHover = (event, elements) => { if (onPointHover) onPointHover(elements.length ? elements[0].index : null); };
    chart.update('none');
    return;
  }
  canvas._chart = new Chart(canvas, {type:'line', data:{labels, datasets:[{data:values, borderColor:'#4d6b38', backgroundColor:fill, fill:true, borderWidth:2, pointRadius:3, pointHoverRadius:7, pointHitRadius:14, tension:.25}]}, options:{responsive:true, maintainAspectRatio:false, interaction:{mode:'index', intersect:false}, onHover:(event, elements)=>{if(onPointHover) onPointHover(elements.length ? elements[0].index : null)}, plugins:{legend:{display:false}, tooltip:{displayColors:false, callbacks:{label:(context)=>`${context.parsed.y.toFixed(1)} · ${context.label}`}}}, scales:{x:{grid:{display:false},ticks:{maxTicksLimit:8,color:'#77817c',font:{family:'DM Mono',size:10}}},y:{beginAtZero:true,grid:{color:'#dce2dc'},ticks:{color:'#77817c',font:{family:'DM Mono',size:10}}}}}});
}

function drawWeeklyChart(items) {
  const weeks = {};
  items.forEach((ride) => { const date=new Date(ride.date), day=(date.getDay()+6)%7; date.setDate(date.getDate()-day); const key=date.toISOString().slice(0,10); weeks[key]=(weeks[key]||0)+(ride.distance_km||0); });
  const keys=Object.keys(weeks).sort(); drawLine($('weekly-chart'),keys.map(k=>weeks[k]),keys.map(k=>k.slice(5)), 'rgba(200,230,106,.48)');
}

function drawSegmentChart(values) {
  const valid = values.map(value => value || 0);
  drawLine($('segment-chart'), valid, valid.map((_, i) => `${i * 10}%`), 'rgba(200,230,106,.35)');
}

function drawAllRoutes(routes) {
  const allPoints = routes.flatMap((routeData) => routeData.points);
  if (!allPoints.length) return;
  if (!overviewMap) {
    overviewMap = L.map('all-map', {zoomControl:false}).setView(allPoints[0], 13);
    L.control.zoom({position:'bottomright'}).addTo(overviewMap);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution:'© OpenStreetMap contributors'}).addTo(overviewMap);
  } else {
    overviewMap.invalidateSize({pan:false});
  }
  overviewLayers.forEach((layer) => overviewMap.removeLayer(layer));
  overviewLayers = [];
  const bounds = L.latLngBounds([]);
  routes.forEach((routeData) => {
    const line=L.polyline(routeData.points, {color:'#d45b3f', weight:3, opacity:.42, lineCap:'round', lineJoin:'round'}).addTo(overviewMap);
    overviewLayers.push(line);
    bounds.extend(line.getBounds());
  });
  overviewMap.fitBounds(bounds, {padding:[24,24]});
}

function drawSpeedChart(track) {
  const valid = track.map((point,index)=>({point,index})).filter((sample)=>sample.point.speed != null);
  const stride = Math.max(1, Math.ceil(valid.length / 100));
  const samples = valid.filter((_, index) => index % stride === 0);
  drawLine($('speed-chart'),samples.map(sample=>sample.point.speed*3.6),samples.map(sample=>sample.point.t ? new Date(sample.point.t).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ''),'rgba(200,230,106,.35)', (index) => {
    if (index == null || !map) { if (speedMarker && map) map.removeLayer(speedMarker); speedMarker = null; return; }
    const point = samples[index].point;
    if (!speedMarker) speedMarker = L.circleMarker([point.lat, point.lon], {radius:8, color:'#18221f', weight:3, fillColor:'#c8e66a', fillOpacity:1}).addTo(map);
    else speedMarker.setLatLng([point.lat, point.lon]);
    speedMarker.bindTooltip(`${(point.speed * 3.6).toFixed(1)} km/h`, {permanent:false}).openTooltip();
  });
}

function loadOverviewData() {
  fetch('/api/routes').then((response) => response.json()).then((data) => drawAllRoutes(data.routes)).catch(() => {});
  fetch('/api/insights').then((response) => response.json()).then((insights) => {
    drawSegmentChart(insights.segments);
    const busiest = insights.weekday_counts.indexOf(Math.max(...insights.weekday_counts));
    const weekday = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][busiest];
    $('insight-card').innerHTML = `<p class="eyebrow">PATTERNS IN THE ARCHIVE</p><div class="insight-row"><span>Most common day</span><b>${weekday}</b></div><div class="insight-row"><span>Fastest average</span><b>${insights.fastest ? insights.fastest.average_speed_kmh.toFixed(1)+' km/h' : '—'}</b></div><div class="insight-row"><span>Longest ride</span><b>${insights.longest ? insights.longest.distance_km.toFixed(1)+' km' : '—'}</b></div>`;
  }).catch(() => {});
}

$('refresh').addEventListener('click', () => load().catch((error) => { $('ride-list').innerHTML = `<p>Could not load workouts: ${error}</p>`; }));
load().catch((error) => { $('ride-list').innerHTML = `<p>Could not load workouts: ${error}</p>`; });
