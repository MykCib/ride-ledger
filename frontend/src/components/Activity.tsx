import { BarChart } from './Charts';
import type { ActivityDay, Insights } from '../types';

const weekdayLabels = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];
const hourLabels = Array.from({ length: 24 }, (_, index) => String(index).padStart(2, '0'));

function calendarDate(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function dateKey(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function addDays(value: Date, days: number): Date {
  const result = new Date(value);
  result.setUTCDate(result.getUTCDate() + days);
  return result;
}

function activityCells(days: ActivityDay[]) {
  const first = calendarDate(days[0].date);
  const last = calendarDate(days[days.length - 1].date);
  const start = addDays(first, -((first.getUTCDay() + 6) % 7));
  const end = addDays(last, 6 - ((last.getUTCDay() + 6) % 7));
  const byDate = new Map(days.map((day) => [day.date, day]));
  const maximum = Math.max(...days.map((day) => day.ride_count), 1);
  const cells: Array<{ date: string; count: number; distance: number | null; level: number }> = [];
  for (let date = start; date <= end; date = addDays(date, 1)) {
    const key = dateKey(date);
    const day = byDate.get(key);
    const count = day?.ride_count ?? 0;
    cells.push({
      date: key,
      count,
      distance: day?.distance_km ?? null,
      level: count ? Math.max(1, Math.ceil(count / maximum * 4)) : 0,
    });
  }
  return cells;
}

function ActivityCalendar({ days }: { days: ActivityDay[] }) {
  if (!days.length) return <p className="activity-empty">No dated rides yet.</p>;
  const cells = activityCells(days);
  return (
    <div className="activity-calendar-layout">
      <div className="calendar-labels">{weekdayLabels.map((label) => <span key={label}>{label}</span>)}</div>
      <div className="activity-calendar-grid">
        {cells.map((cell) => (
          <span
            className={`activity-cell level-${cell.level}`}
            key={cell.date}
            title={`${cell.date}: ${cell.count} ride${cell.count === 1 ? '' : 's'}${cell.distance == null ? '' : `, ${cell.distance.toFixed(1)} km`}`}
            aria-label={`${cell.date}: ${cell.count} rides`}
            role="img"
          />
        ))}
      </div>
    </div>
  );
}

export function ActivitySection({ insights }: { insights: Insights | null }) {
  if (!insights) return null;
  const activeDays = insights.calendar.filter((day) => day.ride_count > 0).length;
  return (
    <section className="activity-analysis">
      <div className="section-head"><h2>Activity patterns</h2><span>{activeDays} ACTIVE DAYS</span></div>
      <p className="chart-note activity-note">Ride counts use {insights.timezone}. The hour chart shows when recordings started; the calendar shows each dated ride.</p>
      <div className="activity-charts">
        <div className="chart-card activity-chart">
          <div className="section-head"><h2>Weekday</h2><span>RIDES</span></div>
          <div className="chart-wrap"><BarChart values={insights.weekday_counts} labels={weekdayLabels} fill="rgba(77,107,56,.68)" /></div>
        </div>
        <div className="chart-card activity-chart">
          <div className="section-head"><h2>Departure hour</h2><span>LOCAL HOUR</span></div>
          <div className="chart-wrap"><BarChart values={insights.departure_hour_counts} labels={hourLabels} fill="rgba(90,120,160,.58)" /></div>
        </div>
      </div>
      <div className="calendar-card">
        <div className="section-head"><h2>Riding calendar</h2><span>{insights.calendar.length} DAYS IN ARCHIVE</span></div>
        <ActivityCalendar days={insights.calendar} />
        <p className="chart-note">Darker cells indicate more rides on that day. Hover a cell for its date and distance.</p>
      </div>
    </section>
  );
}
