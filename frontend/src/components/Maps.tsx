import { useEffect, useRef } from 'react';
import L from 'leaflet';
import type { RouteCoordinate, RouteOverlay, TrackPoint } from '../types';

const tileUrl = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const tileOptions = { attribution: '© OpenStreetMap contributors' };

interface RouteMapProps {
  track: TrackPoint[];
  highlightedPoint: TrackPoint | null;
}

export function RouteMap({ track, highlightedPoint }: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const routeRef = useRef<L.Polyline | null>(null);
  const startRef = useRef<L.CircleMarker | null>(null);
  const endRef = useRef<L.CircleMarker | null>(null);
  const highlightRef = useRef<L.CircleMarker | null>(null);

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
