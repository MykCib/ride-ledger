import { useEffect, useRef, useState, type ReactNode, type SyntheticEvent } from 'react';
import { Link, NavLink, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { getCommutes, getInsights, getRoutes, getSegments, getWeather, getWorkouts, renameCommuteLocation } from '../api';
import { clearDetailCache, prefetchDetail } from '../detailCache';
import { useWorkoutDetail } from '../hooks/useWorkoutDetail';
import { formatClock, formatDuration, formatSpeed, formatTime, formatVerticalRate, formatWorkoutTitle } from '../format';
import type { CommuteAnalysis, Insights, PeriodSummary, RouteAssignment, RouteDirection, RouteGroup, RouteOverlay, SegmentAnalysis, TrackPoint, WeatherAnalysis, WeatherSummary, WorkoutDetail, WorkoutSummary } from '../types';
import { AllRoutesMap, RouteMap } from './Maps';
import { BarChart, ElevationChart, SegmentChart, SpeedChart, WeeklyChart } from './Charts';
import { CommuteSection } from './Commutes';
import { SegmentsSection } from './Segments';
import { ActivitySection } from './Activity';
import { WeatherSection } from './Weather';

const weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const emptyAssignments: Record<string, RouteAssignment> = {};
const weekdayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const weekdayFormatters = new Map<string, Intl.DateTimeFormat>();
const dateFormatters = new Map<string, Intl.DateTimeFormat>();

function rideWeekday(date: string, timezone: string): number {
  let formatter = weekdayFormatters.get(timezone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: timezone });
    weekdayFormatters.set(timezone, formatter);
  }
  return weekdayNames.indexOf(formatter.format(new Date(date)));
}

function rideDateKey(date: string, timezone: string): string {
  let formatter = dateFormatters.get(timezone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-US', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: timezone });
    dateFormatters.set(timezone, formatter);
  }
  const parts = Object.fromEntries(formatter.formatToParts(new Date(date)).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function archiveSearch(search: string): string {
  const params = new URLSearchParams(search);
  params.delete('chapter');
  const value = params.toString();
  return value ? `?${value}` : '';
}

interface HeaderProps {
  count: number;
  updated: string | null;
  dataUpdated: string | null;
  loading: boolean;
  notice: string | null;
  onRefresh: () => void;
}

function Header({ count, updated, dataUpdated, loading, notice, onRefresh }: HeaderProps) {
  const checkedText = updated ? `checked ${new Date(updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'loading archive';
  const dataText = dataUpdated ? `files ${new Date(dataUpdated).toLocaleDateString([], { month: 'short', day: 'numeric' })}` : null;
  return (
    <header className="topbar">
      <div className="brand"><span className="brand-mark">R</span><span>RIDE LEDGER</span></div>
      <div className="top-meta">
        <span className="live-dot" aria-hidden="true" />
        <span>{count} rides · {checkedText}</span>
        {dataText && <span className="data-updated" title={new Date(dataUpdated || '').toLocaleString()}>· {dataText}</span>}
        {notice && <span className="sync-notice" role="status">{notice}</span>}
        <button type="button" onClick={onRefresh} disabled={loading} aria-label={loading ? 'Refreshing archive' : 'Refresh archive'}>{loading ? 'Checking' : 'Refresh'}</button>
      </div>
    </header>
  );
}

function Navigation({ ridesSearch }: { ridesSearch: string }) {
  return (
    <nav className="main-nav" aria-label="Main navigation">
      <NavLink end to="/" className={({ isActive }) => isActive ? 'active' : undefined}>Overview</NavLink>
      <NavLink to={{ pathname: '/rides', search: ridesSearch }} className={({ isActive }) => isActive ? 'active' : undefined}>Rides</NavLink>
      <NavLink to="/routes" className={({ isActive }) => isActive ? 'active' : undefined}>Routes</NavLink>
      <NavLink to="/insights" className={({ isActive }) => isActive ? 'active' : undefined}>Insights</NavLink>
    </nav>
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

type DashboardPageName = 'overview' | 'rides' | 'routes' | 'insights';
type AnalyticsErrorKey = 'directions' | 'routes' | 'segments' | 'insights' | 'weather';
type AnalyticsErrors = Partial<Record<AnalyticsErrorKey, string>>;

function PageIntro({ page }: { page: DashboardPageName }) {
  if (page === 'overview') return <Intro />;
  const copy = {
    rides: { eyebrow: 'THE RIDE ARCHIVE', title: 'Ride archive', copy: 'Browse every workout, then open one for its route and metrics.', action: 'Browse workouts', target: '#ride-list' },
    routes: { eyebrow: 'ROUTE NOTEBOOK', title: 'Route notebook', copy: 'The roads you return to, grouped by direction and distance.', action: 'Start with the map', target: '#route-explorer' },
    insights: { eyebrow: 'PATTERNS IN THE ARCHIVE', title: 'Archive insights', copy: 'Weather, activity, and pace patterns across the full archive.', action: 'Open highlights', target: '#insight-highlights' },
  }[page];
  return (
    <section className="page-header">
      <div><p className="eyebrow">{copy.eyebrow}</p><h1>{copy.title}</h1></div>
      <div className="page-header-side"><p className="page-header-copy">{copy.copy}</p><a className="page-header-action" href={copy.target}>{copy.action} <b>-&gt;</b></a></div>
    </section>
  );
}

function LoadingState({ label }: { label: string }) {
  return <div className="loading-state" role="status"><span className="loading-line" /><strong>{label}</strong><p>Useful data will appear here as the archive is read.</p></div>;
}

function AnalyticsErrorNotice({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="inline-error" role="alert"><span>{message}</span><button type="button" onClick={onRetry}>Retry</button></div>;
}

function DeferredContent({ children }: { children: ReactNode }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !('IntersectionObserver' in window)) {
      setReady(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      setReady(true);
      observer.disconnect();
    }, { rootMargin: '400px 0px' });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  return <div ref={containerRef} className="deferred-content">{ready ? children : <div className="deferred-placeholder" aria-hidden="true" />}</div>;
}

function Stats({ rides }: { rides: WorkoutSummary[] }) {
  const totalKm = rides.reduce((sum, ride) => sum + (ride.distance_km || 0), 0);
  const totalHours = rides.reduce((sum, ride) => sum + (ride.moving_seconds || 0), 0) / 3600;
  const stoppedHours = rides.reduce((sum, ride) => sum + (ride.estimated_stopped_seconds || 0), 0) / 3600;
  const values: Array<[string, string | number]> = [
    ['RIDES', rides.length],
    ['DISTANCE', `${totalKm.toFixed(1)} km`],
    ['MOVING TIME', `${totalHours.toFixed(1)} h`],
    ['STOPPED TIME', `${stoppedHours.toFixed(1)} h`],
    ['AVG RIDE', `${(totalKm / Math.max(rides.length, 1)).toFixed(1)} km`],
  ];
  return <section className="stats">{values.map(([label, value]) => <div className="stat" key={label}><div className="stat-label">{label}</div><div className="stat-value">{value}</div></div>)}</section>;
}

function OverviewLinks({ rides, routeCount }: { rides: WorkoutSummary[]; routeCount: number }) {
  return (
    <section className="overview-links">
      <Link className="overview-link" to="/rides">
        <p className="eyebrow">RIDE ARCHIVE</p>
        <h2>{rides.length ? `${rides.length} workouts` : 'Open the archive'}</h2>
        <p>Search the archive, filter by route or weather, and inspect any workout in detail.</p>
        <span>Browse rides <b>-&gt;</b></span>
      </Link>
      <Link className="overview-link overview-link-dark" to="/routes">
        <p className="eyebrow">ROUTE NOTEBOOK</p>
        <h2>{routeCount} repeated route{routeCount === 1 ? '' : 's'}</h2>
        <p>See the roads together, compare directions, and inspect repeated sections.</p>
        <span>Explore routes <b>-&gt;</b></span>
      </Link>
      <Link className="overview-link" to="/insights">
        <p className="eyebrow">ARCHIVE SIGNALS</p>
        <h2>Patterns, not noise.</h2>
        <p>Weather, weekday, departure, and pace patterns live on the insights page.</p>
        <span>View insights <b>-&gt;</b></span>
      </Link>
    </section>
  );
}

function LatestRide({ ride }: { ride: WorkoutSummary | undefined }) {
  if (!ride) {
    return <section className="latest-ride"><div className="data-empty"><strong>No rides in the archive yet.</strong><p>Download a FIT workout to make the latest ride available here.</p></div></section>;
  }
  return (
    <section className="latest-ride">
      <div className="section-head"><h2>Latest ride</h2><span>READY TO INSPECT</span></div>
      <Link className="latest-ride-link" to={`/rides/${ride.id}`}>
        <div className="latest-ride-title"><p className="eyebrow">{formatWorkoutTitle(ride.date)}</p><h3>{ride.file}</h3><span>{ride.data_quality?.status === 'warning' ? 'Review data quality checks' : 'Complete workout record'}</span></div>
        <div className="latest-ride-metrics"><div><span>Distance</span><strong>{ride.distance_km == null ? '—' : `${ride.distance_km.toFixed(1)} km`}</strong></div><div><span>Average speed</span><strong>{formatSpeed(ride.average_speed_kmh)}</strong></div><div><span>Moving time</span><strong>{formatTime(ride.moving_seconds)}</strong></div><b className="latest-ride-action">Open ride -&gt;</b></div>
      </Link>
    </section>
  );
}

function RecentHighlights({ rides, title = 'Recent rides' }: { rides: WorkoutSummary[]; title?: string }) {
  const recent = rides.slice(0, 3);
  return (
    <section className="recent-highlights">
      <div className="section-head"><h2>{title}</h2><Link to="/rides">Open archive <b>-&gt;</b></Link></div>
      {recent.length ? (
        <div className="recent-highlight-list">
          {recent.map((ride) => (
            <Link className="recent-highlight" to={`/rides/${ride.id}`} key={ride.id}>
              <span className="recent-highlight-date">{formatWorkoutTitle(ride.date)}</span>
               <strong>{ride.distance_km == null ? '—' : `${ride.distance_km.toFixed(1)} km`}</strong>
              <span>{formatSpeed(ride.average_speed_kmh)}</span>
              {ride.data_quality?.status === 'warning' && <span className="quality-badge">Review data</span>}
              <b className="recent-highlight-arrow">-&gt;</b>
            </Link>
          ))}
        </div>
      ) : (
        <p className="empty-copy">No dated rides are available yet.</p>
      )}
    </section>
  );
}

type RouteMapLayer = 'overlay' | 'density' | 'speed' | 'elevation';

interface AllRoutesSectionProps {
  routes: RouteOverlay[];
  rides: WorkoutSummary[];
  groups: RouteGroup[];
  selectedGroupId: string | null;
  selectedRouteId: string | null;
  onSelectGroup: (groupId: string | null) => void;
  onSelectRoute: (routeId: string | null) => void;
}

function AllRoutesSection({ routes, rides, groups, selectedGroupId, selectedRouteId, onSelectGroup, onSelectRoute, error, onRetry }: AllRoutesSectionProps & { error?: string; onRetry: () => void }) {
  const [layer, setLayer] = useState<RouteMapLayer>('overlay');
  const selectedGroup = groups.find((group) => group.id === selectedGroupId) ?? null;
  const selectedRide = selectedRouteId ? rides.find((ride) => ride.id === selectedRouteId) : null;
  const focusRouteIds = selectedGroup ? [...selectedGroup.outbound.ride_ids, ...selectedGroup.return.ride_ids] : undefined;
  const focusRouteSet = focusRouteIds ? new Set(focusRouteIds) : null;
  const routeGroupByRide = new Map<string, RouteGroup>();
  groups.forEach((group) => [...group.outbound.ride_ids, ...group.return.ride_ids].forEach((rideId) => routeGroupByRide.set(rideId, group)));
  const selectedRouteGroup = selectedRouteId ? routeGroupByRide.get(selectedRouteId) : undefined;
  const selectedDirection = selectedRouteId && selectedRouteGroup
    ? selectedRouteGroup.outbound.ride_ids.includes(selectedRouteId) ? 'outbound' : selectedRouteGroup.return.ride_ids.includes(selectedRouteId) ? 'return' : null
    : null;
  const metricValues = routes.reduce<number[]>((values, route) => {
    if (focusRouteSet && !focusRouteSet.has(route.id)) return values;
    (route.samples ?? []).forEach((sample) => {
      const value = layer === 'speed' ? sample.speed_kmh : sample.elevation_m;
      if (value != null && Number.isFinite(value)) values.push(value);
    });
    return values;
  }, []);
  const metric = layer === 'speed' ? 'speed' : layer === 'elevation' ? 'elevation' : null;
  const metricRange = metricValues.length ? { min: Math.min(...metricValues), max: Math.max(...metricValues) } : null;
  const hasRouteTracks = routes.some((route) => route.points.length > 1);
  const handleRouteSelect = (routeId: string | null) => {
    if (!routeId) {
      onSelectRoute(null);
      return;
    }
    const group = routeGroupByRide.get(routeId);
    onSelectGroup(group?.id ?? null);
    onSelectRoute(routeId);
  };
  return (
    <section className="all-routes" id="route-explorer">
      <div className="section-head"><h2>Route explorer</h2><span>{routes.length} TRACKS</span></div>
      <div className="route-map-controls">
        <label className="route-focus-field">Focus route
          <select value={selectedGroupId ?? ''} onChange={(event) => {
            onSelectGroup(event.currentTarget.value || null);
            onSelectRoute(null);
          }}>
            <option value="">All repeated routes</option>
            {groups.map((group) => <option value={group.id} key={group.id}>{group.label} · {group.total_rides} rides</option>)}
          </select>
        </label>
        <div className="map-layer-toggle" role="group" aria-label="Route map layer">
        <button type="button" className={layer === 'overlay' ? 'active' : ''} aria-pressed={layer === 'overlay'} onClick={() => setLayer('overlay')}>All routes</button>
        <button type="button" className={layer === 'density' ? 'active' : ''} aria-pressed={layer === 'density'} onClick={() => setLayer('density')}>Density</button>
          <button type="button" className={layer === 'speed' ? 'active' : ''} aria-pressed={layer === 'speed'} onClick={() => setLayer('speed')}>Speed</button>
          <button type="button" className={layer === 'elevation' ? 'active' : ''} aria-pressed={layer === 'elevation'} onClick={() => setLayer('elevation')}>Elevation</button>
        </div>
      </div>
      {error && <AnalyticsErrorNotice message={error} onRetry={onRetry} />}
      {hasRouteTracks ? <AllRoutesMap routes={routes} mode={layer} focusRouteKey={focusRouteIds?.join('|')} selectedRouteId={selectedRouteId} onSelectRoute={handleRouteSelect} /> : <div className="data-empty"><strong>No route tracks are available.</strong><p>Valid GPS tracks will appear here after the route index is rebuilt.</p></div>}
      {metric && metricRange && <div className="route-metric-legend" aria-label={`${metric} map legend`}>
        <span>Low {metric === 'speed' ? `${metricRange.min.toFixed(1)} km/h` : `${metricRange.min.toFixed(0)} m`}</span>
        <i aria-hidden="true" />
        <span>High {metric === 'speed' ? `${metricRange.max.toFixed(1)} km/h` : `${metricRange.max.toFixed(0)} m`}</span>
      </div>}
      {selectedRide ? (
        <div className="route-selection" aria-live="polite"><span>Selected ride · {selectedRouteGroup?.label ?? 'Unassigned route'}{selectedDirection ? ` · ${selectedDirection}` : ''} · {formatWorkoutTitle(selectedRide.date)} · {formatSpeed(selectedRide.average_speed_kmh)}{selectedRide.weather && ` · ${selectedRide.weather.temperature_c ?? '—'}°C`}</span><Link to={`/rides/${selectedRide.id}`}>Open ride <b>-&gt;</b></Link></div>
      ) : selectedGroup ? (
        <div className="route-selection" aria-live="polite"><span>{selectedGroup.label} · {selectedGroup.total_rides} rides selected</span><button type="button" onClick={() => { onSelectGroup(null); onSelectRoute(null); }}>Clear focus</button></div>
      ) : <p className="chart-note">Click a track to inspect one ride. Speed and elevation layers include a low-to-high legend; group colors remain available in the route notebook below.</p>}
    </section>
  );
}

function InsightsSection({ insights, error, onRetry }: { insights: Insights | null; error?: string; onRetry: () => void }) {
  if (!insights) return error ? <section className="insights"><div className="data-empty"><strong>Performance insights could not be loaded.</strong><p>Try again after the archive has finished indexing.</p><AnalyticsErrorNotice message={error} onRetry={onRetry} /></div></section> : null;
  const segments = insights?.segments ?? [];
  const weekdayCounts = insights?.weekday_counts ?? [];
  const busiest = weekdayCounts.length ? weekdayCounts.indexOf(Math.max(...weekdayCounts)) : -1;
  return (
    <section className="insights">
      {error && <AnalyticsErrorNotice message={error} onRetry={onRetry} />}
      <div className="chart-card">
        <div className="section-head"><h2>Route segments</h2><span>AVERAGE SPEED · ROUTE PROGRESS</span></div>
        <div className="chart-wrap"><SegmentChart values={segments} /></div>
        <p className="chart-note">Each ride is split into ten equal distance segments. This shows where your repeated route tends to slow down or open up.</p>
      </div>
      <div className="insight-card">
        {insights && <>
          <p className="eyebrow">PATTERNS IN THE ARCHIVE</p>
          <div className="insight-row"><span>Most common day</span><b>{weekdays[busiest] || '—'}</b></div>
           <div className="insight-row"><span>Fastest average</span><b>{insights.fastest ? formatSpeed(insights.fastest.average_speed_kmh) : '—'}</b></div>
           <div className="insight-row"><span>Longest ride</span><b>{insights.longest?.distance_km == null ? '—' : `${insights.longest.distance_km.toFixed(1)} km`}</b></div>
        </>}
      </div>
    </section>
  );
}

function InsightHighlights({ insights, weather }: { insights: Insights; weather: WeatherAnalysis | null }) {
  const availableRecords = insights.fastest_sections.filter((section) => section.ride_id).length;
  const activeDays = insights.calendar.filter((day) => day.ride_count > 0).length;
  const recentPeriods = (insights.monthly_summary ?? []).slice(-2);
  const recentChange = recentPeriods.length === 2 && recentPeriods[0].distance_km != null && recentPeriods[1].distance_km != null
    ? `${recentPeriods[1].distance_km - recentPeriods[0].distance_km >= 0 ? '+' : ''}${(recentPeriods[1].distance_km - recentPeriods[0].distance_km).toFixed(1)} km`
    : '—';
  const values: Array<[string, string, string]> = [
    ['Fastest average', insights.fastest ? formatSpeed(insights.fastest.average_speed_kmh) : '—', 'archive pace'],
    ['Longest ride', insights.longest?.distance_km == null ? '—' : `${insights.longest.distance_km.toFixed(1)} km`, 'single workout'],
    ['Recent change', recentChange, recentPeriods.length === 2 ? `${recentPeriods[0].label} to ${recentPeriods[1].label}` : 'monthly distance'],
    ['Rolling records', `${availableRecords}/3`, '1, 2, and 5 km'],
  ];
  return (
    <section className="insight-highlights" id="insight-highlights">
      <div className="section-head"><h2>Highlights</h2><span>{activeDays} ACTIVE DAYS · {weather ? `${weather.available_rides}/${weather.total_rides} WEATHER LINKED` : 'WEATHER PENDING'}</span></div>
      <div className="highlight-grid">
        {values.map(([label, value, note]) => <article className="highlight" key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}
      </div>
    </section>
  );
}

function PeriodSummaryTable({ periods, label }: { periods: PeriodSummary[]; label: string }) {
  const visible = [...periods].reverse().slice(0, 12);
  return (
    <div className="period-summary-block">
      <div className="section-head"><h3>{label} summary</h3><span>{periods.length} PERIODS</span></div>
      {visible.length ? <div className="period-summary-scroll"><table className="period-summary-table"><caption>{label} ride summary</caption><thead><tr className="period-summary-heading"><th scope="col">Period</th><th scope="col">Rides</th><th scope="col">Distance</th><th scope="col">Moving</th><th scope="col">Avg speed</th></tr></thead><tbody>
        {visible.map((period) => <tr className="period-summary-row" key={period.period}>
          <th scope="row">{period.label}</th>
          <td data-label="Rides">{period.ride_count}</td>
          <td data-label="Distance">{period.distance_km == null ? '—' : `${period.distance_km.toFixed(1)} km`}</td>
          <td data-label="Moving">{formatTime(period.moving_seconds)}</td>
          <td data-label="Avg speed">{formatSpeed(period.average_speed_kmh)}</td>
        </tr>)}
      </tbody></table></div> : <p className="empty-copy">No dated rides are available for this summary.</p>}
      {periods.length > visible.length && <p className="chart-note">Showing the latest {visible.length} periods.</p>}
    </div>
  );
}

function ArchiveSummaries({ insights }: { insights: Insights }) {
  const [period, setPeriod] = useState<'month' | 'year'>('month');
  const periods = period === 'month' ? (insights.monthly_summary ?? []) : (insights.yearly_summary ?? []);
  return (
    <section className="archive-summaries">
      <div className="section-head"><h2>Archive summaries</h2><span>LOCAL TIME · {insights.timezone}</span></div>
      <div className="summary-toggle" role="group" aria-label="Summary period">
        <button type="button" className={period === 'month' ? 'active' : ''} aria-pressed={period === 'month'} onClick={() => setPeriod('month')}>Monthly</button>
        <button type="button" className={period === 'year' ? 'active' : ''} aria-pressed={period === 'year'} onClick={() => setPeriod('year')}>Yearly</button>
      </div>
      <PeriodSummaryTable periods={periods} label={period === 'month' ? 'Monthly' : 'Yearly'} />
    </section>
  );
}

function PerformanceSection({ insights }: { insights: Insights }) {
  return (
    <section className="performance-analysis">
      <div className="performance-records">
        <div className="section-head"><h2>Fastest rolling sections</h2><span>ARCHIVE RECORDS</span></div>
        <p className="chart-note performance-note">Best elapsed time over exactly 1, 2, and 5 km windows. The source ride links to its full route.</p>
        <div className="performance-record-grid">
          {insights.fastest_sections.map((section) => {
            const hasRecord = section.time_seconds != null && section.ride_id;
            return (
              <article className={`performance-record${hasRecord ? '' : ' performance-record-empty'}`} key={section.distance_km}>
                <p className="eyebrow">{section.distance_km} KM SECTION</p>
                {hasRecord ? <>
                  <strong>{formatDuration(section.time_seconds)}</strong>
                  <span>{formatSpeed(section.speed_kmh)}</span>
                  {section.start_km != null && section.end_km != null && <small>{section.start_km.toFixed(2)} - {section.end_km.toFixed(2)} km in the ride</small>}
                  <Link className="record-ride" to={`/rides/${section.ride_id}`}>{formatWorkoutTitle(section.date)} <b>-&gt;</b></Link>
                </> : <p>No complete section in the archive yet.</p>}
              </article>
            );
          })}
        </div>
      </div>
      <div className="chart-card speed-distribution">
        <div className="section-head"><h2>Speed distribution</h2><span>KM/H · RECORDED SAMPLES</span></div>
        {insights.speed_distribution.length ? <div className="chart-wrap"><BarChart values={insights.speed_distribution.map((bin) => bin.point_count)} labels={insights.speed_distribution.map((bin) => bin.label)} fill="rgba(77,107,56,.68)" /></div> : <p className="weather-empty">No valid speed samples yet.</p>}
        <p className="chart-note">Each bar counts recorded speed samples; with one-second FIT records this approximates time spent at each pace.</p>
      </div>
    </section>
  );
}

interface RideFilters {
  search: string;
  from: string;
  to: string;
  weekday: string;
  direction: 'all' | RouteDirection;
  weather: 'all' | 'dry' | 'wet' | 'available';
  minDistance: string;
  maxDistance: string;
  sort: 'date' | 'speed' | 'distance' | 'duration';
}

const defaultRideFilters: RideFilters = {
  search: '',
  from: '',
  to: '',
  weekday: 'all',
  direction: 'all',
  weather: 'all',
  minDistance: '',
  maxDistance: '',
  sort: 'date',
};

const rideFilterParams = ['q', 'from', 'to', 'weekday', 'direction', 'weather', 'min', 'max', 'sort'];

function filtersFromSearchParams(params: URLSearchParams): RideFilters {
  const direction = params.get('direction');
  const weather = params.get('weather');
  const sort = params.get('sort');
  const numeric = (key: string) => {
    const value = params.get(key);
    return value && Number.isFinite(Number(value)) && Number(value) >= 0 ? value : '';
  };
  const weekday = params.get('weekday');
  return {
    search: params.get('q') ?? '',
    from: params.get('from') ?? '',
    to: params.get('to') ?? '',
    weekday: weekday && ['0', '1', '2', '3', '4', '5', '6'].includes(weekday) ? weekday : 'all',
    direction: direction === 'outbound' || direction === 'return' || direction === 'loop' ? direction : 'all',
    weather: weather === 'dry' || weather === 'wet' || weather === 'available' ? weather : 'all',
    minDistance: numeric('min'),
    maxDistance: numeric('max'),
    sort: sort === 'speed' || sort === 'distance' || sort === 'duration' ? sort : 'date',
  };
}

function updateRideSearchParams(current: URLSearchParams, filters: RideFilters): URLSearchParams {
  const next = new URLSearchParams(current);
  rideFilterParams.forEach((key) => next.delete(key));
  const values: Array<[string, string, string]> = [
    ['q', filters.search.trim(), ''],
    ['from', filters.from, ''],
    ['to', filters.to, ''],
    ['weekday', filters.weekday, 'all'],
    ['direction', filters.direction, 'all'],
    ['weather', filters.weather, 'all'],
    ['min', filters.minDistance, ''],
    ['max', filters.maxDistance, ''],
    ['sort', filters.sort, 'date'],
  ];
  values.forEach(([key, value, defaultValue]) => {
    if (value !== defaultValue && value !== '') next.set(key, value);
  });
  return next;
}

function hasActiveRideFilter(filters: RideFilters): boolean {
  return Object.entries(filters).some(([field, value]) => field === 'sort' ? value !== 'date' : value !== '' && value !== 'all');
}

function rideFilterSummary(filters: RideFilters): string[] {
  const summary: string[] = [];
  if (filters.search) summary.push(`search: ${filters.search}`);
  if (filters.from || filters.to) summary.push(`${filters.from || 'any'} to ${filters.to || 'any'}`);
  if (filters.weekday !== 'all') summary.push(['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][Number(filters.weekday)] ?? 'weekday');
  if (filters.direction !== 'all') summary.push(filters.direction);
  if (filters.weather !== 'all') summary.push(filters.weather === 'available' ? 'weather linked' : `${filters.weather} weather`);
  if (filters.minDistance || filters.maxDistance) summary.push(`${filters.minDistance || '0'}-${filters.maxDistance || 'any'} km`);
  if (filters.sort !== 'date') summary.push(filters.sort === 'speed' ? 'fastest first' : filters.sort === 'distance' ? 'longest first' : 'most moving time');
  return summary;
}

function filterRides(rides: WorkoutSummary[], filters: RideFilters, assignments: Record<string, RouteAssignment>, timezone = 'Europe/Vilnius'): WorkoutSummary[] {
  const search = filters.search.trim().toLowerCase();
  const filtered = rides.filter((ride) => {
    const assignment = assignments[ride.id];
    const haystack = [ride.id, ride.file, ride.date, assignment?.label, assignment?.direction].join(' ').toLowerCase();
    if (search && !haystack.includes(search)) return false;
    const date = ride.date ? rideDateKey(ride.date, timezone) : '';
    if (filters.from && (!date || date < filters.from)) return false;
    if (filters.to && (!date || date > filters.to)) return false;
    if (filters.weekday !== 'all' && ride.date) {
      const weekday = rideWeekday(ride.date, timezone);
      if (weekday !== Number(filters.weekday)) return false;
    }
    if (filters.weekday !== 'all' && !ride.date) return false;
    if (filters.direction !== 'all' && assignment?.direction !== filters.direction) return false;
    if (filters.weather === 'available' && !ride.weather) return false;
    if (filters.weather === 'dry' && ride.weather?.precipitation_mm !== 0) return false;
    if (filters.weather === 'wet' && !(ride.weather?.precipitation_mm != null && ride.weather.precipitation_mm > 0)) return false;
    const distance = ride.distance_km;
    const minimum = filters.minDistance === '' ? null : Number(filters.minDistance);
    const maximum = filters.maxDistance === '' ? null : Number(filters.maxDistance);
    if (minimum != null && (distance == null || distance < minimum)) return false;
    if (maximum != null && (distance == null || distance > maximum)) return false;
    return true;
  });
  return [...filtered].sort((first, second) => {
    const values = {
      date: (ride: WorkoutSummary) => ride.date ? Date.parse(ride.date) : -Infinity,
      speed: (ride: WorkoutSummary) => ride.average_speed_kmh ?? -Infinity,
      distance: (ride: WorkoutSummary) => ride.distance_km ?? -Infinity,
      duration: (ride: WorkoutSummary) => ride.moving_seconds ?? -Infinity,
    };
    return values[filters.sort](second) - values[filters.sort](first);
  });
}

function RideFilters({ filters, dates, directions, resultCount, totalCount, onChange, onReset }: { filters: RideFilters; dates: string[]; directions: RouteDirection[]; resultCount: number; totalCount: number; onChange: (next: RideFilters) => void; onReset: () => void }) {
  const [expanded, setExpanded] = useState(() => hasActiveRideFilter(filters) || (typeof window !== 'undefined' && window.matchMedia('(min-width: 801px)').matches));
  const update = <K extends keyof RideFilters>(field: K, value: RideFilters[K]) => onChange({ ...filters, [field]: value });
  const summary = rideFilterSummary(filters);
  return (
    <div className="ride-filters">
      <div className="filter-bar">
        <label className="filter-field filter-search">Search<input type="search" value={filters.search} onChange={(event) => update('search', event.currentTarget.value)} placeholder="Date, file, or route" /></label>
        <button type="button" className="filter-toggle" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>{expanded ? 'Hide filters' : 'More filters'}{summary.length ? ` · ${summary.length}` : ''}</button>
        {summary.length > 0 && <button type="button" className="filter-clear" onClick={onReset}>Clear all</button>}
      </div>
      {summary.length > 0 && <div className="active-filters" aria-label="Active filters">{summary.map((item) => <span key={item}>{item}</span>)}</div>}
      {expanded && <div className="filter-grid">
        <label className="filter-field">From<input type="date" min={dates[0]} max={dates[dates.length - 1]} value={filters.from} onChange={(event) => update('from', event.currentTarget.value)} /></label>
        <label className="filter-field">To<input type="date" min={dates[0]} max={dates[dates.length - 1]} value={filters.to} onChange={(event) => update('to', event.currentTarget.value)} /></label>
        <label className="filter-field">Weekday<select value={filters.weekday} onChange={(event) => update('weekday', event.currentTarget.value)}><option value="all">All days</option><option value="1">Monday</option><option value="2">Tuesday</option><option value="3">Wednesday</option><option value="4">Thursday</option><option value="5">Friday</option><option value="6">Saturday</option><option value="0">Sunday</option></select></label>
        <label className="filter-field">Direction<select value={filters.direction} onChange={(event) => update('direction', event.currentTarget.value as RideFilters['direction'])}><option value="all">All directions</option>{directions.map((direction) => <option value={direction} key={direction}>{direction}</option>)}</select></label>
        <label className="filter-field">Weather<select value={filters.weather} onChange={(event) => update('weather', event.currentTarget.value as RideFilters['weather'])}><option value="all">All conditions</option><option value="available">Weather linked</option><option value="dry">Dry rides</option><option value="wet">Wet rides</option></select></label>
        <label className="filter-field">Min km<input type="number" min="0" step="0.1" value={filters.minDistance} onChange={(event) => update('minDistance', event.currentTarget.value)} /></label>
        <label className="filter-field">Max km<input type="number" min="0" step="0.1" value={filters.maxDistance} onChange={(event) => update('maxDistance', event.currentTarget.value)} /></label>
        <label className="filter-field">Sort<select value={filters.sort} onChange={(event) => update('sort', event.currentTarget.value as RideFilters['sort'])}><option value="date">Newest first</option><option value="speed">Fastest first</option><option value="distance">Longest first</option><option value="duration">Most moving time</option></select></label>
        <button type="button" className="filter-reset" onClick={onReset} disabled={!hasActiveRideFilter(filters)}>Reset</button>
      </div>
      }
      <p className="filter-result" aria-live="polite">Showing {resultCount} of {totalCount} workouts</p>
    </div>
  );
}

function RideList({ rides, totalRides, selectedId, assignments, filters, allDates, directions, locationSearch, directionsError, onRetry, onFiltersChange, onFiltersReset }: { rides: WorkoutSummary[]; totalRides: number; selectedId: string | undefined; assignments: Record<string, RouteAssignment>; filters: RideFilters; allDates: string[]; directions: RouteDirection[]; locationSearch: string; directionsError?: string; onRetry: () => void; onFiltersChange: (filters: RideFilters) => void; onFiltersReset: () => void }) {
  return (
    <div className="ride-list-wrap" id="ride-list">
      <div className="section-head"><h2>Workouts</h2><span>{rides.length}/{totalRides} FILES</span></div>
      {directionsError && <AnalyticsErrorNotice message={directionsError} onRetry={onRetry} />}
      <RideFilters filters={filters} dates={allDates} directions={directions} resultCount={rides.length} totalCount={totalRides} onChange={onFiltersChange} onReset={onFiltersReset} />
      <div className="ride-list">
        {rides.length ? rides.map((ride) => {
          const date = ride.date ? new Date(ride.date) : null;
          const assignment = assignments[ride.id];
          return (
            <Link
              className={`ride${selectedId === ride.id ? ' active' : ''}`}
              data-id={ride.id}
              key={ride.id}
              to={`/rides/${ride.id}${locationSearch}`}
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
              <div><div className="ride-route-label">{assignment?.label ?? 'Unassigned route'}</div><div className="ride-title">{formatWorkoutTitle(ride.date)}</div><div className="ride-sub">{formatTime(ride.moving_seconds)}{assignment && <span className={`direction-tag ${assignment.direction}`}>{assignment.direction}</span>}{ride.weather && <span className="weather-badge">{ride.weather.precipitation_mm == null ? 'linked' : ride.weather.precipitation_mm > 0 ? 'wet' : 'dry'}</span>}{ride.data_quality?.status === 'warning' && <span className="quality-badge">{ride.data_quality.warning_count} QUALITY</span>}</div></div>
               <div className="ride-distance">{ride.distance_km == null ? '—' : <>{ride.distance_km.toFixed(1)}<small> km</small></>}</div>
            </Link>
          );
        }) : <div className="ride-empty"><span>No workouts match these filters.</span>{hasActiveRideFilter(filters) && <button type="button" onClick={onFiltersReset}>Clear filters</button>}</div>}
      </div>
    </div>
  );
}

function PrimaryDetailStats({ ride }: { ride: WorkoutDetail }) {
  const stats: Array<[string, string]> = [
    ['Distance', ride.distance_km == null ? '—' : `${ride.distance_km.toFixed(2)} km`],
    ['Average speed', formatSpeed(ride.average_speed_kmh)],
    ['Moving time', formatTime(ride.moving_seconds)],
    ['Elapsed time', formatTime(ride.elapsed_seconds)],
  ];
  return <div className="detail-primary-stats">{stats.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>;
}

function DetailStats({ ride }: { ride: WorkoutDetail }) {
  const stats: Array<[string, string | number]> = [
    ['Moving time', formatTime(ride.moving_seconds)],
    ['Elapsed time', formatTime(ride.elapsed_seconds)],
    ['Estimated stopped', formatDuration(ride.estimated_stopped_seconds)],
    ['Moving share', ride.moving_percent == null ? '—' : `${ride.moving_percent.toFixed(1)}%`],
    ['Stops', ride.stop_count],
    ['Longest stop', formatDuration(ride.longest_stop_seconds)],
    ['Average speed', formatSpeed(ride.average_speed_kmh)],
    ['Top speed', formatSpeed(ride.max_speed_kmh)],
    ['Ascent', `${ride.ascent_m ?? '—'} m`],
    ['Descent', `${ride.descent_m ?? '—'} m`],
    ['Climbing rate', formatVerticalRate(ride.climbing_rate_m_per_hour)],
    ['Descent rate', formatVerticalRate(ride.descent_rate_m_per_hour)],
    ['Calories', ride.calories ?? '—'],
  ];
  return <div className="detail-grid">{stats.map(([label, value]) => <div className="detail-stat" key={label}><span className="detail-stat-label">{label}</span><b>{value}</b></div>)}</div>;
}

function DetailWeather({ weather }: { weather: WeatherSummary }) {
  const values: Array<[string, string]> = [
    ['Temperature', `${weather.temperature_c ?? '—'}°C`],
    ['Feels like', `${weather.feels_like_c ?? '—'}°C`],
    ['Wind', `${weather.wind_kmh ?? '—'} km/h`],
    ['Precipitation', `${weather.precipitation_mm ?? '—'} mm`],
  ];
  return <div className="detail-weather">{values.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>;
}

const CLOSED_CHAPTER = 'none';

function DetailChapter({ id, title, label, defaultOpen = false, children }: { id: string; title: string; label: string; defaultOpen?: boolean; children: ReactNode }) {
  const [chapterParams, setChapterParams] = useSearchParams();
  const chapter = chapterParams.get('chapter');
  const hasChapter = chapterParams.has('chapter');
  const [open, setOpen] = useState(() => chapter === id || (!hasChapter && defaultOpen));
  const previousChapterRef = useRef(chapter);
  const userToggleRef = useRef(false);
  useEffect(() => {
    if (previousChapterRef.current === chapter) return;
    previousChapterRef.current = chapter;
    setOpen(chapter === id || (!hasChapter && defaultOpen));
  }, [chapter, defaultOpen, hasChapter, id]);
  const setChapterOpen = (nextOpen: boolean) => {
    setOpen(nextOpen);
    setChapterParams((current) => {
      const next = new URLSearchParams(current);
      if (nextOpen) next.set('chapter', id);
      else if (next.get('chapter') === id || !next.has('chapter')) next.set('chapter', CLOSED_CHAPTER);
      return next;
    }, { replace: true });
  };
  const handleToggle = (event: SyntheticEvent<HTMLDetailsElement>) => {
    if (!userToggleRef.current) return;
    userToggleRef.current = false;
    setChapterOpen(event.currentTarget.open);
  };
  return (
    <details className="detail-chapter" open={open} onToggle={handleToggle} onKeyDown={(event) => {
        if (event.key === 'Escape' && open) {
          event.preventDefault();
          setChapterOpen(false);
        }
      }}>
      <summary onClick={() => { userToggleRef.current = true; }}><span><small>{label}</small><strong>{title}</strong></span><b>{open ? 'Hide' : 'Show'}</b></summary>
      {open && <div className="detail-chapter-content">{children}</div>}
    </details>
  );
}

function StopList({ ride }: { ride: WorkoutDetail }) {
  const stops = ride.stops ?? [];
  return (
    <section className="stop-panel">
      <div className="section-head"><h2>Detected stops</h2><span>{ride.stop_count} PAUSES</span></div>
      {stops.length ? (
        <ol className="stop-list">
          {stops.map((stop, index) => (
            <li className="stop-row" key={`${stop.start}-${stop.end}`}>
              <span className="stop-index">{String(index + 1).padStart(2, '0')}</span>
              <span className="stop-time">{formatClock(stop.start)} – {formatClock(stop.end)}</span>
              <b>{formatDuration(stop.duration_seconds)}</b>
            </li>
          ))}
        </ol>
      ) : (
        <p className="stop-empty">No stationary interval of at least five seconds was detected.</p>
      )}
      <p className="chart-note">Stopped time is estimated from the elapsed and moving session timers. Intervals are inferred from timestamp gaps and near-zero-speed samples.</p>
    </section>
  );
}

function QualityPanel({ ride }: { ride: WorkoutDetail }) {
  const quality = ride.data_quality;
  return (
    <section className={`quality-panel ${quality.status}`}>
      <div className="section-head"><h2>Data quality</h2><span>{quality.status === 'ok' ? 'OK' : `${quality.warning_count} CHECK${quality.warning_count === 1 ? '' : 'S'}`}</span></div>
      {quality.warnings.length ? (
        <ul className="quality-list">
          {quality.warnings.map((warning) => <li key={warning.code}><span className="quality-code">{warning.code.replaceAll('_', ' ')}</span><span>{warning.message}</span></li>)}
        </ul>
      ) : <p className="quality-empty">No suspicious gaps, coordinates, speeds, stops, timing, or distance values were detected.</p>}
      <a className="download-link" href={`/api/workouts/${encodeURIComponent(ride.id)}/download`} download={ride.file}>Download original FIT</a>
    </section>
  );
}

function PlaybackControls({ track, weather, index, playing, onToggle, onReset, onSeek }: { track: TrackPoint[]; weather: WeatherSummary | null; index: number | null; playing: boolean; onToggle: () => void; onReset: () => void; onSeek: (index: number) => void }) {
  const point = index == null ? null : track[index] ?? null;
  return (
    <section className="playback-panel">
      <div className="section-head"><h2>Route playback</h2><span>{point ? `${(index ?? 0) + 1}/${track.length}` : 'READY'}</span></div>
      <div className="playback-controls">
        <button type="button" onClick={onToggle} disabled={!track.length}>{playing ? 'Pause' : 'Play'}</button>
        <button type="button" className="playback-reset" onClick={onReset} disabled={index == null}>Reset</button>
        <input type="range" min="0" max={Math.max(track.length - 1, 0)} value={index ?? 0} onChange={(event) => onSeek(Number(event.currentTarget.value))} disabled={!track.length} aria-label="Route playback position" />
      </div>
      <div className="playback-readout">
        <span>{point ? formatClock(point.t) : 'Move through the route'}</span>
        <b>{point ? formatSpeed(point.speed == null ? null : point.speed * 3.6) : '—'}</b>
        <b>{point?.altitude == null ? '—' : `${point.altitude.toFixed(0)} m`}</b>
      </div>
      {weather && <p className="chart-note">Archive weather average: {weather.temperature_c ?? '—'}°C · {weather.wind_kmh ?? '—'} km/h wind · {weather.precipitation_mm ?? '—'} mm rain.</p>}
    </section>
  );
}

function PlaybackMap({ ride, highlightedPoint }: { ride: WorkoutDetail; highlightedPoint: TrackPoint | null }) {
  const [playbackIndex, setPlaybackIndex] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const playbackIndexRef = useRef<number | null>(null);

  const setPlaybackPosition = (index: number | null) => {
    playbackIndexRef.current = index;
    setPlaybackIndex(index);
  };

  useEffect(() => {
    if (!playing || !ride.track.length) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setPlaybackPosition(ride.track.length - 1);
      setPlaying(false);
      return;
    }
    const timer = window.setInterval(() => {
      const next = Math.min((playbackIndexRef.current ?? 0) + 4, ride.track.length - 1);
      setPlaybackPosition(next);
      if (next >= ride.track.length - 1) setPlaying(false);
    }, 250);
    return () => window.clearInterval(timer);
  }, [playing, ride.track.length]);

  const playbackPoint = playbackIndex == null ? null : ride.track[playbackIndex] ?? null;
  return (
    <>
      {ride.track.length ? <RouteMap track={ride.track} highlightedPoint={highlightedPoint} playbackPoint={playbackPoint} /> : <div className="map-empty"><strong>No GPS track is available.</strong><span>The FIT file contains workout metrics but no mappable position records.</span></div>}
      <PlaybackControls
        track={ride.track}
        weather={ride.weather}
        index={playbackIndex}
        playing={playing}
        onToggle={() => {
          if (playing) {
            setPlaying(false);
            return;
          }
          if (playbackIndexRef.current == null || playbackIndexRef.current >= ride.track.length - 1) setPlaybackPosition(0);
          setPlaying(true);
        }}
        onReset={() => {
          setPlaybackPosition(null);
          setPlaying(false);
        }}
        onSeek={(index) => {
          setPlaybackPosition(index);
          setPlaying(false);
        }}
      />
    </>
  );
}

function DetailPanel({ selectedId, ride, loading, error, assignment, returnSearch }: { selectedId: string | undefined; ride: WorkoutDetail | null; loading: boolean; error: Error | null; assignment?: RouteAssignment; returnSearch: string }) {
  const [highlight, setHighlight] = useState<{ rideId: string; point: TrackPoint } | null>(null);
  const detailRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!ride || selectedId !== ride.id || !window.matchMedia('(max-width: 800px)').matches) return;
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
    detailRef.current?.scrollIntoView({ behavior, block: 'start' });
  }, [ride?.id, selectedId]);

  if (!ride || !selectedId || ride.id !== selectedId) {
    return (
      <aside ref={detailRef} className="detail">
        <div className="empty-state" role={error ? 'alert' : 'status'}><span className="empty-icon">+</span><h2>{loading ? 'Loading workout' : error ? 'Could not load workout' : 'Select a workout'}</h2><p>{error?.message || 'Your route and ride details will appear here.'}</p></div>
      </aside>
    );
  }

  const highlightedPoint = highlight?.rideId === ride.id ? highlight.point : null;
  const fullDate = ride.date ? new Date(ride.date).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
  return (
    <aside ref={detailRef} className="detail">
      <div className="detail-view">
        <Link className="back-link" to={`/rides${returnSearch}`}>-&gt; Back to rides</Link>
        <div className="detail-head"><div><p>WORKOUT{assignment && <> · <span className={`direction-tag ${assignment.direction}`}>{assignment.direction}</span>{assignment.group_id && <span className="detail-route-label">{assignment.label}</span>}</>}</p><h2>{fullDate}</h2></div>{ride.data_quality?.status === 'warning' && <span className="quality-badge">{ride.data_quality.warning_count} checks</span>}</div>
        <PrimaryDetailStats ride={ride} />
        <DetailChapter id="route" key={`${ride.id}-route`} title="Route and playback" label="01 · SPATIAL CONTEXT" defaultOpen>
          <PlaybackMap key={ride.id} ride={ride} highlightedPoint={highlightedPoint} />
        </DetailChapter>
        <DetailChapter id="pace" key={`${ride.id}-pace`} title="Pace and speed" label="02 · PERFORMANCE">
          <div className="speed-chart"><div className="section-head"><h2>Average speed</h2><span>KM/H · OVER TIME</span></div><div className="chart-wrap"><SpeedChart track={ride.track} onPointHover={(point) => setHighlight(point ? { rideId: ride.id, point } : null)} /></div></div>
        </DetailChapter>
        <DetailChapter id="elevation" key={`${ride.id}-elevation`} title="Elevation" label="03 · TERRAIN">
          <div className="elevation-chart"><div className="section-head"><h2>Elevation profile</h2><span>METRES · ROUTE PROGRESS</span></div><div className="chart-wrap"><ElevationChart track={ride.track} onPointHover={(point) => setHighlight(point ? { rideId: ride.id, point } : null)} /></div></div>
        </DetailChapter>
        <DetailChapter id="timing" key={`${ride.id}-timing`} title="Timing and effort" label="04 · RIDE METRICS">
          <DetailStats ride={ride} />
          <StopList ride={ride} />
        </DetailChapter>
        <DetailChapter id="weather" key={`${ride.id}-weather`} title="Weather" label="05 · ARCHIVE CONDITIONS">
          {ride.weather ? <><DetailWeather weather={ride.weather} /><p className="chart-note">Historical conditions are matched to the ride start and cached locally from Open-Meteo.</p></> : <p className="empty-copy">Weather has not been cached for this ride yet.</p>}
        </DetailChapter>
        <DetailChapter id="source" key={`${ride.id}-source`} title="Data quality and original file" label="06 · SOURCE">
          <QualityPanel ride={ride} />
          <p className="route-note">{ride.points.toLocaleString()} GPS points · {ride.temperature_c ?? '—'}°C computer temperature · {ride.file}</p>
        </DetailChapter>
       </div>
       {error && <p className="route-note">Could not load selected workout: {error.message}</p>}
    </aside>
  );
}

function OverviewContent({ rides, routeCount, timezone, directionsError, onRetry }: { rides: WorkoutSummary[]; routeCount: number; timezone: string; directionsError?: string; onRetry: () => void }) {
  return (
    <div className="page-stack overview-page-content">
      <LatestRide ride={rides[0]} />
      <Stats rides={rides} />
      <section className="overview-charts"><div className="chart-card"><div className="section-head"><h2>Distance by week</h2><span>KM</span></div><div className="chart-wrap"><WeeklyChart items={rides} timezone={timezone} /></div></div></section>
      {rides.length > 1 && <RecentHighlights rides={rides.slice(1)} title="More recent rides" />}
      {directionsError && <AnalyticsErrorNotice message={directionsError} onRetry={onRetry} />}
      <OverviewLinks rides={rides} routeCount={routeCount} />
    </div>
  );
}

function RoutesContent({ routes, rides, commutes, segments, errors, onRename, onRetry }: { routes: RouteOverlay[]; rides: WorkoutSummary[]; commutes: CommuteAnalysis | null; segments: SegmentAnalysis | null; errors: AnalyticsErrors; onRename: (locationId: string, name: string) => Promise<void>; onRetry: () => void }) {
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  if (!routes.length && !commutes?.groups.length && !segments?.segments.length && !Object.keys(errors).length) {
    return <div className="data-empty"><strong>No repeated route data yet.</strong><p>Routes will appear after the archive contains valid GPS tracks.</p></div>;
  }
  return (
    <div className="page-stack routes-page-content">
      <AllRoutesSection routes={routes} rides={rides} groups={commutes?.groups ?? []} selectedGroupId={selectedGroupId} selectedRouteId={selectedRouteId} error={errors.routes} onRetry={onRetry} onSelectGroup={(groupId) => { setSelectedGroupId(groupId); setSelectedRouteId(null); }} onSelectRoute={setSelectedRouteId} />
      {errors.directions && <AnalyticsErrorNotice message={errors.directions} onRetry={onRetry} />}
      {commutes?.groups.length ? <DeferredContent><CommuteSection timezone={commutes.timezone} groups={commutes.groups} routes={routes} locations={commutes.locations} selectedGroupId={selectedGroupId} onSelectGroup={(groupId) => { setSelectedGroupId(groupId); setSelectedRouteId(null); }} onRename={onRename} /></DeferredContent> : null}
      {(segments?.segments.length || errors.segments) ? <DeferredContent><SegmentsSection segmentCount={segments?.segment_count ?? 0} segments={segments?.segments ?? []} selectedGroupId={selectedGroupId} error={errors.segments} onRetry={onRetry} /></DeferredContent> : null}
    </div>
  );
}

function InsightsContent({ insights, weather, errors, onRetry }: { insights: Insights | null; weather: WeatherAnalysis | null; errors: AnalyticsErrors; onRetry: () => void }) {
  if (!insights && !weather) return <div className="data-empty"><strong>{errors.insights || errors.weather ? 'Archive insights are temporarily unavailable.' : 'No archive insights yet.'}</strong><p>{errors.insights || errors.weather ? 'Try again after the archive has finished indexing.' : 'Insights will appear after at least one dated ride has been indexed.'}</p>{errors.insights && <AnalyticsErrorNotice message={errors.insights} onRetry={onRetry} />}{errors.weather && <AnalyticsErrorNotice message={errors.weather} onRetry={onRetry} />}</div>;
  return (
    <div className="page-stack insights-page-content">
      {insights && <InsightHighlights insights={insights} weather={weather} />}
      <InsightsSection insights={insights} error={errors.insights} onRetry={onRetry} />
      {insights && <PerformanceSection insights={insights} />}
      {(weather || errors.weather) && <DeferredContent><WeatherSection analysis={weather} error={errors.weather} onRetry={onRetry} /></DeferredContent>}
      {insights && <DeferredContent><ActivitySection insights={insights} /></DeferredContent>}
      {insights && <ArchiveSummaries insights={insights} />}
    </div>
  );
}

function RidesContent({ visibleRides, totalRides, selectedId, assignments, filters, allDates, directions, locationSearch, directionsError, onRetry, onFiltersChange, onFiltersReset, detailState, selectedAssignment }: { visibleRides: WorkoutSummary[]; totalRides: number; selectedId: string | undefined; assignments: Record<string, RouteAssignment>; filters: RideFilters; allDates: string[]; directions: RouteDirection[]; locationSearch: string; directionsError?: string; onRetry: () => void; onFiltersChange: (filters: RideFilters) => void; onFiltersReset: () => void; detailState: { data: WorkoutDetail | null; loading: boolean; error: Error | null }; selectedAssignment?: RouteAssignment }) {
  return (
    <div className="content-grid rides-page-content">
      <RideList rides={visibleRides} totalRides={totalRides} selectedId={selectedId} assignments={assignments} filters={filters} allDates={allDates} directions={directions} locationSearch={locationSearch} directionsError={directionsError} onRetry={onRetry} onFiltersChange={onFiltersChange} onFiltersReset={onFiltersReset} />
      <DetailPanel selectedId={selectedId} ride={detailState.data} loading={detailState.loading} error={detailState.error} assignment={selectedAssignment} returnSearch={locationSearch} />
    </div>
  );
}

export function DashboardPage({ page }: { page: DashboardPageName }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { rideId } = useParams<{ rideId: string }>();
  const [rides, setRides] = useState<WorkoutSummary[]>([]);
  const [updated, setUpdated] = useState<string | null>(null);
  const [dataUpdated, setDataUpdated] = useState<string | null>(null);
  const [loadingRides, setLoadingRides] = useState(true);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [routes, setRoutes] = useState<RouteOverlay[]>([]);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [commutes, setCommutes] = useState<CommuteAnalysis | null>(null);
  const [segments, setSegments] = useState<SegmentAnalysis | null>(null);
  const [weather, setWeather] = useState<WeatherAnalysis | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsStarted, setAnalyticsStarted] = useState(false);
  const [analyticsErrors, setAnalyticsErrors] = useState<AnalyticsErrors>({});
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const previousCount = useRef<number | null>(null);
  const previousDataUpdated = useRef<string | null>(null);
  const loadingRidesRef = useRef(true);
  const rideCountRef = useRef(0);

  const filters = filtersFromSearchParams(searchParams);
  const assignments = commutes?.assignments ?? emptyAssignments;
  const analyticsTimezone = commutes?.timezone ?? 'Europe/Vilnius';
  const visibleRides = filterRides(rides, filters, assignments, analyticsTimezone);
  const allDates = [...new Set(rides.flatMap((ride) => ride.date ? [rideDateKey(ride.date, analyticsTimezone)] : []))].sort();
  const directions = [...new Set(Object.values(assignments).map((assignment) => assignment.direction))];

  useEffect(() => {
    rideCountRef.current = rides.length;
  }, [rides.length]);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingRides(true);
    loadingRidesRef.current = true;
    setLoadError(null);
    getWorkouts(controller.signal)
      .then((data) => {
        const previous = previousCount.current;
        if (previous != null && data.count > previous) {
          setSyncNotice(`${data.count - previous} new ride${data.count - previous === 1 ? '' : 's'} found`);
        } else if (previous != null && data.count < previous) {
          setSyncNotice('Archive changed');
        } else if (previousDataUpdated.current !== null && data.data_updated !== previousDataUpdated.current) {
          setSyncNotice('Archive updated');
        } else {
          setSyncNotice(null);
        }
        previousCount.current = data.count;
        previousDataUpdated.current = data.data_updated;
        setRides(data.workouts);
        setUpdated(data.updated);
        setDataUpdated(data.data_updated);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        const message = error instanceof Error ? error.message : 'Could not load workouts';
        if (rideCountRef.current) setSyncNotice(`Refresh failed: ${message}`);
        else setLoadError(new Error(message));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          loadingRidesRef.current = false;
          setLoadingRides(false);
        }
      });
    return () => controller.abort();
  }, [refreshKey]);

  useEffect(() => {
    loadingRidesRef.current = loadingRides;
  }, [loadingRides]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      if (!loadingRidesRef.current) setRefreshKey((value) => value + 1);
    }, 60_000);
    return () => window.clearInterval(interval);
  }, []);

  const validRideId = page === 'rides' && rideId && visibleRides.some((ride) => ride.id === rideId) ? rideId : undefined;
  const selectedId = page === 'rides' ? validRideId || visibleRides[0]?.id : undefined;
  useEffect(() => {
    if (page === 'rides' && visibleRides.length && !validRideId) navigate(`/rides/${visibleRides[0].id}${location.search}`, { replace: true });
  }, [page, visibleRides, validRideId, location.search, navigate]);

  const detailState = useWorkoutDetail(selectedId, refreshKey);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    if (!rides.length) {
      setAnalyticsLoading(false);
      setAnalyticsStarted(false);
      setAnalyticsErrors({});
      return () => { active = false; controller.abort(); };
    }
    setAnalyticsStarted(true);
    setAnalyticsLoading(true);
    setAnalyticsErrors({});
    let pending = 0;
    const errorText = (reason: unknown) => reason instanceof Error ? reason.message : 'request failed';
    const load = <T,>(promise: Promise<T>, key: AnalyticsErrorKey, label: string, onSuccess: (value: T) => void) => {
      pending += 1;
      promise
        .then((value) => {
          if (active) onSuccess(value);
        })
        .catch((error: unknown) => {
          if (active && !(error instanceof DOMException && error.name === 'AbortError')) setAnalyticsErrors((current) => ({ ...current, [key]: `${label}: ${errorText(error)}` }));
        })
        .finally(() => {
          pending -= 1;
          if (active && pending === 0) {
            setAnalyticsLoading(false);
          }
        });
    };

    if (page === 'overview' || page === 'rides') {
      load(getCommutes(controller.signal), 'directions', 'Route directions', setCommutes);
    } else if (page === 'routes') {
      load(getRoutes(controller.signal), 'routes', 'Routes', (data) => setRoutes(data.routes));
      load(getCommutes(controller.signal), 'directions', 'Route directions', setCommutes);
      load(getSegments(controller.signal), 'segments', 'Route segments', setSegments);
    } else {
      load(getInsights(controller.signal), 'insights', 'Insights', setInsights);
      load(getWeather(controller.signal), 'weather', 'Weather analysis', setWeather);
    }

    if (pending === 0) {
      setAnalyticsLoading(false);
    }
    return () => {
      active = false;
      controller.abort();
    };
  }, [page, refreshKey, rides.length]);

  const handleRefresh = () => {
    if (loadingRides) return;
    clearDetailCache();
    setRefreshKey((value) => value + 1);
  };
  const handleRenameLocation = async (locationId: string, name: string) => {
    try {
      const nextCommutes = await renameCommuteLocation(locationId, name);
      setCommutes(nextCommutes);
      setSegments((current) => current ? {
        ...current,
        segments: current.segments.map((segment) => ({
          ...segment,
          label: nextCommutes.groups.find((group) => group.id === segment.group_id)?.label ?? segment.label,
        })),
      } : current);
      setWeather((current) => current ? {
        ...current,
        directions: current.directions.map((direction) => ({
          ...direction,
          label: nextCommutes.groups.find((group) => group.id === direction.group_id)?.label ?? direction.label,
        })),
      } : current);
    } catch (error: unknown) {
      setAnalyticsErrors((current) => ({ ...current, directions: error instanceof Error ? error.message : 'Could not rename location' }));
      throw error;
    }
  };
  const selectedAssignment = selectedId ? commutes?.assignments[selectedId] : undefined;
  const setRideFilters = (next: RideFilters) => setSearchParams((current) => updateRideSearchParams(current, next), { replace: true });
  const resetRideFilters = () => setSearchParams((current) => updateRideSearchParams(current, defaultRideFilters), { replace: true });
  const locationSearch = archiveSearch(location.search);
  const routeReady = routes.length > 0 || commutes !== null || segments !== null;
  const insightsReady = insights !== null || weather !== null;
  const pageLoading = loadingRides && !rides.length;
  const loadingLabel = page === 'routes' ? 'Loading route notebook' : page === 'insights' ? 'Loading archive insights' : 'Loading archive';
  const ridesSearch = locationSearch;
  const routeDataPending = page === 'routes' && rides.length > 0 && !routeReady && !analyticsStarted;
  const insightDataPending = page === 'insights' && rides.length > 0 && !insightsReady && !analyticsStarted;

  return (
    <>
      <Header count={rides.length} updated={updated} dataUpdated={dataUpdated} loading={loadingRides} notice={syncNotice} onRefresh={handleRefresh} />
      <Navigation ridesSearch={ridesSearch} />
      <main className={`shell page-shell page-${page}`}>
        <PageIntro page={page} />
        {loadError ? <div className="error-state" role="alert"><strong>Could not load the archive</strong><p>{loadError.message}</p><button type="button" onClick={handleRefresh}>Try again</button></div> : pageLoading ? <LoadingState label={loadingLabel} /> : <>
          {analyticsLoading && <div className="page-loading-note" role="status">{loadingLabel}...</div>}
          {page === 'overview' && <OverviewContent rides={rides} routeCount={commutes?.groups.length ?? 0} timezone={analyticsTimezone} directionsError={analyticsErrors.directions} onRetry={handleRefresh} />}
          {page === 'routes' && (routeReady || (!analyticsLoading && !routeDataPending) ? <RoutesContent routes={routes} rides={rides} commutes={commutes} segments={segments} errors={analyticsErrors} onRename={handleRenameLocation} onRetry={handleRefresh} /> : <LoadingState label={loadingLabel} />)}
          {page === 'insights' && (insightsReady || (!analyticsLoading && !insightDataPending) ? <InsightsContent insights={insights} weather={weather} errors={analyticsErrors} onRetry={handleRefresh} /> : <LoadingState label={loadingLabel} />)}
          {page === 'rides' && <RidesContent visibleRides={visibleRides} totalRides={rides.length} selectedId={selectedId} assignments={assignments} filters={filters} allDates={allDates} directions={directions} locationSearch={locationSearch} directionsError={analyticsErrors.directions} onRetry={handleRefresh} onFiltersChange={setRideFilters} onFiltersReset={resetRideFilters} detailState={detailState} selectedAssignment={selectedAssignment} />}
        </>}
      </main>
    </>
  );
}

export function App() {
  return <DashboardPage page="overview" />;
}
