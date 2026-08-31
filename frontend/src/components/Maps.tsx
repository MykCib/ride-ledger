import { useEffect, useRef } from 'react';
import L from 'leaflet';
import type { RouteCoordinate, RouteGroup, RouteLocation, RouteOverlay, TrackPoint } from '../types';

const tileUrl = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const tileOptions = { attribution: '© OpenStreetMap contributors' };

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
    highlightRef.current.bindTooltip(`${((highlightedPoint.speed ?? 0) * 3.6).toFixed(1)} km/h`, { permanent: false }).openTooltip();
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

  return <div ref={containerRef} className="map" />;
}

export function AllRoutesMap({ routes }: { routes: RouteOverlay[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layersRef = useRef<L.Polyline[]>([]);

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
    layersRef.current.forEach((layer) => map.removeLayer(layer));
    layersRef.current = [];
    const bounds = L.latLngBounds([]);
    routes.forEach((routeData) => {
      if (!routeData.points.length) return;
      const layer = L.polyline(routeData.points, { color: '#d45b3f', weight: 3, opacity: 0.42, lineCap: 'round', lineJoin: 'round' }).addTo(map);
      layersRef.current.push(layer);
      bounds.extend(layer.getBounds());
    });
    map.invalidateSize({ pan: false });
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24] });
  }, [routes]);

  return <div id="all-map" ref={containerRef} className="all-map" />;
}

const commuteColors = ['#4d6b38', '#d45b3f', '#5a78a0', '#8a6e9c', '#b68c3a'];

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
  onRename: (locationId: string, name: string) => Promise<void>;
}

export function CommuteRoutesMap({ routes, groups, locations, onRename }: CommuteRoutesMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layersRef = useRef<L.Polyline[]>([]);
  const markersRef = useRef<L.Marker[]>([]);
  const renameRef = useRef(onRename);

  useEffect(() => {
    renameRef.current = onRename;
  }, [onRename]);

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
    layersRef.current.forEach((layer) => map.removeLayer(layer));
    layersRef.current = [];
    const colors = new Map<string, string>();
    groups.forEach((group, groupIndex) => {
      const color = commuteColors[groupIndex % commuteColors.length];
      group.outbound.ride_ids.forEach((rideId) => colors.set(rideId, color));
      group.return.ride_ids.forEach((rideId) => colors.set(rideId, color));
    });
    const bounds = L.latLngBounds([]);
    routes.forEach((routeData) => {
      if (!routeData.points.length) return;
      const layer = L.polyline(routeData.points, {
        color: colors.get(routeData.id) || '#7c8981',
        weight: 3,
        opacity: colors.has(routeData.id) ? 0.28 : 0.2,
        lineCap: 'round',
        lineJoin: 'round',
      }).addTo(map);
      layersRef.current.push(layer);
      bounds.extend(layer.getBounds());
    });
    map.invalidateSize({ pan: false });
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24] });
  }, [groups, routes]);

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

  return <div ref={containerRef} className="commute-map" />;
}
