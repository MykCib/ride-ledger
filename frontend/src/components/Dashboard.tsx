import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getInsights, getRoutes, getWorkouts } from '../api';
import { clearDetailCache, prefetchDetail } from '../detailCache';
import { useWorkoutDetail } from '../hooks/useWorkoutDetail';
import { formatSpeed, formatTime, formatWorkoutTitle } from '../format';
import type { Insights, RouteOverlay, TrackPoint, WorkoutDetail, WorkoutSummary } from '../types';
import { AllRoutesMap, RouteMap } from './Maps';
import { SegmentChart, SpeedChart, WeeklyChart } from './Charts';

const weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

interface HeaderProps {
  count: number;
  updated: string | null;
  loading: boolean;
  onRefresh: () => void;
}

function Header({ count, updated, loading, onRefresh }: HeaderProps) {
  const updatedText = updated ? `${count} rides · updated ${new Date(updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Loading rides';
  return (
    <header className="topbar">
      <div className="brand"><span className="brand-mark">R</span><span>RIDE LEDGER</span></div>
      <div className="top-meta"><span className="live-dot" /><span>{updatedText}</span><button type="button" onClick={onRefresh} disabled={loading}>Refresh</button></div>
    </header>
  );
}

function Intro() {
  return (
    <section className="intro">
      <div><p className="eyebrow">PERSONAL ROUTE ARCHIVE</p><h1>Every ride,<br /><em>mapped.</em></h1></div>
      <p className="intro-copy">A quiet record of the roads between here and there. Select a ride to inspect the route, pace, and numbers.</p>
    </section>
  );
}

function Stats({ rides }: { rides: WorkoutSummary[] }) {
  const totalKm = rides.reduce((sum, ride) => sum + (ride.distance_km || 0), 0);
  const totalHours = rides.reduce((sum, ride) => sum + (ride.moving_seconds || 0), 0) / 3600;
  const values: Array<[string, string | number]> = [
    ['RIDES', rides.length],
    ['DISTANCE', `${totalKm.toFixed(1)} km`],
    ['MOVING TIME', `${totalHours.toFixed(1)} h`],
    ['AVG RIDE', `${(totalKm / Math.max(rides.length, 1)).toFixed(1)} km`],
  ];
  return <section className="stats">{values.map(([label, value]) => <div className="stat" key={label}><div className="stat-label">{label}</div><div className="stat-value">{value}</div></div>)}</section>;
}

function AllRoutesSection({ routes }: { routes: RouteOverlay[] }) {
  return (
    <section className="all-routes">
      <div className="section-head"><h2>All routes</h2><span>OVERLAY · EVERY WORKOUT</span></div>
      <AllRoutesMap routes={routes} />
      <p className="chart-note">Repeated roads become darker as rides overlap.</p>
    </section>
  );
}

function InsightsSection({ insights }: { insights: Insights | null }) {
  const segments = insights?.segments ?? [];
  const weekdayCounts = insights?.weekday_counts ?? [];
  const busiest = weekdayCounts.length ? weekdayCounts.indexOf(Math.max(...weekdayCounts)) : -1;
  return (
    <section className="insights">
      <div className="chart-card">
        <div className="section-head"><h2>Route segments</h2><span>AVERAGE SPEED · ROUTE PROGRESS</span></div>
        <div className="chart-wrap"><SegmentChart values={segments} /></div>
        <p className="chart-note">Each ride is split into ten equal distance segments. This shows where your repeated route tends to slow down or open up.</p>
      </div>
      <div className="insight-card">
        {insights && <>
          <p className="eyebrow">PATTERNS IN THE ARCHIVE</p>
          <div className="insight-row"><span>Most common day</span><b>{weekdays[busiest] || '—'}</b></div>
          <div className="insight-row"><span>Fastest average</span><b>{insights.fastest ? `${(insights.fastest.average_speed_kmh ?? 0).toFixed(1)} km/h` : '—'}</b></div>
          <div className="insight-row"><span>Longest ride</span><b>{insights.longest ? `${(insights.longest.distance_km ?? 0).toFixed(1)} km` : '—'}</b></div>
        </>}
      </div>
    </section>
  );
}

function RideList({ rides, selectedId }: { rides: WorkoutSummary[]; selectedId: string | undefined }) {
  return (
    <div className="ride-list-wrap">
      <div className="section-head"><h2>Workouts</h2><span>{rides.length} FILES</span></div>
      <div className="ride-list">
        {rides.map((ride) => {
          const date = ride.date ? new Date(ride.date) : null;
          return (
            <Link
              className={`ride${selectedId === ride.id ? ' active' : ''}`}
              data-id={ride.id}
              key={ride.id}
              to={`/rides/${ride.id}`}
              aria-current={selectedId === ride.id ? 'page' : undefined}
              onPointerEnter={() => prefetchDetail(ride.id)}
              onFocus={() => prefetchDetail(ride.id)}
              onKeyDown={(event) => {
                if (event.key === ' ') {
                  event.preventDefault();
                  event.currentTarget.click();
                }
              }}
            >
              <div className="ride-date"><strong>{date ? String(date.getDate()).padStart(2, '0') : '—'}</strong>{date ? date.toLocaleDateString(undefined, { month: 'short' }).toUpperCase() : ''}</div>
              <div><div className="ride-title">{formatWorkoutTitle(ride.date)}</div><div className="ride-sub">{formatTime(ride.moving_seconds)}</div></div>
              <div className="ride-distance">{(ride.distance_km || 0).toFixed(1)}<small> km</small></div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function DetailStats({ ride }: { ride: WorkoutDetail }) {
  const stats: Array<[string, string | number]> = [
    ['Moving time', formatTime(ride.moving_seconds)],
    ['Average speed', formatSpeed(ride.average_speed_kmh)],
    ['Top speed', formatSpeed(ride.max_speed_kmh)],
    ['Ascent', `${ride.ascent_m ?? '—'} m`],
    ['Descent', `${ride.descent_m ?? '—'} m`],
    ['Calories', ride.calories ?? '—'],
  ];
  if (ride.weather) {
    stats.push(
      ['Weather temp', `${ride.weather.temperature_c ?? '—'}°C`],
      ['Feels like', `${ride.weather.feels_like_c ?? '—'}°C`],
      ['Wind', `${ride.weather.wind_kmh ?? '—'} km/h`],
      ['Precipitation', `${ride.weather.precipitation_mm ?? '—'} mm`],
    );
  }
  return <div className="detail-grid">{stats.map(([label, value]) => <div className="detail-stat" key={label}><span className="detail-stat-label">{label}</span><b>{value}</b></div>)}</div>;
}

function DetailPanel({ selectedId, ride, loading, error }: { selectedId: string | undefined; ride: WorkoutDetail | null; loading: boolean; error: Error | null }) {
  const [highlight, setHighlight] = useState<{ rideId: string; point: TrackPoint } | null>(null);
  const detailRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!ride || selectedId !== ride.id || !window.matchMedia('(max-width: 800px)').matches) return;
    detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [ride?.id, selectedId]);

  if (!ride) {
    return (
      <aside ref={detailRef} className="detail">
        <div className="empty-state"><span className="empty-icon">+</span><h2>{loading ? 'Loading workout' : 'Select a workout'}</h2><p>{error?.message || 'Your route and ride details will appear here.'}</p></div>
      </aside>
    );
  }

  const highlightedPoint = highlight?.rideId === ride.id ? highlight.point : null;
  const fullDate = ride.date ? new Date(ride.date).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
  const isLoadingNewRide = loading && selectedId !== ride.id;
  return (
    <aside ref={detailRef} className="detail">
      <div className="detail-view">
        {isLoadingNewRide && <div className="detail-loading" aria-live="polite">Loading workout...</div>}
        <div className="detail-head"><div><p>WORKOUT</p><h2>{fullDate}</h2></div><div className="ride-distance">{(ride.distance_km || 0).toFixed(2)} km</div></div>
        <RouteMap track={ride.track} highlightedPoint={highlightedPoint} />
        <div className="speed-chart"><div className="section-head"><h2>Average speed</h2><span>KM/H · OVER TIME</span></div><div className="chart-wrap"><SpeedChart track={ride.track} onPointHover={(point) => setHighlight(point ? { rideId: ride.id, point } : null)} /></div></div>
        <DetailStats ride={ride} />
        <p className="route-note">{ride.points.toLocaleString()} GPS points · {ride.temperature_c ?? '—'}°C computer temperature · {ride.weather ? 'Historical weather from Open-Meteo' : 'Weather data is being collected for this ride'} · {ride.file}</p>
      </div>
      {error && <p className="route-note">Could not load selected workout: {error.message}</p>}
    </aside>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { rideId } = useParams<{ rideId: string }>();
  const [rides, setRides] = useState<WorkoutSummary[]>([]);
  const [updated, setUpdated] = useState<string | null>(null);
  const [loadingRides, setLoadingRides] = useState(true);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [routes, setRoutes] = useState<RouteOverlay[]>([]);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [overviewError, setOverviewError] = useState<Error | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingRides(true);
    setLoadError(null);
    getWorkouts(controller.signal)
      .then((data) => {
        setRides(data.workouts);
        setUpdated(data.updated);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) setLoadError(error instanceof Error ? error : new Error('Could not load workouts'));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingRides(false);
      });
    return () => controller.abort();
  }, [refreshKey]);

  const validRideId = rideId && rides.some((ride) => ride.id === rideId) ? rideId : undefined;
  const selectedId = validRideId || rides[0]?.id;
  useEffect(() => {
    if (rides.length && !validRideId) navigate(`/rides/${rides[0].id}`, { replace: true });
  }, [rides, validRideId, navigate]);

  const detailState = useWorkoutDetail(selectedId, refreshKey);
  const overviewVersion = useRef(-1);
  useEffect(() => {
    if (!rides.length || !detailState.data || detailState.data.id !== selectedId || detailState.loading || overviewVersion.current === refreshKey) return;
    const controller = new AbortController();
    let active = true;
    setOverviewError(null);
    Promise.all([getRoutes(controller.signal), getInsights(controller.signal)])
      .then(([routeData, insightData]) => {
        if (!active) return;
        overviewVersion.current = refreshKey;
        setRoutes(routeData.routes);
        setInsights(insightData);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) setOverviewError(error instanceof Error ? error : new Error('Could not load overview data'));
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [detailState.data, detailState.loading, refreshKey, rides.length, selectedId]);

  const handleRefresh = () => {
    if (loadingRides) return;
    clearDetailCache();
    setRefreshKey((value) => value + 1);
  };

  return (
    <>
      <Header count={rides.length} updated={updated} loading={loadingRides} onRefresh={handleRefresh} />
      <main className="shell">
        <Intro />
        {loadError ? <p className="route-note">{loadError.message}</p> : <>
          <Stats rides={rides} />
          <AllRoutesSection routes={routes} />
          <section className="overview-charts"><div className="chart-card"><div className="section-head"><h2>Distance by week</h2><span>KM</span></div><div className="chart-wrap"><WeeklyChart items={rides} /></div></div></section>
          <InsightsSection insights={insights} />
          {overviewError && <p className="route-note">{overviewError.message}</p>}
          <section className="content-grid">
            <RideList rides={rides} selectedId={selectedId} />
            <DetailPanel selectedId={selectedId} ride={detailState.data} loading={detailState.loading} error={detailState.error} />
          </section>
        </>}
      </main>
    </>
  );
}

export function App() {
  return <DashboardPage />;
}
