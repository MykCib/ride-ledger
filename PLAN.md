# Ride Analytics Dashboard Plan

## Current State

- XOSS FIT files are downloaded automatically.
- Workouts are parsed and displayed in a local website.
- Routes are shown individually and as a combined map.
- Weather data is fetched from Open-Meteo and cached.
- Weekly distance, speed charts, and map-linked hovering are implemented.
- The dashboard count is derived dynamically from the downloaded FIT files.
- Available data includes GPS, speed, altitude, distance, temperature, and timestamps.
- Heart-rate and cadence values are currently zero and should not be used.

## Phase 1: Ride Performance

- Add fastest 1 km section.
- Add fastest 2 km section.
- Add fastest 5 km section.
- Add personal-best records for repeated route sections.
- Add speed distribution histogram.
- Add elevation profile chart.
- Add climbing rate and descent rate.
- Add moving time versus elapsed time.
- Add estimated stopped time.
- Add stop count and stop durations.

## Phase 2: Commute Analysis

- Automatically group rides by route direction.
- Detect outbound and return routes.
- Compare outbound and return performance.
- Show typical departure time.
- Show typical arrival time.
- Show average commute duration.
- Show distance variation between repeated rides.
- Show weekday riding patterns.
- Show departure-hour patterns.
- Add a riding activity calendar heatmap.

## Phase 3: Route Segments

- Divide repeated routes into geographic segments.
- Detect frequently repeated road sections.
- Calculate average speed per segment.
- Track fastest time through each segment.
- Show segment personal records.
- Show number of rides through each segment.
- Compare segment performance by direction.
- Color route lines by speed.
- Color route lines by elevation.
- Allow selecting a segment directly on the map.

## Phase 4: Weather Analysis

- Compare speed against temperature.
- Compare speed against wind speed.
- Compare rides in rain versus dry conditions.
- Estimate headwind and tailwind based on route direction.
- Show weather conditions along the route.
- Display weather markers on the route map.
- Identify weather conditions associated with fastest rides.
- Compare outbound and return weather differences.
- Cache all weather responses locally.

## Phase 5: Map Features

- Add animated ride playback.
- Add a time slider for ride playback.
- Show the moving position on the route.
- Display speed while playing back a ride.
- Display altitude while playing back a ride.
- Display weather conditions while playing back a ride.
- Add route start and finish markers.
- Add a combined route-density map.
- Highlight roads used most often.
- Add selectable map layers.

## Phase 6: Data Quality

- Detect GPS signal gaps.
- Detect invalid GPS points.
- Detect unrealistic speed spikes.
- Detect unusually long stops.
- Detect incomplete recordings.
- Detect suspicious distance values.
- Show a data-quality warning per workout.
- Add a raw FIT-file download link.
- Preserve the original FIT files unchanged.

## Phase 7: Dashboard Improvements

- Add filters by date range.
- Add filters by weekday.
- Add filters by route direction.
- Add filters by distance.
- Add filters by weather.
- Add sorting by speed, distance, duration, or date.
- Add a search field.
- Add monthly and yearly summaries.
- Add personal records summary.
- Add recent-workout highlights.
- Add automatic dashboard refresh after new downloads.

## Recommended Implementation Order

1. Stop detection and moving-versus-elapsed-time analysis.
2. Automatic outbound and return route grouping.
3. Repeated route segment detection.
4. Personal-best segment tracking.
5. Elevation profile and climbing statistics.
6. Weather-versus-performance analysis.
7. Calendar and weekday analysis.
8. Animated route playback.
9. Data-quality checks.
10. Advanced map layers and filters.

## Data Limitations

- Heart-rate data is unavailable or zero in the current files.
- Cadence data is unavailable or zero in the current files.
- Historical weather is estimated from route locations and hourly weather records.
- Older rides are not currently stored on the XOSS device.
- Segment detection will be more reliable after more rides are collected.
