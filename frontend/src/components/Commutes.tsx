import { formatDuration, formatSpeed, formatTime } from '../format';
import type { RouteGroup, RoutePerformance } from '../types';

function distance(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(2)} km`;
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
      <div className="commute-metrics">
        <div><span>Avg speed</span><b>{formatSpeed(performance.average_speed_kmh)}</b></div>
        <div><span>Moving time</span><b>{formatTime(performance.average_moving_seconds)}</b></div>
        <div><span>Elapsed time</span><b>{formatTime(performance.average_elapsed_seconds)}</b></div>
        <div><span>Stopped time</span><b>{formatDuration(performance.average_stopped_seconds)}</b></div>
        <div><span>Distance</span><b>{distance(performance.average_distance_km)}</b></div>
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
  return `${Math.abs(delta).toFixed(1)} km/h faster outbound on average.`;
}

export function CommuteSection({ groups }: { groups: RouteGroup[] }) {
  if (!groups.length) return null;
  return (
    <section className="commutes">
      <div className="section-head"><h2>Route directions</h2><span>{groups.length} GROUPS</span></div>
      <p className="chart-note commute-note">Repeated endpoint pairs are grouped together. Outbound is the direction with the earlier typical departure; endpoint labels are anonymous.</p>
      <div className="commute-list">
        {groups.map((group) => (
          <article className="commute-card" key={group.id}>
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
          </article>
        ))}
      </div>
    </section>
  );
}
