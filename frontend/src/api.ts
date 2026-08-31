import type { Insights, RouteOverlay, WorkoutDetail, WorkoutSummary } from './types';

async function request<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export async function getWorkouts(signal?: AbortSignal): Promise<{ workouts: WorkoutSummary[]; count: number; updated: string }> {
  return request('/api/workouts', signal);
}

export async function getWorkoutDetail(id: string, signal?: AbortSignal): Promise<WorkoutDetail> {
  return request(`/api/workouts/${encodeURIComponent(id)}`, signal);
}

export async function getRoutes(signal?: AbortSignal): Promise<{ routes: RouteOverlay[] }> {
  return request('/api/routes', signal);
}

export async function getInsights(signal?: AbortSignal): Promise<Insights> {
  return request('/api/insights', signal);
}
