import { useState } from 'react';
import { Link } from 'react-router-dom';
import { formatDuration, formatSpeed } from '../format';
import type { RouteSegment } from '../types';
import { SegmentsMap } from './Maps';

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

export function SegmentsSection({ segmentCount, segments, selectedGroupId = null, error, onRetry }: { segmentCount: number; segments: RouteSegment[]; selectedGroupId?: string | null; error?: string; onRetry?: () => void }) {
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  if (!segments.length && error) {
    return <section className="segments"><div className="data-empty"><strong>Repeated segments could not be loaded.</strong><p>Try again after the route index has finished rebuilding.</p>{onRetry && <button type="button" className="segment-retry" onClick={onRetry}>Retry</button>}</div></section>;
  }
  if (!segments.length) return null;
  const groups = groupSegments(segments);
  const selectedSegment = segments.find((segment) => segment.id === selectedSegmentId && (!selectedGroupId || segment.group_id === selectedGroupId)) ?? null;
  const isSelected = (segment: RouteSegment) => selectedSegmentId === segment.id && (!selectedGroupId || segment.group_id === selectedGroupId);
  return (
    <section className="segments">
      <div className="section-head"><h2>Repeated route segments</h2><span>{selectedGroupId ? 'GROUP FOCUS' : `${groups.length} DIRECTIONS`}</span></div>
      {error && <div className="inline-error" role="alert"><span>{error}</span>{onRetry && <button type="button" onClick={onRetry}>Retry</button>}</div>}
      <p className="chart-note segment-note">Repeated directions are normalized into {segmentCount} equal-distance sections. Each row shows the geographic span, average speed, fastest observed time, and ride coverage.</p>
      <div className="segment-map-panel">
        <SegmentsMap segments={segments} focusGroupId={selectedGroupId} selectedSegmentId={selectedSegmentId} onSelectSegment={setSelectedSegmentId} />
        <div className="segment-map-note" aria-live="polite">
          {selectedSegment ? <><span>Selected {selectedSegment.label} · {selectedSegment.progress_start}-{selectedSegment.progress_end}% · {formatSpeed(selectedSegment.average_speed_kmh)}</span>{selectedSegment.record_ride_id && <Link to={`/rides/${selectedSegment.record_ride_id}`}>Open record ride <b>-&gt;</b></Link>}</> : <span>Select a segment on the map or in the tables below.</span>}
        </div>
      </div>
      <div className="segment-groups">
        {groups.map((group) => (
          <article className={`segment-card${selectedGroupId === group.segments[0]?.group_id ? ' selected' : ''}`} key={group.key}>
            <div className="segment-card-head">
              <div><p className="eyebrow">REPEATED SECTION</p><h3>{group.label}</h3></div>
              <span className={`direction-tag ${group.direction}`}>{group.direction} · {group.totalRides} RIDES</span>
            </div>
            <div className="segment-table-head"><span /><span>PROGRESS</span><span>LENGTH</span><span>AVG / BEST</span><span>RIDES</span></div>
            <div className="segment-rows">
              {group.segments.map((segment) => (
                <button type="button" className={`segment-row${isSelected(segment) ? ' selected' : ''}`} aria-pressed={isSelected(segment)} key={segment.id} onClick={() => setSelectedSegmentId(segment.id)}>
                  <span className="segment-index">{String(segment.index).padStart(2, '0')}</span>
                  <div className="segment-route">
                    <div className="segment-route-head"><b>{segment.progress_start}% - {segment.progress_end}%</b><span>{coordinate(segment.start)} -&gt; {coordinate(segment.end)}</span></div>
                    <div className="segment-bar"><i style={{ width: `${segment.coverage_percent ?? 0}%` }} /></div>
                  </div>
                  <span className="segment-distance">{distance(segment.distance_km)}</span>
                  <span className="segment-performance" title={segment.record_ride_id ? `Record: ${segment.record_ride_id}` : undefined}><b>{formatSpeed(segment.average_speed_kmh)}</b><small>BEST {formatDuration(segment.fastest_time_seconds)}</small></span>
                  <b className="segment-rides">{segment.ride_count}/{segment.total_rides}</b>
                </button>
              ))}
            </div>
            <p className="chart-note segment-card-note">Coverage is based on valid GPS tracks available for this direction.</p>
          </article>
        ))}
      </div>
    </section>
  );
}
