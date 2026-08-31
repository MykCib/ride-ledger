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
  climbing_rate_m_per_hour: number | null;
  descent_rate_m_per_hour: number | null;
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

export type RouteDirection = 'outbound' | 'return' | 'loop';

export interface RouteLocation {
  id: string;
  label: string;
  lat: number;
  lon: number;
}

export interface RoutePerformance {
  count: number;
  ride_ids: string[];
  typical_departure_time: string | null;
  typical_arrival_time: string | null;
  average_commute_seconds: number | null;
  average_distance_km: number | null;
  distance_variation_km: number | null;
  average_speed_kmh: number | null;
  average_moving_seconds: number | null;
  average_elapsed_seconds: number | null;
  average_stopped_seconds: number | null;
}

export interface RouteGroup {
  id: string;
  label: string;
  origin: RouteLocation;
  destination: RouteLocation;
  total_rides: number;
  outbound: RoutePerformance;
  return: RoutePerformance;
}

export interface RouteAssignment {
  group_id: string | null;
  direction: RouteDirection;
  label: string;
}

export interface RouteSegment {
  id: string;
  group_id: string;
  label: string;
  direction: Exclude<RouteDirection, 'loop'>;
  index: number;
  progress_start: number;
  progress_end: number;
  start: RouteCoordinate;
  end: RouteCoordinate;
  distance_km: number | null;
  ride_count: number;
  total_rides: number;
  coverage_percent: number | null;
  performance_count: number;
  average_time_seconds: number | null;
  average_speed_kmh: number | null;
  fastest_time_seconds: number | null;
  record_ride_id: string | null;
}

export interface SegmentAnalysis {
  segment_count: number;
  segments: RouteSegment[];
}

export interface WeatherBin {
  label: string;
  average_speed_kmh: number | null;
  ride_count: number;
}

export interface WeatherConditionStats {
  count: number;
  average_speed_kmh: number | null;
  average_temperature_c: number | null;
  average_wind_kmh: number | null;
  average_precipitation_mm: number | null;
}

export interface FastestWeatherRide {
  ride_id: string;
  date: string | null;
  speed_kmh: number;
  temperature_c: number | null;
  wind_kmh: number | null;
  precipitation_mm: number | null;
}

export interface WeatherDirectionComparison {
  group_id: string;
  label: string;
  outbound: WeatherConditionStats;
  return: WeatherConditionStats;
}

export interface WeatherAnalysis {
  total_rides: number;
  available_rides: number;
  temperature_bins: WeatherBin[];
  wind_bins: WeatherBin[];
  conditions: {
    dry: WeatherConditionStats;
    wet: WeatherConditionStats;
  };
  fastest: FastestWeatherRide | null;
  directions: WeatherDirectionComparison[];
}

export interface ActivityDay {
  date: string;
  ride_count: number;
  distance_km: number | null;
}

export interface CommuteAnalysis {
  timezone: string;
  groups: RouteGroup[];
  assignments: Record<string, RouteAssignment>;
  locations: RouteLocation[];
}

export interface Insights {
  timezone: string;
  segments: Array<number | null>;
  segment_rides: number[];
  weekday_counts: number[];
  departure_hour_counts: number[];
  calendar: ActivityDay[];
  fastest: WorkoutSummary | null;
  longest: WorkoutSummary | null;
}
