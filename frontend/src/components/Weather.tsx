import { formatSpeed } from '../format';
import { Link } from 'react-router-dom';
import type { WeatherBin, WeatherConditionStats, WeatherAnalysis } from '../types';
import { LineChart } from './Charts';
import { MetricSeparator } from './MetricSeparator';

function value(value: number | null, unit: string): string {
  return value == null ? '—' : `${value.toFixed(1)}${unit}`;
}

function chartBins(bins: WeatherBin[]): WeatherBin[] {
  return bins.filter((bin) => bin.average_speed_kmh != null);
}

function WeatherChart({ title, label, bins, fill }: { title: string; label: string; bins: WeatherBin[]; fill: string }) {
  const visible = chartBins(bins);
  return (
    <div className="chart-card weather-chart">
      <div className="section-head"><h2>{title}</h2><span>{label}</span></div>
      {visible.length ? (
        <div className="chart-wrap"><LineChart values={visible.map((bin) => bin.average_speed_kmh ?? 0)} labels={visible.map((bin) => bin.label)} fill={fill} /></div>
      ) : <p className="weather-empty">Not enough weather records yet.</p>}
      <p className="chart-note">Average ride speed per weather range.</p>
    </div>
  );
}

function ConditionCard({ label, stats }: { label: string; stats: WeatherConditionStats }) {
  return (
    <article className="weather-condition-card">
      <p className="eyebrow">{label} RIDES</p>
      <strong>{stats.count}</strong>
      <span>{formatSpeed(stats.average_speed_kmh)} average</span>
      <p>{value(stats.average_temperature_c, '°C')} <MetricSeparator /> {value(stats.average_wind_kmh, ' km/h wind')}</p>
    </article>
  );
}

function DirectionWeather({ title, stats }: { title: string; stats: WeatherConditionStats }) {
  return (
    <div className="weather-direction-stat">
      <div><span>{title}</span><b>{stats.count} rides</b></div>
      <strong>{formatSpeed(stats.average_speed_kmh)}</strong>
      <small>{value(stats.average_temperature_c, '°C')} <MetricSeparator /> {value(stats.average_wind_kmh, ' km/h wind')} <MetricSeparator /> {value(stats.average_precipitation_mm, ' mm rain')}</small>
    </div>
  );
}

function FastestWeather({ analysis }: { analysis: WeatherAnalysis }) {
  const fastest = analysis.fastest;
  if (!fastest) return <article className="weather-fastest weather-empty-card">No weather-linked speed record yet.</article>;
  const date = fastest.date ? new Date(fastest.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : fastest.ride_id;
  return (
    <article className="weather-fastest">
      <p className="eyebrow">FASTEST WEATHER RIDE</p>
      <h3>{formatSpeed(fastest.speed_kmh)}</h3>
      <span>{date}</span>
      <p>{value(fastest.temperature_c, '°C')} <MetricSeparator /> {value(fastest.wind_kmh, ' km/h wind')} <MetricSeparator /> {value(fastest.precipitation_mm, ' mm rain')}</p>
      <Link className="weather-ride-link" to={`/rides/${fastest.ride_id}`}>Open ride <b>-&gt;</b></Link>
    </article>
  );
}

export function WeatherSection({ analysis, error, onRetry }: { analysis: WeatherAnalysis | null; error?: string; onRetry?: () => void }) {
  if (!analysis && error) {
    return <section className="weather-analysis"><div className="section-head"><h2>Weather and pace</h2><span>UNAVAILABLE</span></div><div className="data-empty"><strong>Weather analysis could not be loaded.</strong><p>Try again after the weather cache or archive index is available.</p>{onRetry && <button type="button" className="weather-retry" onClick={onRetry}>Retry</button>}</div></section>;
  }
  if (!analysis) return null;
  if (!analysis.available_rides) {
    return <section className="weather-analysis"><div className="section-head"><h2>Weather and pace</h2><span>NO LINKED RIDES</span></div><div className="data-empty"><strong>Weather coverage is not available yet.</strong><p>Run the weather cache after a ride is downloaded to compare temperature, wind, and precipitation with pace.</p></div></section>;
  }
  return (
    <section className="weather-analysis">
      <div className="section-head"><h2>Weather and pace</h2><span>{analysis.available_rides}/{analysis.total_rides} RIDES LINKED</span></div>
      {error && onRetry && <div className="weather-refresh-error"><span>{error}</span><button type="button" onClick={onRetry}>Retry</button></div>}
      <p className="chart-note weather-note">Historical Open-Meteo conditions are compared with each ride's average speed. Rain is any cached precipitation above zero.</p>
      <div className="weather-charts">
        <WeatherChart title="Temperature" label="°C · AVERAGE SPEED" bins={analysis.temperature_bins} fill="rgba(212,91,63,.25)" />
        <WeatherChart title="Wind" label="KM/H · AVERAGE SPEED" bins={analysis.wind_bins} fill="rgba(90,120,160,.25)" />
      </div>
      <div className="weather-summary">
        <div className="weather-conditions">
          <div className="section-head"><h2>Dry versus wet</h2><span>PERFORMANCE</span></div>
          <div className="weather-condition-grid metric-grid">
            <ConditionCard label="Dry" stats={analysis.conditions.dry} />
            <ConditionCard label="Wet" stats={analysis.conditions.wet} />
          </div>
        </div>
        <FastestWeather analysis={analysis} />
      </div>
      {analysis.directions.length > 0 && (
        <div className="weather-directions">
          <div className="section-head"><h2>Weather by direction</h2><span>ROUTE COMPARISON</span></div>
          <div className="weather-direction-list">
            {analysis.directions.map((direction) => (
              <article className="weather-direction-card" key={direction.group_id}>
                <h3>{direction.label}</h3>
                <div className="metric-grid"><DirectionWeather title="Outbound" stats={direction.outbound} /><DirectionWeather title="Return" stats={direction.return} /></div>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
