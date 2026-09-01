import type { CommuteAnalysis, Insights, RouteOverlay, SegmentAnalysis, WeatherAnalysis, WorkoutDetail, WorkoutSummary } from './types';

async function request<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export async function getWorkouts(signal?: AbortSignal): Promise<{ workouts: WorkoutSummary[]; count: number; updated: string; data_updated: string | null }> {
  return request('/api/workouts', signal);
}

export async function getWorkoutDetail(id: string, signal?: AbortSignal): Promise<WorkoutDetail> {
  return request(`/api/workouts/${encodeURIComponent(id)}`, signal);
}

export async function getRoutes(signal?: AbortSignal): Promise<{ routes: RouteOverlay[] }> {
  return request('/api/routes', signal);
}

export async function getCommutes(signal?: AbortSignal): Promise<CommuteAnalysis> {
  return request('/api/commutes', signal);
}

export async function getSegments(signal?: AbortSignal): Promise<SegmentAnalysis> {
  return request('/api/segments', signal);
}

export async function getWeather(signal?: AbortSignal): Promise<WeatherAnalysis> {
  return request('/api/weather', signal);
}

export async function renameCommuteLocation(locationId: string, name: string): Promise<CommuteAnalysis> {
  const response = await fetch(`/api/commutes/locations/${encodeURIComponent(locationId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<CommuteAnalysis>;
}

export async function getInsights(signal?: AbortSignal): Promise<Insights> {
  return request('/api/insights', signal);
}
