# Ride Ledger UX/UI Design Plan

## Goal

Make Ride Ledger feel calm, navigable, and useful without hiding the detail that
makes the archive valuable. The interface should help a rider answer one
question at a time:

- Overview: What happened recently?
- Rides: Which workout do I want to inspect?
- Routes: Where do I repeatedly ride?
- Insights: What patterns are emerging?

The plan is inspired by the [Scandinavian Design skill](https://github.com/ericzakariasson/scandinavian-design), adapted for a data-heavy personal analytics product. Comprehension, wayfinding, accessibility, and useful density take priority over stylistic minimalism.

## Preserve

- The existing Overview, Rides, Routes, and Insights information architecture.
- The Manrope and DM Mono type pairing unless a replacement clearly improves readability.
- The lime brand accent, dark identity surfaces, and semantic warning colors.
- Route-group colors where color identifies a route or direction.
- The existing map, chart, playback, filtering, endpoint naming, FIT download, and data-quality capabilities.
- Direct ride URLs such as `/rides/{rideId}`.

Do not force the product into strict monochrome. Removing colors that encode route groups, warnings, selected states, or brand identity would reduce comprehension.

## Design Principles

- Put comprehension and wayfinding before decoration.
- Give every page one dominant purpose and one obvious next action.
- Use hierarchy, alignment, and whitespace before adding another card or divider.
- Keep related data close and separate unrelated chapters with larger gaps.
- Prefer a few meaningful surfaces over a wall of equal-weight cards.
- Use a restrained 8px spacing rhythm and consistent control heights.
- Keep supporting copy short, specific, and readable.
- Use sentence case for navigation and controls; reserve small uppercase labels for intentional metadata or brand treatment.
- Keep color restrained, but preserve colors that communicate state or data identity.
- Use motion only for spatial continuity, feedback, or playback. Honor `prefers-reduced-motion`.
- Treat mobile as a separate composition, not a narrow desktop layout.

## Page Plan

### Overview

Purpose: orient the rider and provide a fast path into the archive.

- Keep the large editorial hero only on the Overview page.
- Replace large repeated hero treatments on inner pages with compact page headers.
- Make the latest ride the primary content block, including date, distance, speed, and an obvious open action.
- Keep the main archive totals, but reduce their visual competition with the latest ride.
- Retain the weekly distance chart as the main trend view.
- Keep three concise entry points for the archive, routes, and insights.
- Add a small sync status showing the last data refresh and whether new files were found.
- Add a recent-workout highlight when there is enough data, without turning Overview into another full archive.

### Rides Archive

Purpose: find a workout quickly and understand the current result set.

- Preserve the sortable ride list and direct ride links.
- Store search, date range, weekday, direction, distance, and sort state in URL query parameters.
- Preserve filter state when navigating to a ride and returning with browser back.
- Show a compact active-filter summary and a clear result count.
- Keep filters expanded on desktop and move them into a mobile disclosure panel.
- Keep the search field first because it is the fastest route to a known ride.
- Make each row scan as date, route/direction, duration, distance, and quality status.
- Use subtle alternating row treatment or spacing instead of adding a heavy border to every row.
- Keep keyboard focus, pointer hover, selected state, and quality warnings visibly distinct.
- Provide a useful empty state that explains which filters can be cleared.

### Ride Detail

Purpose: understand one workout without scrolling through an undifferentiated metric wall.

- Add a clear Back to rides action and preserve the originating archive query string.
- Make the route map the dominant visual element near the top of the page.
- Keep date, route direction, distance, average speed, and moving time in the first summary block.
- Group the remaining content into explicit chapters:
  - Route and playback
  - Pace and speed
  - Elevation
  - Stops and timing
  - Weather
  - Data quality and original FIT file
- Use tabs on desktop only if they do not hide important context; use accordions or stacked chapters on mobile.
- Keep the selected chapter in the URL when practical so refresh and sharing remain predictable.
- Keep chart hover linked to the map and make the active point obvious without relying on color alone.
- Keep the playback controls close to the map and provide a reduced-motion behavior.
- Show quality warnings near the affected data rather than burying them at the bottom.
- Show unavailable metrics as explained states, not empty-looking placeholders.

### Routes

Purpose: understand repeated roads and compare route directions.

- Make the grouped route map and route selection the central interaction.
- Let a route card highlight its tracks on the map; let a map route reveal its group and direction.
- Visually distinguish the selected route from neighboring routes without changing the meaning of group colors.
- Keep endpoint labels and rename behavior discoverable without making the map controls dominant.
- Present each route group as a compact summary with total rides, outbound/return comparison, and a link to matching rides.
- Keep repeated segment analysis below the route overview and make the selected group context persistent.
- Add segment selection from the map later, using the existing segment records rather than creating a separate analysis model.
- Add speed and elevation line coloring only with a legend and an accessible non-color explanation.
- Avoid showing the full route list and every segment table at equal visual weight.

### Insights

Purpose: identify meaningful archive-level patterns.

- Start with a compact Highlights block containing fastest average, longest ride, recent change, and available record counts.
- Follow with three clear chapters:
  - Performance records: fastest 1, 2, and 5 km sections plus speed distribution.
  - Weather and pace: temperature, wind, dry/wet, and route-direction comparisons.
  - Activity patterns: weekday, departure hour, and calendar.
- Keep one dominant chart per chapter and move explanatory detail into short notes or disclosures.
- Make archive records link to their source rides.
- Avoid presenting every chart as a separate bordered card when whitespace and a shared chapter container are sufficient.
- Explain data coverage beside each analysis, especially weather availability and route sample coverage.
- Add monthly and yearly summaries only after the chapter hierarchy is stable.
- Add weather filters as a focused control for the archive, not another always-visible filter row.

## Shared Visual System

### Layout

- Use compact inner-page headers and reserve large display type for Overview or major chapter openings.
- Use a consistent maximum content width and left alignment across text, controls, charts, and maps.
- Use desktop two-column layouts only when the relationship between columns is meaningful.
- On mobile, stack content in task order: context, primary action, result, supporting detail.
- Keep section transitions spacious, but measure the rendered gap so whitespace does not become dead space.

### Surfaces and Borders

- Prefer the existing paper, card, dark, and line tokens over new one-off colors.
- Reduce the number of boxed panels, especially around secondary analytics.
- Keep borders for dense tables, form controls, map frames, and boundaries that improve comprehension.
- Use whitespace or subtle row treatment for repeated records when a border adds no meaning.
- Avoid decorative shadows, gradients, and ornamental background treatments.
- Normalize equivalent buttons, inputs, tags, and cards to shared heights, padding, radii, and focus styles.

### Typography

- Preserve the current type families while reducing unnecessary weight changes.
- Use size and whitespace as the primary hierarchy tools.
- Keep body text at a comfortable reading size and limit explanatory copy width.
- Reduce all-caps usage in navigation and controls; keep intentional eyebrow metadata visually quiet.
- Keep chart labels and data values legible at mobile widths.

### Color and State

- Use ink, muted text, paper, card, and line tokens consistently.
- Keep lime for product identity and selected primary emphasis.
- Keep route-group colors for route identity and provide labels or patterns where needed.
- Keep warning, error, success, live, selected, and disabled states distinguishable by shape, label, or border as well as color.
- Use chart color as an encoding with a visible label or legend, not as decoration.
- Check contrast for muted text, map controls, form fields, and focus rings.

## Interaction Improvements

- Preserve navigation position and active state on every route.
- Add visible focus states to all links, buttons, inputs, selects, map controls, and disclosure triggers.
- Make touch targets at least comfortable on small screens, especially filters, playback, and map actions.
- Keep destructive or reset actions visually secondary but clearly identifiable.
- Add chapter-level loading states instead of leaving large blank areas while APIs resolve.
- Make errors local to the affected chapter and provide a useful recovery action.
- Make no-data messages explain why data is unavailable and what would make it appear.
- Keep hover-only affordances optional; all important actions must work by keyboard and touch.
- Respect reduced-motion preferences for navigation transitions, card movement, and playback.

## Performance Improvements

- Fetch only the data needed by the current page where practical.
- Lazy-load maps and charts below the first viewport.
- Avoid initializing hidden charts or maps before their chapter is opened.
- Keep route and ride detail prefetching, but avoid prefetching large data for every page.
- Show useful content as soon as workouts are available instead of waiting for all analytics.

## Implementation Order

Implementation items below reflect work shipped in commits through `30d1649`.
Verification items are checked only where the previous validation directly covered
the stated requirement.

### Phase 1: Hierarchy and Wayfinding

- [x] Replace inner-page hero blocks with compact page headers.
- [x] Add consistent page-level back and context actions.
- [x] Rework Overview around the latest ride, totals, weekly trend, and three entry points.
- [x] Add chapter-level loading, empty, and error states.
- [x] Audit navigation, focus, active, hover, pressed, and disabled states.

### Phase 2: Rides and Detail

- [x] Persist archive filters and sort order in URL query parameters.
- [x] Add active-filter summary and clearer empty-result actions.
- [x] Recompose ride detail around map, summary metrics, and progressive-disclosure chapters.
- [x] Add Back to rides behavior that preserves archive state.
- [x] Improve mobile archive-to-detail flow and touch targets.

### Phase 3: Route Exploration

- [x] Connect route cards and map selection.
- [x] Highlight selected route groups and expose matching ride links.
- [x] Add direct map segment selection.
- [x] Add speed/elevation map coloring with legends and non-color labels.

### Phase 4: Insights and Archive Summaries

- [x] Recompose Insights into Highlights, Performance, Weather, and Activity chapters.
- [x] Add recent-workout highlights.
- [x] Add monthly and yearly summaries.
- [x] Add weather-aware archive filtering with a compact disclosure control.
- [x] Add comparison copy that explains sample size and data coverage.

### Phase 5: System and Performance Polish

- [x] Normalize spacing, borders, controls, radii, and typography across all pages.
- [x] Reduce unnecessary all-caps labels and secondary card containers.
- [x] Add page-specific data loading and lazy chart/map initialization.
- [x] Add automatic dashboard refresh after new downloads without interrupting active detail work.
- [x] Add weather readouts to playback when route-level weather data becomes available.

## Verification Checklist

- [x] Verify Overview, Rides, Routes, Insights, and ride-detail URLs at desktop width.
- [ ] Verify the same flows at 390px mobile width without horizontal overflow or clipped controls.
- [x] Verify browser back/forward behavior with active ride filters.
- [x] Verify keyboard navigation, visible focus, and Escape behavior for disclosures and controls.
- [ ] Verify loading, empty, partial-data, API-error, and data-quality-warning states.
- [x] Verify route and chart interactions without relying on color alone.
- [ ] Verify reduced-motion behavior for navigation, hover movement, and playback.
- [ ] Check browser console errors and network waterfalls.
- [x] Run `npm run typecheck`, `npm run build`, Python tests, `git diff --check`, and React Doctor.
- [x] Review long pages chapter by chapter rather than checking only the first viewport.

## Success Criteria

- A first-time user can tell where they are and what to do next without reading instructions.
- Opening a ride does not require scanning unrelated archive analytics.
- The most important content on every page is visible early without removing useful data.
- Filters, navigation, maps, charts, playback, warnings, and downloads remain reachable and understandable.
- Desktop feels spacious and editorial; mobile feels deliberate rather than compressed.
- The visual system feels quiet because hierarchy is clear, not because information has been hidden.
