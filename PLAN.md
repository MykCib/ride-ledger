# Ride Analytics Dashboard Plan

## Current State

- XOSS FIT files are downloaded automatically.
- Workouts are parsed and displayed in a local website.
- Routes are shown individually and as a combined map.
- Weather data is fetched from Open-Meteo and cached.
- Weekly distance, speed charts, and map-linked hovering are implemented.
- The dashboard count is derived dynamically from the downloaded FIT files.
- Repeated endpoint route groups and outbound/return comparisons are displayed.
- Ride details include moving-versus-elapsed time, estimated stopped time, stop counts, and stop intervals.
- Repeated routes are stacked on a grouped map, with endpoint labels persisted by coordinate and editable across all routes.
- Commute cards include median departure and arrival times, average duration, distance variation, and direction-specific performance.
- Repeated directions are normalized into ten geographic segments with ride coverage and segment lengths.
- Segment rows include average speed, average elapsed time, and the fastest observed time with its record ride.
- Ride details include elevation profiles plus climbing and descent rates based on moving time.
- Weather analysis compares speed against temperature and wind, dry versus wet rides, fastest-ride conditions, and route directions.
- Activity patterns include timezone-aware weekday and departure-hour distributions plus a riding calendar heatmap.
- Available data includes GPS, speed, altitude, distance, temperature, and timestamps.
- Heart-rate and cadence values are currently zero and should not be used.

## Phase 1: Ride Performance

- [ ] Add fastest 1 km section.
- [ ] Add fastest 2 km section.
- [ ] Add fastest 5 km section.
- [ ] Add personal-best records for repeated route sections.
- [ ] Add speed distribution histogram.
- [x] Add elevation profile chart.
- [x] Add climbing rate and descent rate.
- [x] Add moving time versus elapsed time.
- [x] Add estimated stopped time.
- [x] Add stop count and stop durations.

## Phase 2: Commute Analysis

- [x] Automatically group rides by route direction.
- [x] Detect outbound and return routes.
- [x] Compare outbound and return performance.
- [x] Show typical departure time.
- [x] Show typical arrival time.
- [x] Show average commute duration.
- [x] Show distance variation between repeated rides.
- [x] Show weekday riding patterns.
- [x] Show departure-hour patterns.
- [x] Add a riding activity calendar heatmap.

## Phase 3: Route Segments

- [x] Divide repeated routes into geographic segments.
- [x] Detect frequently repeated road sections.
- [x] Calculate average speed per segment.
- [x] Track fastest time through each segment.
- [x] Show segment personal records.
- [x] Show number of rides through each segment.
- [ ] Compare segment performance by direction.
- [ ] Color route lines by speed.
- [ ] Color route lines by elevation.
- [ ] Allow selecting a segment directly on the map.

## Phase 4: Weather Analysis

- [x] Compare speed against temperature.
- [x] Compare speed against wind speed.
- [x] Compare rides in rain versus dry conditions.
- [ ] Estimate headwind and tailwind based on route direction.
- [ ] Show weather conditions along the route.
- [ ] Display weather markers on the route map.
- [x] Identify weather conditions associated with fastest rides.
- [x] Compare outbound and return weather differences.
- [x] Cache all weather responses locally.

## Phase 5: Map Features

- [ ] Add animated ride playback.
- [ ] Add a time slider for ride playback.
- [ ] Show the moving position on the route.
- [ ] Display speed while playing back a ride.
- [ ] Display altitude while playing back a ride.
- [ ] Display weather conditions while playing back a ride.
- [ ] Add route start and finish markers.
- [ ] Add a combined route-density map.
- [ ] Highlight roads used most often.
- [ ] Add selectable map layers.

## Phase 6: Data Quality

- [ ] Detect GPS signal gaps.
- [ ] Detect invalid GPS points.
- [ ] Detect unrealistic speed spikes.
- [ ] Detect unusually long stops.
- [ ] Detect incomplete recordings.
- [ ] Detect suspicious distance values.
- [ ] Show a data-quality warning per workout.
- [ ] Add a raw FIT-file download link.
- [x] Preserve the original FIT files unchanged.

## Phase 7: Dashboard Improvements

- [ ] Add filters by date range.
- [ ] Add filters by weekday.
- [ ] Add filters by route direction.
- [ ] Add filters by distance.
- [ ] Add filters by weather.
- [ ] Add sorting by speed, distance, duration, or date.
- [ ] Add a search field.
- [ ] Add monthly and yearly summaries.
- [ ] Add personal records summary.
- [ ] Add recent-workout highlights.
- [ ] Add automatic dashboard refresh after new downloads.

## Recommended Implementation Order

1. [x] Stop detection and moving-versus-elapsed-time analysis.
2. [x] Automatic outbound and return route grouping.
3. [x] Repeated route segment detection.
4. [x] Personal-best segment tracking.
5. [x] Elevation profile and climbing statistics.
6. [x] Weather-versus-performance analysis.
7. [x] Calendar and weekday analysis.
8. [ ] Animated route playback.
9. [ ] Data-quality checks.
10. [ ] Advanced map layers and filters.

## Data Limitations

- Heart-rate data is unavailable or zero in the current files.
- Cadence data is unavailable or zero in the current files.
- Historical weather is estimated from route locations and hourly weather records.
- Wind direction is not currently cached, so headwind and tailwind analysis remains pending.
- Older rides are not currently stored on the XOSS device.
- Segment detection will be more reliable after more rides are collected.
