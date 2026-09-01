import { useEffect, useRef } from 'react';
import Chart from 'chart.js/auto';
import type { TrackPoint } from '../types';

interface LineChartProps {
  values: number[];
  labels: string[];
  fill: string;
  beginAtZero?: boolean;
  onPointHover?: (index: number | null) => void;
}

export function LineChart({ values, labels, fill, beginAtZero = true, onPointHover }: LineChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart<'line'> | null>(null);
  const hoverRef = useRef(onPointHover);

  useEffect(() => {
    hoverRef.current = onPointHover;
  }, [onPointHover]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          data: [],
          borderColor: '#4d6b38',
          backgroundColor: fill,
          fill: true,
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 7,
          pointHitRadius: 14,
          tension: 0.25,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        onHover: (_event, elements) => {
          hoverRef.current?.(elements.length ? elements[0].index : null);
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            displayColors: false,
            callbacks: {
              label: (context) => `${Number(context.parsed.y).toFixed(1)} · ${context.label}`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxTicksLimit: 8, color: '#77817c', font: { family: 'DM Mono', size: 10 } },
          },
          y: {
            beginAtZero,
            grid: { color: '#dce2dc' },
            ticks: { color: '#77817c', font: { family: 'DM Mono', size: 10 } },
          },
        },
      },
    });
    chartRef.current = chart;
    return () => {
      chart.destroy();
      chartRef.current = null;
    };
  }, [beginAtZero, fill]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.data.labels = labels;
    chart.data.datasets[0].data = values;
    chart.update('none');
  }, [labels, values]);

  return <canvas ref={canvasRef} role="img" aria-label="Interactive line chart" />;
}

export function BarChart({ values, labels, fill }: { values: number[]; labels: string[]; fill: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart<'bar'> | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [{
          data: [],
          backgroundColor: fill,
          borderWidth: 0,
          borderRadius: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxRotation: 0, color: '#77817c', font: { family: 'DM Mono', size: 10 } },
          },
          y: {
            beginAtZero: true,
            ticks: { precision: 0, color: '#77817c', font: { family: 'DM Mono', size: 10 } },
            grid: { color: '#dce2dc' },
          },
        },
      },
    });
    chartRef.current = chart;
    return () => {
      chart.destroy();
      chartRef.current = null;
    };
  }, [fill]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.data.labels = labels;
    chart.data.datasets[0].data = values;
    chart.update('none');
  }, [labels, values]);

  return <canvas ref={canvasRef} role="img" aria-label="Interactive bar chart" />;
}

function ChartDataDisclosure({ title, samples, value, onPointHover }: { title: string; samples: TrackPoint[]; value: (sample: TrackPoint) => string; onPointHover?: (point: TrackPoint | null) => void }) {
  if (!samples.length) return null;
  const stride = Math.max(1, Math.ceil(samples.length / 20));
  const visible = samples.filter((_, index) => index % stride === 0 || index === samples.length - 1);
  return (
    <details className="chart-data">
      <summary>{title} values</summary>
      <ol>
        {visible.map((sample, index) => <li key={sample.t ?? `${sample.lat}-${sample.lon}-${sample.speed}-${sample.altitude}`}><button type="button" onFocus={() => onPointHover?.(sample)} onBlur={() => onPointHover?.(null)}>{sample.t ? new Date(sample.t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : `Point ${index + 1}`} <b>{value(sample)}</b></button></li>)}
      </ol>
    </details>
  );
}

interface SpeedChartProps {
  track: TrackPoint[];
  onPointHover: (point: TrackPoint | null) => void;
}

export function SpeedChart({ track, onPointHover }: SpeedChartProps) {
  const valid = track.filter((point) => point.speed != null);
  const stride = Math.max(1, Math.ceil(valid.length / 100));
  const samples = valid.filter((_, index) => index % stride === 0);
  const values = samples.map((sample) => (sample.speed ?? 0) * 3.6);
  const labels = samples.map((sample) => sample.t ? new Date(sample.t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '');

  return (
    <>
      <LineChart
        values={values}
        labels={labels}
        fill="rgba(200,230,106,.35)"
        onPointHover={(index) => onPointHover(index == null ? null : samples[index] ?? null)}
      />
      <ChartDataDisclosure title="Speed" samples={samples} value={(sample) => `${((sample.speed ?? 0) * 3.6).toFixed(1)} km/h`} onPointHover={onPointHover} />
    </>
  );
}

const weeklyDateFormatters = new Map<string, Intl.DateTimeFormat>();

function localDateKey(value: string, timezone: string): string {
  let formatter = weeklyDateFormatters.get(timezone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-US', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: timezone });
    weeklyDateFormatters.set(timezone, formatter);
  }
  const parts = Object.fromEntries(formatter.formatToParts(new Date(value)).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function mondayKey(dateKey: string): string {
  const date = new Date(`${dateKey}T12:00:00Z`);
  const day = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - day);
  return date.toISOString().slice(0, 10);
}

export function WeeklyChart({ items, timezone = 'Europe/Vilnius' }: { items: Array<{ date: string | null; distance_km: number | null }>; timezone?: string }) {
  const weeks: Record<string, number> = {};
  items.forEach((ride) => {
    if (!ride.date) return;
    const key = mondayKey(localDateKey(ride.date, timezone));
    weeks[key] = (weeks[key] || 0) + (ride.distance_km || 0);
  });
  const labels = Object.keys(weeks).sort();
  return <LineChart values={labels.map((key) => weeks[key])} labels={labels.map((key) => key.slice(5))} fill="rgba(200,230,106,.48)" />;
}

export function SegmentChart({ values }: { values: Array<number | null> }) {
  const numbers = values.map((value) => value || 0);
  return <LineChart values={numbers} labels={numbers.map((_, index) => `${index * 10}%`)} fill="rgba(200,230,106,.35)" />;
}

export function ElevationChart({ track, onPointHover }: { track: TrackPoint[]; onPointHover?: (point: TrackPoint | null) => void }) {
  const valid = track.filter((point) => point.altitude != null);
  const stride = Math.max(1, Math.ceil(valid.length / 100));
  const samples = valid.filter((_, index) => index % stride === 0);
  const values = samples.map((sample) => sample.altitude ?? 0);
  const labels = samples.map((sample, index) => sample.distance_m != null ? `${(sample.distance_m / 1000).toFixed(1)} km` : `${index * 10}%`);

  return (
    <>
      <LineChart
        values={values}
        labels={labels}
        fill="rgba(90,120,160,.22)"
        beginAtZero={false}
        onPointHover={(index) => onPointHover?.(index == null ? null : samples[index] ?? null)}
      />
      <ChartDataDisclosure title="Elevation" samples={samples} value={(sample) => `${(sample.altitude ?? 0).toFixed(0)} m`} onPointHover={onPointHover} />
    </>
  );
}
