import { formatDuration, formatSpeed } from '../format';
import type { RouteSegment } from '../types';

interface SegmentGroup {
  key: string;
  label: string;
  direction: RouteSegment['direction'];
  totalRides: number;
  segments: RouteSegment[];
}

function groupSegments(segments: RouteSegment[]): SegmentGroup[] {
  const groups = new Map<string, SegmentGroup>();
  segments.forEach((segment) => {
    const key = `${segment.group_id}-${segment.direction}`;
    const group = groups.get(key);
    if (group) {
      group.segments.push(segment);
      return;
    }
    groups.set(key, {
      key,
      label: segment.label,
      direction: segment.direction,
      totalRides: segment.total_rides,
      segments: [segment],
    });
  });
  return [...groups.values()];
}

function coordinate(point: [number, number]): string {
  return `${point[0].toFixed(4)}, ${point[1].toFixed(4)}`;
}

function distance(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(2)} km`;
}

export function SegmentsSection({ segmentCount, segments }: { segmentCount: number; segments: RouteSegment[] }) {
  if (!segments.length) return null;
  const groups = groupSegments(segments);
  return (
    <section className="segments">
      <div className="section-head"><h2>Repeated route segments</h2><span>{groups.length} DIRECTIONS</span></div>
      <p className="chart-note segment-note">Repeated directions are normalized into {segmentCount} equal-distance sections. Each row shows the geographic span, average speed, fastest observed time, and ride coverage.</p>
      <div className="segment-groups">
        {groups.map((group) => (
          <article className="segment-card" key={group.key}>
            <div className="segment-card-head">
              <div><p className="eyebrow">REPEATED SECTION</p><h3>{group.label}</h3></div>
              <span className={`direction-tag ${group.direction}`}>{group.direction} · {group.totalRides} RIDES</span>
            </div>
            <div className="segment-table-head"><span /><span>PROGRESS</span><span>LENGTH</span><span>AVG / BEST</span><span>RIDES</span></div>
            <div className="segment-rows">
              {group.segments.map((segment) => (
                <div className="segment-row" key={segment.id}>
                  <span className="segment-index">{String(segment.index).padStart(2, '0')}</span>
                  <div className="segment-route">
                    <div className="segment-route-head"><b>{segment.progress_start}% - {segment.progress_end}%</b><span>{coordinate(segment.start)} -&gt; {coordinate(segment.end)}</span></div>
                    <div className="segment-bar"><i style={{ width: `${segment.coverage_percent ?? 0}%` }} /></div>
                  </div>
                  <span className="segment-distance">{distance(segment.distance_km)}</span>
                  <span className="segment-performance" title={segment.record_ride_id ? `Record: ${segment.record_ride_id}` : undefined}><b>{formatSpeed(segment.average_speed_kmh)}</b><small>BEST {formatDuration(segment.fastest_time_seconds)}</small></span>
                  <b className="segment-rides">{segment.ride_count}/{segment.total_rides}</b>
                </div>
              ))}
            </div>
            <p className="chart-note segment-card-note">Coverage is based on valid GPS tracks available for this direction.</p>
          </article>
        ))}
      </div>
    </section>
  );
}
