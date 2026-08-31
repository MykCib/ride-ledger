export interface WorkoutSummary {
  id: string;
  file: string;
  date: string | null;
  distance_km: number | null;
  moving_seconds: number | null;
  elapsed_seconds: number | null;
  average_speed_kmh: number | null;
  max_speed_kmh: number | null;
  ascent_m: number | null;
  descent_m: number | null;
  calories: number | null;
  temperature_c: number | null;
  points: number;
  estimated_stopped_seconds: number | null;
  moving_percent: number | null;
  stop_count: number;
  longest_stop_seconds: number;
}

export interface TrackPoint {
  lat: number;
  lon: number;
  t: string | null;
  speed: number | null;
  altitude: number | null;
  distance_m: number | null;
}

export interface WeatherSummary {
  temperature_c: number | null;
  feels_like_c: number | null;
  wind_kmh: number | null;
  precipitation_mm: number | null;
}

export interface StopInterval {
  start: string;
  end: string;
  duration_seconds: number;
}

export interface WorkoutDetail extends WorkoutSummary {
  track: TrackPoint[];
  weather: WeatherSummary | null;
  stops: StopInterval[];
}

export type RouteCoordinate = [number, number];

export interface RouteOverlay {
  id: string;
  points: RouteCoordinate[];
}

export interface Insights {
  segments: Array<number | null>;
  segment_rides: number[];
  weekday_counts: number[];
  fastest: WorkoutSummary | null;
  longest: WorkoutSummary | null;
}
