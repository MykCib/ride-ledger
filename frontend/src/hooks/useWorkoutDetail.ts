import { useEffect, useState } from 'react';
import { fetchDetail, getCachedDetail } from '../detailCache';
import type { WorkoutDetail } from '../types';

interface DetailState {
  data: WorkoutDetail | null;
  loading: boolean;
  error: Error | null;
}

export function useWorkoutDetail(id: string | undefined, refreshKey: number): DetailState {
  const [state, setState] = useState<DetailState>({ data: null, loading: Boolean(id), error: null });

  useEffect(() => {
    let active = true;
    if (!id) {
      setState({ data: null, loading: false, error: null });
      return () => { active = false; };
    }

    const cached = getCachedDetail(id);
    if (cached) {
      setState({ data: cached, loading: false, error: null });
      return () => { active = false; };
    }

    setState((previous) => ({ ...previous, loading: true, error: null }));
    fetchDetail(id)
      .then((data) => {
        if (active) setState({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (active && !(error instanceof DOMException && error.name === 'AbortError')) {
          setState((previous) => ({ ...previous, loading: false, error: error instanceof Error ? error : new Error('Could not load workout') }));
        }
      });
    return () => { active = false; };
  }, [id, refreshKey]);

  return state;
}
