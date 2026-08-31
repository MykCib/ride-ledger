import { getWorkoutDetail } from './api';
import type { WorkoutDetail } from './types';

interface DetailRequest {
  controller: AbortController;
  promise: Promise<WorkoutDetail>;
}

const cache = new Map<string, WorkoutDetail>();
const requests = new Map<string, DetailRequest>();

export function getCachedDetail(id: string): WorkoutDetail | undefined {
  return cache.get(id);
}

export function fetchDetail(id: string): Promise<WorkoutDetail> {
  const cached = getCachedDetail(id);
  if (cached) return Promise.resolve(cached);
  const pending = requests.get(id);
  if (pending) return pending.promise;

  const controller = new AbortController();
  let promise: Promise<WorkoutDetail>;
  promise = getWorkoutDetail(id, controller.signal)
    .then((data) => {
      cache.set(id, data);
      return data;
    })
    .finally(() => {
      if (requests.get(id)?.promise === promise) requests.delete(id);
    });
  requests.set(id, { controller, promise });
  return promise;
}

export function prefetchDetail(id: string): void {
  fetchDetail(id).catch(() => {});
}

export function clearDetailCache(): void {
  requests.forEach(({ controller }) => controller.abort());
  requests.clear();
  cache.clear();
}
