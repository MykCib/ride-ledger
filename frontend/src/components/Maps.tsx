import { useEffect, useRef } from 'react';
import L from 'leaflet';
import type { RouteCoordinate, RouteGroup, RouteLocation, RouteMapSample, RouteOverlay, RouteSegment, TrackPoint } from '../types';
import { routeGroupColor } from '../routeColors';

const tileUrl = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const tileOptions = { attribution: '© OpenStreetMap contributors' };

function clearLayers(map: L.Map, layers: L.Polyline[]): void {
  layers.forEach((layer) => {
    layer.off();
    map.removeLayer(layer);
  });
  layers.length = 0;
}

function registerLayerClick(layer: L.Polyline, handler: () => void): () => void {
  layer.on('click', handler);
  return () => layer.off('click', handler);
}

interface RouteMapProps {
  track: TrackPoint[];
  highlightedPoint: TrackPoint | null;
  playbackPoint?: TrackPoint | null;
}

export function RouteMap({ track, highlightedPoint, playbackPoint = null }: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const routeRef = useRef<L.Polyline | null>(null);
  const startRef = useRef<L.CircleMarker | null>(null);
  const endRef = useRef<L.CircleMarker | null>(null);
  const highlightRef = useRef<L.CircleMarker | null>(null);
  const playbackRef = useRef<L.CircleMarker | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: false }).setView([0, 0], 13);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.tileLayer(tileUrl, tileOptions).addTo(map);
    routeRef.current = L.polyline([], { color: '#4d6b38', weight: 4, opacity: 0.9 }).addTo(map);
    startRef.current = L.circleMarker([0, 0], { radius: 6, color: '#26332e', fillColor: '#c8e66a', fillOpacity: 1 }).addTo(map);
    endRef.current = L.circleMarker([0, 0], { radius: 6, color: '#26332e', fillColor: '#fff', fillOpacity: 1 }).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      routeRef.current = null;
      startRef.current = null;
      endRef.current = null;
      highlightRef.current = null;
      playbackRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const route = routeRef.current;
    if (!map || !route) return;
    map.invalidateSize({ pan: false });
    if (!track.length) {
      route.setLatLngs([]);
      return;
    }
    const stride = Math.max(1, Math.ceil(track.length / 1200));
    const points: RouteCoordinate[] = [];
    for (let index = 0; index < track.length; index += 1) {
      if (index % stride !== 0 && index !== track.length - 1) continue;
      const point = track[index];
      points.push([point.lat, point.lon]);
    }
    route.setLatLngs(points);
    startRef.current?.setLatLng(points[0]);
    endRef.current?.setLatLng(points[points.length - 1]);
    map.fitBounds(route.getBounds(), { padding: [20, 20] });
  }, [track]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!highlightedPoint) {
      if (highlightRef.current) map.removeLayer(highlightRef.current);
      highlightRef.current = null;
      return;
    }
    if (!highlightRef.current) {
      highlightRef.current = L.circleMarker([highlightedPoint.lat, highlightedPoint.lon], {
        radius: 8,
        color: '#18221f',
        weight: 3,
        fillColor: '#c8e66a',
        fillOpacity: 1,
      }).addTo(map);
    } else {
      highlightRef.current.setLatLng([highlightedPoint.lat, highlightedPoint.lon]);
    }
    highlightRef.current.bindTooltip(highlightedPoint.speed == null ? 'Speed unavailable' : `${(highlightedPoint.speed * 3.6).toFixed(1)} km/h`, { permanent: false }).openTooltip();
  }, [highlightedPoint]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!playbackPoint) {
      if (playbackRef.current) map.removeLayer(playbackRef.current);
      playbackRef.current = null;
      return;
    }
    if (!playbackRef.current) {
      playbackRef.current = L.circleMarker([playbackPoint.lat, playbackPoint.lon], {
        radius: 9,
        color: '#fff',
        weight: 3,
        fillColor: '#d45b3f',
        fillOpacity: 1,
      }).addTo(map);
    } else {
      playbackRef.current.setLatLng([playbackPoint.lat, playbackPoint.lon]);
    }
    playbackRef.current.bringToFront();
  }, [playbackPoint]);

  return <div ref={containerRef} className="map" role="region" aria-label="Ride route map" />;
}

type AllRoutesMapMode = 'overlay' | 'density' | 'speed' | 'elevation';

function metricValue(sample: RouteMapSample, mode: AllRoutesMapMode): number | null {
  if (mode === 'speed') return sample.speed_kmh;
  if (mode === 'elevation') return sample.elevation_m;
  return null;
}

function metricColor(value: number | null, minimum: number, maximum: number): string {
  if (value == null) return '#7c8981';
  const ratio = maximum > minimum ? Math.max(0, Math.min(1, (value - minimum) / (maximum - minimum))) : 0.5;
  return `hsl(${Math.round(210 - ratio * 165)} 62% ${Math.round(42 + ratio * 12)}%)`;
}

interface AllRoutesMapProps {
  routes: RouteOverlay[];
  mode?: AllRoutesMapMode;
  focusRouteKey?: string;
  selectedRouteId?: string | null;
  onSelectRoute?: (routeId: string) => void;
}

export function AllRoutesMap({ routes, mode = 'overlay', focusRouteKey = '', selectedRouteId = null, onSelectRoute }: AllRoutesMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layersRef = useRef<L.Polyline[]>([]);
  const selectRouteRef = useRef(onSelectRoute);

  useEffect(() => {
    selectRouteRef.current = onSelectRoute;
  }, [onSelectRoute]);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: false }).setView([0, 0], 13);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.tileLayer(tileUrl, tileOptions).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      layersRef.current = [];
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    clearLayers(map, layersRef.current);
    const bounds = L.latLngBounds([]);
    const focusBounds = L.latLngBounds([]);
    const focused = focusRouteKey ? new Set(focusRouteKey.split('|')) : null;
    const createdLayers: L.Polyline[] = [];
    const clickCleanups: Array<() => void> = [];
    const metricValues: number[] = [];
    routes.forEach((routeData) => {
      if (focused && !focused.has(routeData.id)) return;
      (routeData.samples ?? []).forEach((sample) => {
        const value = metricValue(sample, mode);
        if (value != null && Number.isFinite(value)) metricValues.push(value);
      });
    });
    const minimum = metricValues.length ? Math.min(...metricValues) : 0;
    const maximum = metricValues.length ? Math.max(...metricValues) : 0;
    routes.forEach((routeData) => {
      if (!routeData.points.length) return;
      const isFocused = !focused || focused.has(routeData.id);
      const isSelected = selectedRouteId === routeData.id;
      const addLayer = (points: RouteCoordinate[], color: string, weight: number, opacity: number) => {
        if (points.length < 2) return;
        const layer = L.polyline(points, { color, weight, opacity, lineCap: 'round', lineJoin: 'round' }).addTo(map);
        const handleClick = () => selectRouteRef.current?.(routeData.id);
        clickCleanups.push(registerLayerClick(layer, handleClick));
        createdLayers.push(layer);
        layersRef.current.push(layer);
        bounds.extend(layer.getBounds());
        if (isFocused) focusBounds.extend(layer.getBounds());
      };

      if (mode === 'speed' || mode === 'elevation') {
        const samples = routeData.samples?.length ? routeData.samples : routeData.points.map(([lat, lon]) => ({ lat, lon, speed_kmh: null, elevation_m: null }));
        const metricStride = Math.max(1, Math.ceil(samples.length / 80));
        const metricSamples = samples.filter((_sample, index) => index % metricStride === 0 || index === samples.length - 1);
        metricSamples.slice(0, -1).forEach((sample, index) => {
          const next = metricSamples[index + 1];
          const value = metricValue(sample, mode);
          addLayer([[sample.lat, sample.lon], [next.lat, next.lon]], metricColor(value, minimum, maximum), isSelected ? 6 : 3.5, isSelected ? 0.95 : isFocused ? 0.72 : 0.12);
        });
      } else {
        addLayer(routeData.points, mode === 'density' ? '#4d6b38' : '#d45b3f', isSelected ? 6 : mode === 'density' ? 6 : 3, isSelected ? 0.9 : mode === 'density' ? (isFocused ? 0.18 : 0.04) : (isFocused ? 0.42 : 0.08));
      }
    });
    map.invalidateSize({ pan: false });
    const visibleBounds = focusBounds.isValid() ? focusBounds : bounds;
    if (visibleBounds.isValid()) map.fitBounds(visibleBounds, { padding: [24, 24] });
    return () => {
      clickCleanups.forEach((cleanup) => cleanup());
      createdLayers.forEach((layer) => map.removeLayer(layer));
      layersRef.current = [];
    };
  }, [focusRouteKey, mode, routes, selectedRouteId]);

  return <div id="all-map" ref={containerRef} className="all-map" role="region" aria-label="Interactive map of recorded rides" />;
}

interface SegmentsMapProps {
  segments: RouteSegment[];
  focusGroupId: string | null;
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
}

export function SegmentsMap({ segments, focusGroupId, selectedSegmentId, onSelectSegment }: SegmentsMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layersRef = useRef<L.Polyline[]>([]);
  const selectSegmentRef = useRef(onSelectSegment);

  useEffect(() => {
    selectSegmentRef.current = onSelectSegment;
  }, [onSelectSegment]);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: false }).setView([0, 0], 13);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.tileLayer(tileUrl, tileOptions).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      layersRef.current = [];
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    clearLayers(map, layersRef.current);
    const bounds = L.latLngBounds([]);
    const createdLayers: L.Polyline[] = [];
    const clickCleanups: Array<() => void> = [];
    segments.forEach((segment) => {
      const focused = !focusGroupId || segment.group_id === focusGroupId;
      const selected = segment.id === selectedSegmentId && focused;
      const layer = L.polyline([segment.start, segment.end], {
        color: segment.direction === 'outbound' ? '#4d6b38' : '#d45b3f',
        weight: selected ? 7 : 4,
        opacity: selected ? 0.95 : !focused ? 0.12 : selectedSegmentId ? 0.22 : 0.6,
        lineCap: 'round',
      }).addTo(map);
      layer.bindTooltip(`${segment.label} · ${segment.progress_start}-${segment.progress_end}%`, { sticky: true });
      const handleClick = () => selectSegmentRef.current(segment.id);
      clickCleanups.push(registerLayerClick(layer, handleClick));
      createdLayers.push(layer);
      layersRef.current.push(layer);
      bounds.extend(layer.getBounds());
    });
    map.invalidateSize({ pan: false });
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24] });
    return () => {
      clickCleanups.forEach((cleanup) => cleanup());
      createdLayers.forEach((layer) => {
        map.removeLayer(layer);
      });
      layersRef.current = [];
    };
  }, [focusGroupId, segments, selectedSegmentId]);

  return <div ref={containerRef} className="segment-map" role="region" aria-label="Interactive map of repeated route segments" />;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character] || character);
}

function locationIcon(label: string): L.DivIcon {
  return L.divIcon({
    className: 'location-marker',
    html: `<span>${escapeHtml(label)}</span>`,
    iconSize: [36, 28],
    iconAnchor: [18, 14],
  });
}

function locationPopup(location: RouteLocation, marker: L.Marker, rename: (name: string) => Promise<void>): HTMLFormElement {
  const form = document.createElement('form');
  form.className = 'location-popup';
  const label = document.createElement('label');
  label.textContent = 'Point name';
  const input = document.createElement('input');
  input.type = 'text';
  input.value = location.label;
  input.maxLength = 60;
  input.placeholder = 'e.g. Home';
  input.setAttribute('aria-label', 'Point name');
  const actions = document.createElement('div');
  actions.className = 'location-popup-actions';
  const save = document.createElement('button');
  save.type = 'submit';
  save.textContent = 'Save';
  const status = document.createElement('span');
  status.className = 'location-popup-status';
  actions.append(save, status);
  form.append(label, input, actions);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    save.disabled = true;
    status.textContent = 'Saving...';
    rename(input.value.trim())
      .then(() => {
        status.textContent = 'Saved';
        marker.closePopup();
      })
      .catch((error: unknown) => {
        status.textContent = error instanceof Error ? error.message : 'Could not save';
        save.disabled = false;
      });
  });
  return form;
}

interface CommuteRoutesMapProps {
  routes: RouteOverlay[];
  groups: RouteGroup[];
  locations: RouteLocation[];
  selectedGroupId: string | null;
  onSelectGroup: (groupId: string | null) => void;
  onRename: (locationId: string, name: string) => Promise<void>;
}

export function CommuteRoutesMap({ routes, groups, locations, selectedGroupId, onSelectGroup, onRename }: CommuteRoutesMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layersRef = useRef<L.Polyline[]>([]);
  const markersRef = useRef<L.Marker[]>([]);
  const renameRef = useRef(onRename);
  const selectGroupRef = useRef(onSelectGroup);

  useEffect(() => {
    renameRef.current = onRename;
  }, [onRename]);

  useEffect(() => {
    selectGroupRef.current = onSelectGroup;
  }, [onSelectGroup]);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: false }).setView([0, 0], 13);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.tileLayer(tileUrl, tileOptions).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      layersRef.current = [];
      markersRef.current = [];
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    clearLayers(map, layersRef.current);
    const colors = new Map<string, string>();
    const groupsByRoute = new Map<string, RouteGroup>();
    groups.forEach((group) => {
      const color = routeGroupColor(group.id);
      [...group.outbound.ride_ids, ...group.return.ride_ids].forEach((rideId) => {
        colors.set(rideId, color);
        groupsByRoute.set(rideId, group);
      });
    });
    const bounds = L.latLngBounds([]);
    const createdLayers: L.Polyline[] = [];
    const clickCleanups: Array<() => void> = [];
    routes.forEach((routeData) => {
      if (!routeData.points.length) return;
      const group = groupsByRoute.get(routeData.id);
      const selected = group?.id === selectedGroupId;
      const dimmed = selectedGroupId !== null && !selected;
      const layer = L.polyline(routeData.points, {
        color: colors.get(routeData.id) || '#7c8981',
        weight: selected ? 5 : 3,
        opacity: dimmed ? 0.07 : selected ? 0.75 : colors.has(routeData.id) ? 0.28 : 0.2,
        lineCap: 'round',
        lineJoin: 'round',
      }).addTo(map);
      if (group) {
        const handleClick = () => selectGroupRef.current(group.id);
        clickCleanups.push(registerLayerClick(layer, handleClick));
      }
      createdLayers.push(layer);
      layersRef.current.push(layer);
      bounds.extend(layer.getBounds());
    });
    map.invalidateSize({ pan: false });
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24] });
    return () => {
      clickCleanups.forEach((cleanup) => cleanup());
      createdLayers.forEach((layer) => {
        map.removeLayer(layer);
      });
      layersRef.current = [];
    };
  }, [groups, routes, selectedGroupId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach((marker) => map.removeLayer(marker));
    markersRef.current = [];
    locations.forEach((location) => {
      const marker = L.marker([location.lat, location.lon], { icon: locationIcon(location.label) }).addTo(map);
      marker.bindPopup(locationPopup(location, marker, (name) => renameRef.current(location.id, name)));
      markersRef.current.push(marker);
    });
  }, [locations]);

  return <div ref={containerRef} className="commute-map" role="region" aria-label="Interactive map of repeated route groups" />;
}
