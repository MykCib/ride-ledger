let rides = [];
let map;
let route;
let speedMarker;

const $ = (id) => document.getElementById(id);
const fmtDate = (value) => new Date(value).toLocaleDateString(undefined, {weekday:'short', month:'short', day:'numeric', year:'numeric'});
const fmtTime = (seconds) => { if (!seconds) return '—'; const h=Math.floor(seconds/3600), m=Math.floor(seconds%3600/60); return h ? `${h}h ${String(m).padStart(2,'0')}m` : `${m} min`; };
const fmtSpeed = (value) => value == null ? '—' : `${value.toFixed(1)} km/h`;

async function load() {
  const response = await fetch('/api/workouts');
  const data = await response.json();
  rides = data.workouts;
  $('last-updated').textContent = `${data.count} rides · updated ${new Date(data.updated).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`;
  $('ride-count').textContent = `${data.count} FILES`;
  const totalKm = rides.reduce((sum, ride) => sum + (ride.distance_km || 0), 0);
  const totalHours = rides.reduce((sum, ride) => sum + (ride.moving_seconds || 0), 0) / 3600;
  $('stats').innerHTML = [['RIDES', data.count], ['DISTANCE', `${totalKm.toFixed(1)} km`], ['MOVING TIME', `${totalHours.toFixed(1)} h`], ['AVG RIDE', `${(totalKm / Math.max(data.count,1)).toFixed(1)} km`]].map(([label,value]) => `<div class="stat"><div class="stat-label">${label}</div><div class="stat-value">${value}</div></div>`).join('');
  drawWeeklyChart(rides);
  fetch('/api/routes').then(response => response.json()).then(data => drawAllRoutes(data.routes));
  $('ride-list').innerHTML = rides.map((ride) => { const date = new Date(ride.date); return `<article class="ride" data-id="${ride.id}"><div class="ride-date"><strong>${String(date.getDate()).padStart(2,'0')}</strong>${date.toLocaleDateString(undefined,{month:'short'}).toUpperCase()}</div><div><div class="ride-title">${date.toLocaleString(undefined,{month:'short',day:'numeric',year:'numeric',hour:'2-digit',minute:'2-digit'})}</div><div class="ride-sub">${fmtTime(ride.moving_seconds)}</div></div><div class="ride-distance">${(ride.distance_km || 0).toFixed(1)}<small> km</small></div></article>`; }).join('');
  document.querySelectorAll('.ride').forEach((element) => element.addEventListener('click', () => select(element.dataset.id)));
  if (rides.length && !$('detail').querySelector('.detail-head')) select(rides[0].id);
  fetch('/api/insights').then(response => response.json()).then(insights => {
    drawSegmentChart(insights.segments);
    const busiest = insights.weekday_counts.indexOf(Math.max(...insights.weekday_counts));
    const weekday = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][busiest];
    $('insight-card').innerHTML = `<p class="eyebrow">PATTERNS IN THE ARCHIVE</p><div class="insight-row"><span>Most common day</span><b>${weekday}</b></div><div class="insight-row"><span>Fastest average</span><b>${insights.fastest ? insights.fastest.average_speed_kmh.toFixed(1)+' km/h' : '—'}</b></div><div class="insight-row"><span>Longest ride</span><b>${insights.longest ? insights.longest.distance_km.toFixed(1)+' km' : '—'}</b></div>`;
  });
}

async function select(id) {
  document.querySelectorAll('.ride').forEach((element) => element.classList.toggle('active', element.dataset.id === id));
  const ride = await (await fetch(`/api/workouts/${id}`)).json();
  if (map) { map.remove(); map = null; }
  speedMarker = null;
  const fullDate = new Date(ride.date).toLocaleString(undefined,{weekday:'short',month:'short',day:'numeric',year:'numeric',hour:'2-digit',minute:'2-digit'});
  const weatherCards = ride.weather ? `<div class="detail-stat"><label>Weather temp</label><b>${ride.weather.temperature_c}°C</b></div><div class="detail-stat"><label>Feels like</label><b>${ride.weather.feels_like_c}°C</b></div><div class="detail-stat"><label>Wind</label><b>${ride.weather.wind_kmh} km/h</b></div><div class="detail-stat"><label>Precipitation</label><b>${ride.weather.precipitation_mm} mm</b></div>` : '';
  const weatherNote = ride.weather ? 'Historical weather from Open-Meteo' : 'Weather data is being collected for this ride';
  $('detail').innerHTML = `<div class="detail-head"><div><p>WORKOUT</p><h2>${fullDate}</h2></div><div class="ride-distance">${(ride.distance_km || 0).toFixed(2)} km</div></div><div id="map" class="map"></div><div class="speed-chart"><div class="section-head"><h2>Average speed</h2><span>KM/H · OVER TIME</span></div><div class="chart-wrap"><canvas id="speed-chart"></canvas></div></div><div class="detail-grid"><div class="detail-stat"><label>Moving time</label><b>${fmtTime(ride.moving_seconds)}</b></div><div class="detail-stat"><label>Average speed</label><b>${fmtSpeed(ride.average_speed_kmh)}</b></div><div class="detail-stat"><label>Top speed</label><b>${fmtSpeed(ride.max_speed_kmh)}</b></div><div class="detail-stat"><label>Ascent</label><b>${ride.ascent_m ?? '—'} m</b></div><div class="detail-stat"><label>Descent</label><b>${ride.descent_m ?? '—'} m</b></div><div class="detail-stat"><label>Calories</label><b>${ride.calories ?? '—'}</b></div>${weatherCards}</div><p class="route-note">${ride.points.toLocaleString()} GPS points · ${ride.temperature_c ?? '—'}°C computer temperature · ${weatherNote} · ${ride.file}</p>`;
  drawSpeedChart(ride.track);
  if (!ride.track.length) return;
  const points = ride.track.map((point) => [point.lat, point.lon]);
  map = L.map('map', {zoomControl:false}).setView(points[0], 13);
  L.control.zoom({position:'bottomright'}).addTo(map);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution:'© OpenStreetMap contributors'}).addTo(map);
  route = L.polyline(points, {color:'#4d6b38', weight:4, opacity:.9}).addTo(map);
  L.circleMarker(points[0], {radius:6, color:'#26332e', fillColor:'#c8e66a', fillOpacity:1}).addTo(map);
  L.circleMarker(points[points.length-1], {radius:6, color:'#26332e', fillColor:'#fff', fillOpacity:1}).addTo(map);
  map.fitBounds(route.getBounds(), {padding:[20,20]});
  if (window.matchMedia('(max-width: 800px)').matches) {
    $('detail').scrollIntoView({behavior:'smooth', block:'start'});
  }
}

function drawLine(canvas, values, labels, fill, onPointHover = null) {
  if (canvas._chart) canvas._chart.destroy();
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
  const allPoints = routes.flatMap(route => route.points);
  if (!allPoints.length) return;
  const overviewMap = L.map('all-map', {zoomControl:false}).setView(allPoints[0], 13);
  L.control.zoom({position:'bottomright'}).addTo(overviewMap);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution:'© OpenStreetMap contributors'}).addTo(overviewMap);
  const bounds = L.latLngBounds([]);
  routes.forEach(routeData => { const line=L.polyline(routeData.points, {color:'#d45b3f', weight:3, opacity:.42, lineCap:'round', lineJoin:'round'}).addTo(overviewMap); bounds.extend(line.getBounds()); });
  overviewMap.fitBounds(bounds, {padding:[24,24]});
}

function drawSpeedChart(track) {
  const samples=track.map((point,index)=>({point,index})).filter(sample=>sample.point.speed != null).filter((_,i,a)=>i % Math.max(1,Math.ceil(a.length/100))===0);
  drawLine($('speed-chart'),samples.map(sample=>sample.point.speed*3.6),samples.map(sample=>sample.point.t ? new Date(sample.point.t).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ''),'rgba(200,230,106,.35)', (index) => {
    if (index == null || !map) { if (speedMarker && map) map.removeLayer(speedMarker); speedMarker = null; return; }
    const point = samples[index].point;
    if (!speedMarker) speedMarker = L.circleMarker([point.lat, point.lon], {radius:8, color:'#18221f', weight:3, fillColor:'#c8e66a', fillOpacity:1}).addTo(map);
    else speedMarker.setLatLng([point.lat, point.lon]);
    speedMarker.bindTooltip(`${(point.speed * 3.6).toFixed(1)} km/h`, {permanent:false}).openTooltip();
  });
}

$('refresh').addEventListener('click', load);
load().catch((error) => { $('ride-list').innerHTML = `<p>Could not load workouts: ${error}</p>`; });
