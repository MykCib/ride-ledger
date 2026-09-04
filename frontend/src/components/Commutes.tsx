import { formatClockTime, formatDuration, formatSpeed, formatTime } from '../format';
import type { RouteGroup, RouteLocation, RouteOverlay, RoutePerformance } from '../types';
import { CommuteRoutesMap } from './Maps';
import { routeGroupColor } from '../routeColors';
import { Link } from 'react-router-dom';

function distance(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(2)} km`;
}

function distanceVariation(value: number | null): string {
  return value == null ? '—' : `±${value.toFixed(2)} km`;
}

function PerformanceBlock({ title, performance }: { title: string; performance: RoutePerformance }) {
  if (!performance.count) {
    return (
      <div className="commute-direction commute-direction-empty">
        <div className="commute-direction-head"><h3>{title}</h3><span>0 RIDES</span></div>
        <p>No rides detected in this direction yet.</p>
      </div>
    );
  }
  return (
    <div className="commute-direction">
      <div className="commute-direction-head"><h3>{title}</h3><span>{performance.count} RIDES</span></div>
      <div className="commute-metrics metric-grid">
        <div><span>Avg speed</span><b>{formatSpeed(performance.average_speed_kmh)}</b></div>
        <div><span>Moving time</span><b>{formatTime(performance.average_moving_seconds)}</b></div>
        <div><span>Avg duration</span><b>{formatDuration(performance.average_commute_seconds)}</b></div>
        <div><span>Stopped time</span><b>{formatDuration(performance.average_stopped_seconds)}</b></div>
        <div><span>Distance</span><b>{distance(performance.average_distance_km)}</b></div>
        <div><span>Distance spread</span><b>{distanceVariation(performance.distance_variation_km)}</b></div>
        <div><span>Typical departure</span><b>{formatClockTime(performance.typical_departure_time)}</b></div>
        <div><span>Typical arrival</span><b>{formatClockTime(performance.typical_arrival_time)}</b></div>
      </div>
    </div>
  );
}

function comparison(group: RouteGroup): string {
  const outboundSpeed = group.outbound.average_speed_kmh;
  const returnSpeed = group.return.average_speed_kmh;
  if (!group.return.count) return 'A return direction has not been detected yet.';
  if (outboundSpeed == null || returnSpeed == null) return 'Speed comparison is unavailable for this route.';
  const delta = outboundSpeed - returnSpeed;
  if (Math.abs(delta) < 0.05) return 'Average speed is effectively the same in both directions.';
  return delta > 0
    ? `${delta.toFixed(1)} km/h faster outbound on average.`
    : `${Math.abs(delta).toFixed(1)} km/h faster return on average.`;
}

interface CommuteSectionProps {
  timezone: string;
  groups: RouteGroup[];
  routes: RouteOverlay[];
  locations: RouteLocation[];
  onRename: (locationId: string, name: string) => Promise<void>;
  selectedGroupId: string | null;
  onSelectGroup: (groupId: string | null) => void;
}

export function CommuteSection({ timezone, groups, routes, locations, onRename, selectedGroupId, onSelectGroup }: CommuteSectionProps) {
  if (!groups.length) return null;
  return (
    <section className="commutes">
      <div className="section-head"><h2>Route directions</h2><span>{groups.length} GROUPS</span></div>
      <p className="chart-note commute-note">Repeated endpoint pairs are grouped together. Outbound is the direction with the earlier typical departure; median times use {timezone}, and distance spread is standard deviation.</p>
      <div className="commute-overview">
        <div className="commute-list">
          {groups.map((group) => (
            <article className={`commute-card${selectedGroupId === group.id ? ' selected' : ''}`} key={group.id}>
              <div className="commute-card-head">
                <div>
                  <p className="eyebrow">REPEATED ROUTE</p>
                  <h3>{group.label}</h3>
                  <p className="commute-coordinates">
                    {group.origin.lat.toFixed(4)}, {group.origin.lon.toFixed(4)} -&gt; {group.destination.lat.toFixed(4)}, {group.destination.lon.toFixed(4)}
                  </p>
                </div>
                <span>{group.total_rides} RIDES</span>
              </div>
              <div className="commute-directions">
                <PerformanceBlock title="Outbound" performance={group.outbound} />
                <PerformanceBlock title="Return" performance={group.return} />
              </div>
              <p className="commute-comparison">{comparison(group)}</p>
              <div className="commute-ride-links"><span>Matching rides</span>{[...new Set([...group.outbound.ride_ids, ...group.return.ride_ids])].slice(0, 3).map((rideId) => <Link to={`/rides/${rideId}`} key={rideId}>{rideId}</Link>)}{group.total_rides > 3 && <small>+{group.total_rides - 3} more</small>}</div>
              <button type="button" className="route-focus-button" aria-pressed={selectedGroupId === group.id} onClick={() => onSelectGroup(selectedGroupId === group.id ? null : group.id)}>{selectedGroupId === group.id ? 'Clear map focus' : 'Show on map'} <b>-&gt;</b></button>
            </article>
          ))}
        </div>
        <div className="commute-map-panel">
           <div className="section-head"><h2>Stacked routes</h2><span>GROUPED TRACKS</span></div>
          <div className="route-group-legend" aria-label="Repeated route group colors">{groups.map((group) => <span key={group.id}><i style={{ backgroundColor: routeGroupColor(group.id) }} aria-hidden="true" />{group.label}</span>)}</div>
           <CommuteRoutesMap routes={routes} groups={groups} locations={locations} selectedGroupId={selectedGroupId} onSelectGroup={onSelectGroup} onRename={onRename} />
          <p className="chart-note">Each color is a repeated route group. Click any endpoint marker to rename it across the archive. Clear the name to restore its letter.</p>
        </div>
      </div>
    </section>
  );
}
