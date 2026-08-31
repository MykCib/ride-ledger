export function formatTime(seconds: number | null): string {
  if (!seconds) return '—';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor(seconds % 3600 / 60);
  return hours ? `${hours}h ${String(minutes).padStart(2, '0')}m` : `${minutes} min`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor(total % 3600 / 60);
  const remainingSeconds = total % 60;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${String(remainingSeconds).padStart(2, '0')}s`;
  return `${remainingSeconds}s`;
}

export function formatClock(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatClockTime(value: string | null): string {
  if (!value) return '—';
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(value) ? value : '—';
}

export function formatSpeed(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(1)} km/h`;
}

export function formatVerticalRate(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(0)} m/h`;
}

export function formatDate(value: string | null, options?: Intl.DateTimeFormatOptions): string {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, options);
}

export function formatWorkoutTitle(value: string | null): string {
  return formatDate(value, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
