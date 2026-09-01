from datetime import datetime, timedelta, timezone
from bisect import bisect_left, bisect_right
import json
from math import atan2, cos, floor, isfinite, radians, sin, sqrt
import os
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, render_template, request, send_file
from fitparse import FitFile

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
app = Flask(__name__)
app.json.sort_keys = False
_insights_cache = None
_insights_signature = None
_workouts_cache = None
_workouts_signature = None
_routes_cache = None
_routes_signature = None
_tracks_cache = None
_tracks_signature = None
_commutes_cache = None
_commutes_signature = None
_segments_cache = None
_segments_signature = None
_weather_analysis_cache = None
_weather_analysis_signature = None
_detail_cache = {}
_routes_lock = Lock()
WORKOUTS_CACHE_VERSION = 5
COMMUTES_CACHE_VERSION = 4
SEGMENTS_CACHE_VERSION = 2
WEATHER_ANALYSIS_CACHE_VERSION = 2
INSIGHTS_CACHE_VERSION = 5
ROUTES_CACHE_VERSION = 2
LOCATION_NAMES_PATH = DATA / "location_names.json"
DEFAULT_ANALYTICS_TIMEZONE = "Europe/Vilnius"
STOP_SPEED_MPS = 0.5
MIN_STOP_SECONDS = 5
DISTANCE_TOLERANCE_M = 1.0
MAX_STOP_DISTANCE_M = 5.0
RECORD_INTERVAL_SECONDS = 1
ENDPOINT_CLUSTER_RADIUS_M = 500
DAY_SECONDS = 24 * 60 * 60
ROUTE_SEGMENT_COUNT = 10
FASTEST_SECTION_DISTANCES_M = (1000, 2000, 5000)
SPEED_DISTRIBUTION_BIN_KMH = 5
GPS_GAP_SECONDS = 5
LONG_STOP_SECONDS = 15 * 60
MAX_REASONABLE_SPEED_KMH = 120
DISTANCE_MISMATCH_METERS = 500
DISTANCE_MISMATCH_RATIO = 0.20


def degrees(value):
    value = finite_number(value) if value is not None else None
    return value * 180.0 / 2**31 if value is not None else None


def number(value, digits=1):
    return round(float(value), digits) if value is not None else None


def finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def vertical_rate(elevation, moving):
    try:
        elevation = float(elevation)
        moving = float(moving)
    except (TypeError, ValueError):
        return None
    if not isfinite(elevation) or not isfinite(moving) or moving <= 0:
        return None
    return number(elevation / moving * 3600, 1)


def as_utc(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def timestamp_iso(value):
    value = as_utc(value)
    return value.isoformat() if isinstance(value, datetime) else value


def distance_meters(first, second):
    latitude_one, longitude_one = radians(first[0]), radians(first[1])
    latitude_two, longitude_two = radians(second[0]), radians(second[1])
    delta_latitude = latitude_two - latitude_one
    delta_longitude = longitude_two - longitude_one
    component = sin(delta_latitude / 2) ** 2 + cos(latitude_one) * cos(latitude_two) * sin(delta_longitude / 2) ** 2
    return 6371000 * 2 * atan2(sqrt(component), sqrt(1 - component))


def location_label(index):
    value = index + 1
    label = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def saved_location_names():
    if not LOCATION_NAMES_PATH.is_file():
        return []
    try:
        payload = json.loads(LOCATION_NAMES_PATH.read_text())
        entries = payload.get("locations", []) if isinstance(payload, dict) else []
        if not isinstance(entries, list):
            return []
        return [
            entry for entry in entries
            if isinstance(entry, dict)
            and isinstance(entry.get("lat"), (int, float))
            and isinstance(entry.get("lon"), (int, float))
            and isinstance(entry.get("name"), str)
            and entry["name"].strip()
        ]
    except (OSError, ValueError, json.JSONDecodeError):
        return []


def apply_location_names(locations):
    entries = saved_location_names()
    for location in locations.values():
        point = (location["lat"], location["lon"])
        saved = next(
            (entry for entry in entries if distance_meters(point, (entry["lat"], entry["lon"])) <= ENDPOINT_CLUSTER_RADIUS_M),
            None,
        )
        if saved:
            location["label"] = saved["name"].strip()


def update_location_name(location_id, name):
    locations, _ = cluster_route_endpoints(route_overlay_data())
    location = next((item for item in locations.values() if item["id"] == location_id), None)
    if location is None:
        return None

    entries = saved_location_names()
    matching = next(
        (entry for entry in entries if distance_meters((location["lat"], location["lon"]), (entry["lat"], entry["lon"])) <= ENDPOINT_CLUSTER_RADIUS_M),
        None,
    )
    if name:
        if matching:
            matching["lat"] = location["lat"]
            matching["lon"] = location["lon"]
            matching["name"] = name
        else:
            entries.append({"lat": location["lat"], "lon": location["lon"], "name": name})
    elif matching:
        entries.remove(matching)

    LOCATION_NAMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCATION_NAMES_PATH.write_text(json.dumps({"locations": entries}, indent=2) + "\n")
    return location


def cluster_route_endpoints(routes):
    endpoints = []
    for route in routes:
        points = route.get("points", [])
        if len(points) >= 2:
            endpoints.extend([(route["id"], "start", points[0]), (route["id"], "end", points[-1])])

    clusters = []
    endpoint_clusters = {}
    for route_id, side, point in endpoints:
        matching = next(
            (cluster for cluster in clusters if distance_meters(point, cluster["center"]) <= ENDPOINT_CLUSTER_RADIUS_M),
            None,
        )
        if matching is None:
            matching = {"points": [], "center": point}
            clusters.append(matching)
        matching["points"].append(point)
        matching["center"] = [
            sum(item[0] for item in matching["points"]) / len(matching["points"]),
            sum(item[1] for item in matching["points"]) / len(matching["points"]),
        ]
        endpoint_clusters[(route_id, side)] = matching

    clusters.sort(key=lambda cluster: (cluster["center"][0], cluster["center"][1]))
    locations = {}
    cluster_ids = {id(cluster): index for index, cluster in enumerate(clusters)}
    for index, cluster in enumerate(clusters):
        locations[index] = {
            "id": f"location-{index + 1}",
            "label": location_label(index),
            "lat": round(cluster["center"][0], 6),
            "lon": round(cluster["center"][1], 6),
        }

    route_locations = {}
    for route_id, side, _ in endpoints:
        route_locations.setdefault(route_id, {})[side] = cluster_ids[id(endpoint_clusters[(route_id, side)])]
    return locations, route_locations


def median_value(values):
    values = sorted(values)
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def analytics_timezone():
    configured = os.environ.get("RIDE_LEDGER_TIMEZONE", DEFAULT_ANALYTICS_TIMEZONE).strip()
    if not configured:
        configured = "UTC"
    try:
        return configured, ZoneInfo(configured)
    except ZoneInfoNotFoundError:
        app.logger.warning("Unknown RIDE_LEDGER_TIMEZONE %r; using UTC", configured)
        return "UTC", timezone.utc


def item_datetime(item):
    value = item.get("date")
    if isinstance(value, datetime):
        return as_utc(value)
    if not isinstance(value, str):
        return None
    try:
        return as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def elapsed_seconds(item):
    value = finite_number(item.get("elapsed_seconds"))
    return value if value is not None and value >= 0 else None


def numeric_values(items, field):
    values = []
    for item in items:
        value = finite_number(item.get(field))
        if value is not None:
            values.append(value)
    return values


def circular_median(values, period=DAY_SECONDS):
    values = sorted(value % period for value in values)
    if not values:
        return None
    if len(values) == 1:
        return values[0]

    gaps = [
        (values[(index + 1) % len(values)] - values[index]) % period
        for index in range(len(values))
    ]
    largest_gap = max(range(len(gaps)), key=gaps.__getitem__)
    start = (largest_gap + 1) % len(values)
    ordered = values[start:] + values[:start]
    unwrapped = [ordered[0]]
    offset = 0
    for previous, value in zip(ordered, ordered[1:]):
        if value < previous:
            offset += period
        unwrapped.append(value + offset)
    return median_value(unwrapped) % period


def clock_seconds(value, timezone_value):
    value = value.astimezone(timezone_value)
    return value.hour * 60 * 60 + value.minute * 60 + value.second + value.microsecond / 1_000_000


def typical_time(items, timezone_value, arrival=False):
    values = []
    for item in items:
        value = item_datetime(item)
        if value is None:
            continue
        if arrival:
            elapsed = elapsed_seconds(item)
            if elapsed is None:
                continue
            value += timedelta(seconds=float(elapsed))
        values.append(clock_seconds(value, timezone_value))
    if not values:
        return None

    typical_second = circular_median(values)
    typical_minute = int(typical_second / 60 + 0.5) % (24 * 60)
    return f"{typical_minute // 60:02d}:{typical_minute % 60:02d}"


def distance_variation(items):
    values = numeric_values(items, "distance_km")
    if not values:
        return None
    average = sum(values) / len(values)
    return number(sqrt(sum((value - average) ** 2 for value in values) / len(values)), 2)


def departure_seconds(item, timezone_value):
    value = item_datetime(item)
    if value is None:
        return None
    return clock_seconds(value, timezone_value)


def average_value(items, field, digits=1):
    values = numeric_values(items, field)
    return number(sum(values) / len(values), digits) if values else None


def average_elapsed(items):
    values = [value for item in items if (value := elapsed_seconds(item)) is not None]
    return number(sum(values) / len(values), 0) if values else None


def route_performance(items, timezone_value=None):
    if timezone_value is None:
        _, timezone_value = analytics_timezone()
    average_elapsed_seconds = average_elapsed(items)
    return {
        "count": len(items),
        "ride_ids": [item["id"] for item in items],
        "typical_departure_time": typical_time(items, timezone_value),
        "typical_arrival_time": typical_time(items, timezone_value, arrival=True),
        "average_commute_seconds": average_elapsed_seconds,
        "average_distance_km": average_value(items, "distance_km", 2),
        "distance_variation_km": distance_variation(items),
        "average_speed_kmh": average_value(items, "average_speed_kmh", 1),
        "average_moving_seconds": average_value(items, "moving_seconds", 0),
        "average_elapsed_seconds": average_elapsed_seconds,
        "average_stopped_seconds": average_value(items, "estimated_stopped_seconds", 0),
    }


def build_commute_analysis(items, routes):
    timezone_name, timezone_value = analytics_timezone()
    locations, route_locations = cluster_route_endpoints(routes)
    apply_location_names(locations)
    items_by_id = {item["id"]: item for item in items}
    grouped = {}
    assignments = {}

    for route in routes:
        route_id = route["id"]
        location_pair = route_locations.get(route_id, {})
        start_location = location_pair.get("start")
        end_location = location_pair.get("end")
        item = items_by_id.get(route_id)
        if item is None or start_location is None or end_location is None:
            continue
        if start_location == end_location:
            assignments[route_id] = {"group_id": None, "direction": "loop", "label": "Local loop"}
            continue
        pair = tuple(sorted((start_location, end_location)))
        grouped.setdefault(pair, {"forward": [], "reverse": []})[
            "forward" if (start_location, end_location) == pair else "reverse"
        ].append(item)

    groups = []
    for (first_location, second_location), directions in sorted(grouped.items()):
        forward = directions["forward"]
        reverse = directions["reverse"]
        forward_departures = [departure_seconds(item, timezone_value) for item in forward]
        reverse_departures = [departure_seconds(item, timezone_value) for item in reverse]
        forward_departures = [value for value in forward_departures if value is not None]
        reverse_departures = [value for value in reverse_departures if value is not None]
        if forward and reverse and forward_departures and reverse_departures:
            outbound_is_forward = circular_median(forward_departures) <= circular_median(reverse_departures)
        elif len(forward) != len(reverse):
            outbound_is_forward = len(forward) > len(reverse)
        else:
            outbound_is_forward = True

        outbound_items = forward if outbound_is_forward else reverse
        return_items = reverse if outbound_is_forward else forward
        origin_location = first_location if outbound_is_forward else second_location
        destination_location = second_location if outbound_is_forward else first_location
        group_id = f"route-{first_location + 1}-{second_location + 1}"
        origin = locations[origin_location]
        destination = locations[destination_location]
        group = {
            "id": group_id,
            "label": f"{locations[first_location]['label']} <-> {locations[second_location]['label']}",
            "origin": origin,
            "destination": destination,
            "total_rides": len(outbound_items) + len(return_items),
            "outbound": route_performance(outbound_items, timezone_value),
            "return": route_performance(return_items, timezone_value),
        }
        groups.append(group)
        outbound_label = f"{origin['label']} -> {destination['label']}"
        return_label = f"{destination['label']} -> {origin['label']}"
        for item in outbound_items:
            assignments[item["id"]] = {"group_id": group_id, "direction": "outbound", "label": outbound_label}
        for item in return_items:
            assignments[item["id"]] = {"group_id": group_id, "direction": "return", "label": return_label}

    return {
        "timezone": timezone_name,
        "groups": groups,
        "assignments": assignments,
        "locations": list(locations.values()),
    }


def track_progress(track):
    records = []
    for point in track or []:
        try:
            latitude = float(point["lat"])
            longitude = float(point["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if isfinite(latitude) and isfinite(longitude):
            distance = point.get("distance_m")
            try:
                distance = float(distance)
            except (TypeError, ValueError):
                distance = None
            timestamp = as_utc(point.get("t"))
            records.append({
                "point": [latitude, longitude],
                "distance": distance if distance is not None and isfinite(distance) else None,
                "timestamp": timestamp if isinstance(timestamp, datetime) else None,
                "speed": finite_number(point.get("speed")),
            })
    points = [record["point"] for record in records]
    if len(points) < 2:
        return [], 0

    raw_distances = [record["distance"] for record in records]
    valid_raw = all(value is not None for value in raw_distances)
    valid_raw = valid_raw and all(second >= first for first, second in zip(raw_distances, raw_distances[1:]))
    if valid_raw and raw_distances[-1] > raw_distances[0]:
        # FIT distance is cumulative and avoids adding GPS jitter to every segment.
        cumulative = [value - raw_distances[0] for value in raw_distances]
    else:
        cumulative = [0.0]
        for previous, current in zip(points, points[1:]):
            cumulative.append(cumulative[-1] + distance_meters(previous, current))
    return [
        {
            "point": record["point"],
            "distance": distance,
            "timestamp": record["timestamp"],
            "speed": record.get("speed"),
        }
        for record, distance in zip(records, cumulative)
    ], cumulative[-1]


def interpolate_track_sample(progress, target):
    if target <= progress[0]["distance"]:
        return {"point": progress[0]["point"], "timestamp": progress[0]["timestamp"]}
    for index, current in enumerate(progress[1:], 1):
        current_distance = current["distance"]
        if target <= current_distance:
            previous = progress[index - 1]
            previous_point = previous["point"]
            previous_distance = previous["distance"]
            current_point = current["point"]
            span = current_distance - previous_distance
            ratio = (target - previous_distance) / span if span else 0
            timestamp = None
            if previous["timestamp"] is not None and current["timestamp"] is not None:
                timestamp = previous["timestamp"] + (current["timestamp"] - previous["timestamp"]) * ratio
            return {
                "point": [
                    previous_point[0] + (current_point[0] - previous_point[0]) * ratio,
                    previous_point[1] + (current_point[1] - previous_point[1]) * ratio,
                ],
                "timestamp": timestamp,
            }
    return {"point": progress[-1]["point"], "timestamp": progress[-1]["timestamp"]}


def timestamp_at_distance(progress, distances, target, prefer_last=False):
    if prefer_last:
        index = bisect_right(distances, target)
        if index > 0 and distances[index - 1] == target:
            return progress[index - 1]["timestamp"]
    else:
        index = bisect_left(distances, target)
        if index < len(progress) and distances[index] == target:
            return progress[index]["timestamp"]
    if index <= 0:
        return progress[0]["timestamp"]
    if index >= len(progress):
        return progress[-1]["timestamp"]
    current = progress[index]
    previous = progress[index - 1]
    span = current["distance"] - previous["distance"]
    if not span or previous["timestamp"] is None or current["timestamp"] is None:
        return current["timestamp"]
    ratio = (target - previous["distance"]) / span
    return previous["timestamp"] + (current["timestamp"] - previous["timestamp"]) * ratio


def section_quality_index(progress):
    invalid_points = []
    invalid_ranges = []
    for sample in progress:
        speed = finite_number(sample.get("speed"))
        if speed is not None and (speed < 0 or speed * 3.6 > MAX_REASONABLE_SPEED_KMH):
            invalid_points.append(sample["distance"])
        if sample["timestamp"] is None:
            invalid_points.append(sample["distance"])

    for previous, current in zip(progress, progress[1:]):
        previous_distance = previous["distance"]
        current_distance = current["distance"]
        previous_time = previous["timestamp"]
        current_time = current["timestamp"]
        invalid = previous_time is None or current_time is None or current_time <= previous_time
        if invalid:
            if previous_distance == current_distance:
                invalid_points.append(current_distance)
            else:
                invalid_ranges.append((previous_distance, current_distance))
            continue
        gap_seconds = (current_time - previous_time).total_seconds()
        distance_delta = current_distance - previous_distance
        if gap_seconds > GPS_GAP_SECONDS and distance_delta > DISTANCE_TOLERANCE_M:
            invalid_ranges.append((previous_distance, current_distance))
        elif gap_seconds and distance_delta / gap_seconds * 3.6 > MAX_REASONABLE_SPEED_KMH:
            invalid_ranges.append((previous_distance, current_distance))

    invalid_ranges.sort()
    range_starts = [start for start, _ in invalid_ranges]
    range_max_ends = []
    maximum_end = None
    for _, end in invalid_ranges:
        maximum_end = end if maximum_end is None else max(maximum_end, end)
        range_max_ends.append(maximum_end)
    return {
        "points": sorted(invalid_points),
        "range_starts": range_starts,
        "range_max_ends": range_max_ends,
    }


def section_contains_invalid_data(quality, start_distance, end_distance):
    range_count = bisect_left(quality["range_starts"], end_distance)
    if range_count and quality["range_max_ends"][range_count - 1] > start_distance:
        return True
    point_index = bisect_left(quality["points"], start_distance)
    return point_index < len(quality["points"]) and quality["points"][point_index] <= end_distance


def fastest_section_from_progress(progress, total_distance, target_distance):
    if len(progress) < 2 or total_distance < target_distance or target_distance <= 0:
        return None
    distances = [sample["distance"] for sample in progress]
    candidate_distances = {
        distance
        for distance in distances
        if 0 <= distance <= total_distance - target_distance
    }
    candidate_distances.update(
        distance - target_distance
        for distance in distances
        if 0 <= distance - target_distance <= total_distance - target_distance
    )
    quality = section_quality_index(progress)
    fastest = None
    for start_distance in sorted(candidate_distances):
        end_distance = start_distance + target_distance
        if section_contains_invalid_data(quality, start_distance, end_distance):
            continue
        start_time = timestamp_at_distance(progress, distances, start_distance, prefer_last=True)
        if start_time is None:
            continue
        end_time = timestamp_at_distance(progress, distances, end_distance)
        if end_time is None or end_time <= start_time:
            continue
        duration = (end_time - start_time).total_seconds()
        if duration <= 0:
            continue
        if fastest is None or duration < fastest["time_seconds"]:
            fastest = {
                "time_seconds": duration,
                "speed_kmh": target_distance / duration * 3.6,
                "start_km": start_distance / 1000,
                "end_km": end_distance / 1000,
            }
    if fastest is None:
        return None
    return fastest


def fastest_distance_section(track, target_distance):
    progress, total_distance = track_progress(track)
    section = fastest_section_from_progress(progress, total_distance, target_distance)
    if section is None:
        return None
    return {
        "time_seconds": number(section["time_seconds"], 1),
        "speed_kmh": number(section["speed_kmh"], 1),
        "start_km": number(section["start_km"], 2),
        "end_km": number(section["end_km"], 2),
    }


def resample_route(track, segment_count=ROUTE_SEGMENT_COUNT):
    progress, total_distance = track_progress(track)
    if not progress or total_distance <= 0:
        return None
    samples = [
        interpolate_track_sample(progress, total_distance * index / segment_count)
        for index in range(segment_count + 1)
    ]
    return samples, total_distance


def build_route_segments(groups, tracks):
    segments = []
    for group in groups:
        for direction in ("outbound", "return"):
            performance = group[direction]
            ride_ids = performance["ride_ids"]
            if len(ride_ids) < 2:
                continue
            sampled_routes = []
            for ride_id in ride_ids:
                sampled = resample_route(tracks.get(ride_id, []))
                if sampled is not None:
                    sampled_routes.append({"ride_id": ride_id, "samples": sampled[0], "total_distance": sampled[1]})
            if len(sampled_routes) < 2:
                continue
            for index in range(ROUTE_SEGMENT_COUNT):
                starts = [sampled["samples"][index]["point"] for sampled in sampled_routes]
                ends = [sampled["samples"][index + 1]["point"] for sampled in sampled_routes]
                average_start = [
                    sum(point[axis] for point in starts) / len(starts)
                    for axis in (0, 1)
                ]
                average_end = [
                    sum(point[axis] for point in ends) / len(ends)
                    for axis in (0, 1)
                ]
                average_distance = sum(sampled["total_distance"] for sampled in sampled_routes) / len(sampled_routes)
                segment_performances = []
                for sampled in sampled_routes:
                    start_time = sampled["samples"][index]["timestamp"]
                    end_time = sampled["samples"][index + 1]["timestamp"]
                    if start_time is None or end_time is None or end_time <= start_time:
                        continue
                    duration = (end_time - start_time).total_seconds()
                    distance_km = sampled["total_distance"] / ROUTE_SEGMENT_COUNT / 1000
                    segment_performances.append({
                        "ride_id": sampled["ride_id"],
                        "duration": duration,
                        "speed": distance_km / duration * 3600 if duration else None,
                    })
                fastest = min(segment_performances, key=lambda performance: performance["duration"], default=None)
                segments.append({
                    "id": f"{group['id']}-{direction}-{index + 1}",
                    "group_id": group["id"],
                    "label": group["label"],
                    "direction": direction,
                    "index": index + 1,
                    "progress_start": index * 100 // ROUTE_SEGMENT_COUNT,
                    "progress_end": (index + 1) * 100 // ROUTE_SEGMENT_COUNT,
                    "start": [round(average_start[0], 6), round(average_start[1], 6)],
                    "end": [round(average_end[0], 6), round(average_end[1], 6)],
                    "distance_km": number(average_distance / ROUTE_SEGMENT_COUNT / 1000, 2),
                    "ride_count": len(sampled_routes),
                    "total_rides": len(ride_ids),
                    "coverage_percent": number(len(sampled_routes) / len(ride_ids) * 100, 1),
                    "performance_count": len(segment_performances),
                    "average_time_seconds": number(
                        sum(performance["duration"] for performance in segment_performances) / len(segment_performances),
                        0,
                    ) if segment_performances else None,
                    "average_speed_kmh": number(
                        sum(performance["speed"] for performance in segment_performances) / len(segment_performances),
                        1,
                    ) if segment_performances else None,
                    "fastest_time_seconds": number(fastest["duration"], 0) if fastest else None,
                    "record_ride_id": fastest["ride_id"] if fastest else None,
                })
    return {"segment_count": ROUTE_SEGMENT_COUNT, "segments": segments}


def weather_records(items):
    records = []
    for item in items:
        weather_path = DATA / "weather_cache" / f"{item.get('id')}.json"
        if not weather_path.is_file():
            continue
        try:
            payload = json.loads(weather_path.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        weather = {
            field: value
            for field in ("temperature_c", "wind_kmh", "precipitation_mm", "weather_code")
            if (value := finite_number(payload.get(field))) is not None
        }
        if not weather:
            continue
        records.append({
            "id": item.get("id"),
            "date": item.get("date"),
            "speed_kmh": finite_number(item.get("average_speed_kmh")),
            "weather": weather,
        })
    return records


def average_record_value(records, field):
    values = [value for record in records if (value := finite_number(record.get(field))) is not None]
    return number(sum(values) / len(values), 1) if values else None


def average_weather_value(records, field):
    values = [
        value
        for record in records
        if (value := finite_number(record["weather"].get(field))) is not None
    ]
    return number(sum(values) / len(values), 1) if values else None


def weather_stats(records):
    return {
        "count": len(records),
        "average_speed_kmh": average_record_value(records, "speed_kmh"),
        "average_temperature_c": average_weather_value(records, "temperature_c"),
        "average_wind_kmh": average_weather_value(records, "wind_kmh"),
        "average_precipitation_mm": average_weather_value(records, "precipitation_mm"),
    }


def weather_bins(records, field, width, suffix):
    buckets = {}
    for record in records:
        value = finite_number(record["weather"].get(field))
        if value is None:
            continue
        start = floor(value / width) * width
        buckets.setdefault(start, []).append(record)
    result = []
    for start in sorted(buckets):
        end = start + width
        result.append({
            "label": f"{start:g}-{end:g}{suffix}",
            "average_speed_kmh": average_record_value(buckets[start], "speed_kmh"),
            "ride_count": len(buckets[start]),
        })
    return result


def build_weather_analysis(items, commute):
    records = weather_records(items)
    by_id = {record["id"]: record for record in records}
    dry = [record for record in records if record["weather"].get("precipitation_mm") == 0]
    wet = [record for record in records if (record["weather"].get("precipitation_mm") or 0) > 0]
    fastest_record = max(
        (record for record in records if record["speed_kmh"] is not None),
        key=lambda record: record["speed_kmh"],
        default=None,
    )
    fastest = None
    if fastest_record:
        fastest = {
            "ride_id": fastest_record["id"],
            "date": fastest_record["date"],
            "speed_kmh": fastest_record["speed_kmh"],
            "temperature_c": fastest_record["weather"].get("temperature_c"),
            "wind_kmh": fastest_record["weather"].get("wind_kmh"),
            "precipitation_mm": fastest_record["weather"].get("precipitation_mm"),
        }

    directions = []
    for group in commute["groups"]:
        direction_stats = {}
        for direction in ("outbound", "return"):
            direction_stats[direction] = weather_stats([
                by_id[ride_id]
                for ride_id in group[direction]["ride_ids"]
                if ride_id in by_id
            ])
        directions.append({
            "group_id": group["id"],
            "label": group["label"],
            "outbound": direction_stats["outbound"],
            "return": direction_stats["return"],
        })

    return {
        "total_rides": len(items),
        "available_rides": len(records),
        "temperature_bins": weather_bins(records, "temperature_c", 5, " C"),
        "wind_bins": weather_bins(records, "wind_kmh", 5, " km/h"),
        "conditions": {"dry": weather_stats(dry), "wet": weather_stats(wet)},
        "fastest": fastest,
        "directions": directions,
    }


def detect_stops(samples, session_start=None, elapsed_seconds=None):
    """Infer stationary intervals from FIT records and recording pauses.

    XOSS records are normally one second apart while moving, but automatic
    pause removes records while stopped. Unchanged cumulative distance across a
    timestamp gap is therefore a stronger signal than speed alone.
    """
    ordered = []
    for sample in samples:
        timestamp = as_utc(sample.get("timestamp"))
        if isinstance(timestamp, datetime):
            ordered.append({**sample, "timestamp": timestamp})
    ordered.sort(key=lambda sample: sample["timestamp"])
    if not ordered:
        return []

    candidates = []

    def add_candidate(start, end):
        if start and end and end > start:
            candidates.append((start, end))

    session_start = as_utc(session_start)
    first = ordered[0]
    last = ordered[-1]

    if (
        session_start
        and first["timestamp"] > session_start
        and first.get("speed") is not None
        and first["speed"] <= STOP_SPEED_MPS
    ):
        add_candidate(session_start, first["timestamp"])

    for previous, current in zip(ordered, ordered[1:]):
        gap_seconds = (current["timestamp"] - previous["timestamp"]).total_seconds()
        previous_distance = previous.get("distance_m")
        current_distance = current.get("distance_m")
        distance_delta = (
            current_distance - previous_distance
            if previous_distance is not None and current_distance is not None
            else None
        )
        if (
            gap_seconds > RECORD_INTERVAL_SECONDS
            and distance_delta is not None
            and abs(distance_delta) <= DISTANCE_TOLERANCE_M
        ):
            add_candidate(
                previous["timestamp"] + timedelta(seconds=RECORD_INTERVAL_SECONDS),
                current["timestamp"],
            )

    low_start = None
    low_end = None
    low_distance_start = None
    low_distance_end = None
    previous_timestamp = None

    def flush_low_speed_run():
        nonlocal low_start, low_end, low_distance_start, low_distance_end
        if (
            low_start
            and low_end
            and low_distance_start is not None
            and low_distance_end is not None
            and abs(low_distance_end - low_distance_start) <= MAX_STOP_DISTANCE_M
        ):
            add_candidate(low_start, low_end + timedelta(seconds=1))
        low_start = None
        low_end = None
        low_distance_start = None
        low_distance_end = None

    for sample in ordered:
        timestamp = sample["timestamp"]
        speed = sample.get("speed")
        is_contiguous = (
            previous_timestamp is not None
            and (timestamp - previous_timestamp).total_seconds() <= RECORD_INTERVAL_SECONDS + 1
        )
        if speed is not None and speed <= STOP_SPEED_MPS:
            if low_start is None or not is_contiguous:
                flush_low_speed_run()
                low_start = timestamp
                low_distance_start = sample.get("distance_m")
            low_end = timestamp
            low_distance_end = sample.get("distance_m")
        else:
            flush_low_speed_run()
        previous_timestamp = timestamp
    flush_low_speed_run()

    if session_start and elapsed_seconds is not None:
        session_end = session_start + timedelta(seconds=float(elapsed_seconds))
        if (
            session_end > last["timestamp"]
            and last.get("speed") is not None
            and last["speed"] <= STOP_SPEED_MPS
        ):
            add_candidate(last["timestamp"], session_end)

    candidates.sort(key=lambda interval: interval[0])
    merged = []
    for start, end in candidates:
        if merged and start <= merged[-1][1] + timedelta(seconds=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    stops = []
    for start, end in merged:
        duration = round((end - start).total_seconds())
        if duration >= MIN_STOP_SECONDS:
            stops.append({
                "start": timestamp_iso(start),
                "end": timestamp_iso(end),
                "duration_seconds": duration,
            })
    return stops


def valid_coordinate(latitude, longitude):
    latitude = finite_number(latitude)
    longitude = finite_number(longitude)
    return (
        latitude is not None
        and longitude is not None
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def quality_duration(seconds):
    seconds = max(0, round(seconds))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def build_data_quality(samples, point_count, session, session_start, elapsed_seconds, moving_seconds, stops):
    warnings = []

    def add_warning(code, count, message):
        if count:
            warnings.append({"code": code, "count": count, "message": message})

    invalid_coordinates = sum(
        1
        for sample in samples
        if sample.get("coordinate_present")
        and not valid_coordinate(sample.get("lat"), sample.get("lon"))
    )
    add_warning(
        "invalid_gps",
        invalid_coordinates,
        f"{invalid_coordinates} invalid GPS point{'s' if invalid_coordinates != 1 else ''}.",
    )

    timestamp_sequence = [
        sample["timestamp"]
        for sample in samples
        if isinstance(sample.get("timestamp"), datetime)
    ]
    timestamp_order_issues = sum(
        1
        for previous, current in zip(timestamp_sequence, timestamp_sequence[1:])
        if current < previous
    )
    add_warning(
        "timestamp_order",
        timestamp_order_issues,
        f"{timestamp_order_issues} timestamp order issue{'s' if timestamp_order_issues != 1 else ''} "
        "in the original record sequence.",
    )

    ordered = sorted(
        (sample for sample in samples if isinstance(sample.get("timestamp"), datetime)),
        key=lambda sample: sample["timestamp"],
    )
    stop_ranges = []
    for stop in stops:
        stop_start = as_utc(stop.get("start"))
        stop_end = as_utc(stop.get("end"))
        if isinstance(stop_start, datetime) and isinstance(stop_end, datetime) and stop_end > stop_start:
            stop_ranges.append((stop_start, stop_end))

    gps_gaps = []
    for previous, current in zip(ordered, ordered[1:]):
        gap = (current["timestamp"] - previous["timestamp"]).total_seconds()
        if gap <= GPS_GAP_SECONDS:
            continue
        if any(
            previous["timestamp"] < stop_end and current["timestamp"] > stop_start
            for stop_start, stop_end in stop_ranges
        ):
            continue
        previous_distance = finite_number(previous.get("distance_m"))
        current_distance = finite_number(current.get("distance_m"))
        distance_progressed = (
            previous_distance is not None
            and current_distance is not None
            and current_distance - previous_distance > DISTANCE_TOLERANCE_M
        )
        missing_distance_while_moving = (
            previous_distance is None
            and current_distance is None
            and max(
                finite_number(previous.get("speed")) or 0,
                finite_number(current.get("speed")) or 0,
            ) > STOP_SPEED_MPS * 4
        )
        if distance_progressed or missing_distance_while_moving:
            gps_gaps.append(gap)
    longest_gap = max(gps_gaps, default=0)
    add_warning(
        "gps_gap",
        len(gps_gaps),
        f"{len(gps_gaps)} GPS gap{'s' if len(gps_gaps) != 1 else ''} while moving "
        f"over {GPS_GAP_SECONDS} seconds (longest {quality_duration(longest_gap)}).",
    )

    speed_spikes = []
    for sample in samples:
        speed = finite_number(sample.get("speed"))
        if speed is not None and (speed < 0 or speed * 3.6 > MAX_REASONABLE_SPEED_KMH):
            speed_spikes.append(speed * 3.6)
    maximum_speed = max(speed_spikes, default=0)
    add_warning(
        "speed_spike",
        len(speed_spikes),
        f"{len(speed_spikes)} unrealistic speed spike{'s' if len(speed_spikes) != 1 else ''} "
        f"above {MAX_REASONABLE_SPEED_KMH} km/h (maximum {number(maximum_speed, 1)} km/h).",
    )

    long_stops = [
        duration
        for stop in stops
        if (duration := finite_number(stop.get("duration_seconds"))) is not None
        and duration > LONG_STOP_SECONDS
    ]
    longest_stop = max(long_stops, default=0)
    add_warning(
        "long_stop",
        len(long_stops),
        f"{len(long_stops)} unusually long stop{'s' if len(long_stops) != 1 else ''} "
        f"over {quality_duration(LONG_STOP_SECONDS)} (longest {quality_duration(longest_stop)}).",
    )

    distance_values = []
    invalid_distances = 0
    for sample in samples:
        raw_distance = sample.get("distance_m")
        if raw_distance is None:
            continue
        distance = finite_number(raw_distance)
        if distance is None or distance < 0:
            invalid_distances += 1
        else:
            distance_values.append(distance)
    distance_drops = sum(
        1
        for previous, current in zip(distance_values, distance_values[1:])
        if current < previous - DISTANCE_TOLERANCE_M
    )
    distance_messages = []
    distance_events = invalid_distances + distance_drops
    if invalid_distances:
        distance_messages.append(f"{invalid_distances} invalid readings")
    if distance_drops:
        distance_messages.append(f"{distance_drops} cumulative-distance drops")
    raw_session_distance = session.get("total_distance")
    session_distance = finite_number(session.get("total_distance"))
    if raw_session_distance is not None and (session_distance is None or session_distance < 0):
        distance_events += 1
        distance_messages.append("invalid session total")
    track_distance = (
        distance_values[-1] - distance_values[0]
        if len(distance_values) >= 2
        else None
    )
    if track_distance is not None and track_distance < -DISTANCE_TOLERANCE_M:
        distance_events += 1
        distance_messages.append(f"negative first-to-last progress of {number(track_distance, 0)} m")
    if session_distance is not None and track_distance is not None and track_distance >= 0:
        mismatch = abs(session_distance - track_distance)
        if mismatch > max(DISTANCE_MISMATCH_METERS, abs(session_distance) * DISTANCE_MISMATCH_RATIO):
            distance_events += 1
            distance_messages.append(
                f"session/track mismatch of {number(mismatch, 0)} m"
            )
    if distance_events:
        add_warning("suspicious_distance", distance_events, f"Suspicious distance data: {', '.join(distance_messages)}.")

    incomplete_reasons = []
    if not session:
        incomplete_reasons.append("missing session summary")
    else:
        if session_start is None or as_utc(session.get("start_time")) is None:
            incomplete_reasons.append("missing start time")
        if elapsed_seconds is None or elapsed_seconds <= 0:
            incomplete_reasons.append("missing elapsed time")
        if moving_seconds is None or moving_seconds < 0:
            incomplete_reasons.append("missing moving time")
        elif elapsed_seconds is not None and moving_seconds > elapsed_seconds:
            incomplete_reasons.append("moving time exceeds elapsed time")
    if point_count < 2:
        incomplete_reasons.append("fewer than two valid GPS points")
    timestamped = [sample["timestamp"] for sample in ordered]
    if not timestamped:
        incomplete_reasons.append("no timestamped records")
    elif session_start is not None and elapsed_seconds is not None and elapsed_seconds > 0:
        span = (timestamped[-1] - timestamped[0]).total_seconds()
        if span < elapsed_seconds * 0.5:
            incomplete_reasons.append("recorded span is much shorter than elapsed time")
        session_end = session_start + timedelta(seconds=elapsed_seconds)
        if (timestamped[0] - session_start).total_seconds() > 5 * 60:
            incomplete_reasons.append("recording starts late")
        if (session_end - timestamped[-1]).total_seconds() > 5 * 60:
            incomplete_reasons.append("recording ends early")
    if incomplete_reasons:
        add_warning("incomplete_recording", 1, f"Incomplete recording: {', '.join(incomplete_reasons)}.")

    return {
        "status": "warning" if warnings else "ok",
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def parse_workout(path, include_track=False):
    fit = FitFile(str(path))
    records = []
    samples = []
    point_count = 0
    first_point_time = None
    session = {}
    for message in fit.get_messages():
        if message.name == "record":
            values = {field.name: field.value for field in message if field.value is not None}
            timestamp = as_utc(values.get("timestamp"))
            speed_value = finite_number(values.get("enhanced_speed", values.get("speed")))
            speed = number(speed_value, 2)
            distance = values.get("distance")
            lat = degrees(values.get("position_lat"))
            lon = degrees(values.get("position_long"))
            samples.append({
                "timestamp": timestamp,
                "speed": speed,
                "distance_m": distance,
                "lat": lat,
                "lon": lon,
                "coordinate_present": values.get("position_lat") is not None or values.get("position_long") is not None,
            })
            if valid_coordinate(lat, lon):
                point_count += 1
                point_timestamp = timestamp_iso(timestamp)
                if first_point_time is None and point_timestamp:
                    first_point_time = point_timestamp
                if include_track:
                    records.append({
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "t": point_timestamp,
                        "speed": speed,
                        "altitude": number(
                            finite_number(values.get("enhanced_altitude", values.get("altitude"))),
                            1,
                        ),
                        "distance_m": distance,
                    })
        elif message.name == "session":
            session = {field.name: field.value for field in message if field.value is not None}

    session_start = as_utc(session.get("start_time"))
    if session_start is None and first_point_time:
        session_start = datetime.fromisoformat(first_point_time)
    start = timestamp_iso(session_start)
    elapsed = finite_number(session.get("total_elapsed_time"))
    moving = finite_number(session.get("total_moving_time"))
    stops = detect_stops(samples, session_start, elapsed)
    detected_stopped = sum(stop["duration_seconds"] for stop in stops)
    estimated_stopped = (
        max(float(elapsed) - float(moving), 0)
        if elapsed is not None and elapsed >= 0 and moving is not None and moving >= 0
        else detected_stopped or None
    )
    moving_percent = (
        float(moving) / float(elapsed) * 100
        if moving is not None and moving >= 0 and elapsed is not None and elapsed > 0
        else None
    )
    quality = build_data_quality(samples, point_count, session, session_start, elapsed, moving, stops)
    total_distance = finite_number(session.get("total_distance"))
    average_speed = finite_number(session.get("enhanced_avg_speed", session.get("avg_speed")))
    max_speed = finite_number(session.get("enhanced_max_speed", session.get("max_speed")))
    ascent = finite_number(session.get("total_ascent"))
    descent = finite_number(session.get("total_descent"))
    temperature = finite_number(session.get("avg_temperature"))
    result = {
        "id": path.stem,
        "file": path.name,
        "date": start,
        "distance_km": number(total_distance / 1000 if total_distance is not None else None, 2),
        "moving_seconds": number(moving, 0),
        "elapsed_seconds": number(elapsed, 0),
        "average_speed_kmh": number(average_speed * 3.6 if average_speed is not None else None, 1),
        "max_speed_kmh": number(max_speed * 3.6 if max_speed is not None else None, 1),
        "ascent_m": number(ascent, 0),
        "descent_m": number(descent, 0),
        "climbing_rate_m_per_hour": vertical_rate(ascent, moving),
        "descent_rate_m_per_hour": vertical_rate(descent, moving),
        "calories": session.get("total_calories"),
        "temperature_c": number(temperature, 0),
        "points": point_count,
        "estimated_stopped_seconds": number(estimated_stopped, 0),
        "moving_percent": number(moving_percent, 1),
        "stop_count": len(stops),
        "longest_stop_seconds": max((stop["duration_seconds"] for stop in stops), default=0),
        "data_quality": quality,
    }
    if include_track:
        result["track"] = records
        result["stops"] = stops
    return result


def cached_weather_payload(workout_id):
    weather_path = DATA / "weather_cache" / f"{workout_id}.json"
    if not weather_path.is_file():
        return None
    try:
        payload = json.loads(weather_path.read_text())
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def cached_weather_summary(workout_id):
    payload = cached_weather_payload(workout_id)
    if payload is None:
        return None
    weather = {
        field: finite_number(payload.get(field))
        for field in ("temperature_c", "feels_like_c", "wind_kmh", "precipitation_mm")
    }
    weather = {field: value for field, value in weather.items() if value is not None}
    return weather or None


def workouts():
    global _workouts_cache, _workouts_signature
    paths = sorted(DATA.glob("*.fit"), reverse=True)
    signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
    if _workouts_cache is not None and signature == _workouts_signature:
        return _workouts_cache
    cache_path = DATA / "workouts_cache.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text())
            if cached.get("version") == WORKOUTS_CACHE_VERSION and tuple(tuple(item) for item in cached["signature"]) == signature:
                _workouts_signature = signature
                _workouts_cache = cached["workouts"]
                return _workouts_cache
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            pass
    result = []
    for path in paths:
        try:
            result.append(parse_workout(path))
        except Exception as error:
            app.logger.warning("Skipping %s: %s", path.name, error)
    _workouts_signature = signature
    _workouts_cache = result
    cache_path.write_text(json.dumps({"version": WORKOUTS_CACHE_VERSION, "signature": signature, "workouts": result}))
    return result


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/rides/<workout_id>")
def ride_page(workout_id):
    return render_template("index.html")


@app.get("/<path:frontend_path>")
def frontend_route(frontend_path):
    if frontend_path in {"api", "static"} or frontend_path.startswith(("api/", "static/")):
        return jsonify({"error": "Not found"}), 404
    if "." in frontend_path.rsplit("/", 1)[-1]:
        return jsonify({"error": "Not found"}), 404
    return render_template("index.html")


@app.get("/api/workouts")
def workout_list():
    items = workouts()
    enriched = [{**item, "weather": cached_weather_summary(item["id"])} for item in items]
    data_updated = max(
        (path.stat().st_mtime for path in DATA.glob("*.fit")),
        default=None,
    )
    return jsonify({
        "workouts": enriched,
        "count": len(enriched),
        "updated": datetime.now(timezone.utc).isoformat(),
        "data_updated": datetime.fromtimestamp(data_updated, timezone.utc).isoformat() if data_updated is not None else None,
    })


@app.get("/api/workouts/<workout_id>/download")
def workout_download(workout_id):
    path = (DATA / f"{workout_id}.fit").resolve()
    data_root = DATA.resolve()
    if path.parent != data_root or not path.is_file():
        return jsonify({"error": "Workout not found"}), 404
    return send_file(
        path,
        as_attachment=True,
        download_name=path.name,
        mimetype="application/octet-stream",
    )


@app.get("/api/workouts/<workout_id>")
def workout_detail(workout_id):
    path = (DATA / f"{workout_id}.fit").resolve()
    if not path.is_file() or path.parent != DATA.resolve():
        return jsonify({"error": "Workout not found"}), 404
    weather_path = DATA / "weather_cache" / f"{workout_id}.json"
    path_stat = path.stat()
    weather_stat = weather_path.stat() if weather_path.is_file() else None
    signature = (
        path_stat.st_size,
        path_stat.st_mtime_ns,
        weather_stat.st_size if weather_stat else None,
        weather_stat.st_mtime_ns if weather_stat else None,
    )
    cached = _detail_cache.get(workout_id)
    if cached and cached[0] == signature:
        return jsonify(cached[1])
    result = parse_workout(path, include_track=True)
    result["weather"] = cached_weather_payload(workout_id)
    _detail_cache[workout_id] = (signature, result)
    return jsonify(result)


def route_overlay_data():
    with _routes_lock:
        return _route_overlay_data()


def _route_overlay_data():
    global _routes_cache, _routes_signature, _tracks_cache, _tracks_signature
    paths = sorted(DATA.glob("*.fit"), reverse=True)
    fit_signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
    weather_paths = sorted((DATA / "weather_cache").glob("*.json")) if (DATA / "weather_cache").is_dir() else []
    signature = fit_signature + tuple((f"weather/{path.name}", path.stat().st_size, path.stat().st_mtime_ns) for path in weather_paths)
    if _routes_cache is not None and signature == _routes_signature:
        return _routes_cache
    cache_path = DATA / "routes_cache.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text())
            if cached.get("version") == ROUTES_CACHE_VERSION and tuple(tuple(item) for item in cached["signature"]) == signature:
                _routes_signature = signature
                _routes_cache = cached["routes"]
                if _tracks_signature != fit_signature:
                    _tracks_cache = None
                return _routes_cache
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            pass
    routes = []
    tracks = {}
    for path in paths:
        try:
            workout = parse_workout(path, include_track=True)
            points = workout["track"]
            tracks[path.stem] = points
            stride = max(1, (len(points) + 299) // 300)
            sampled = points[::stride]
            if points and sampled[-1] is not points[-1]:
                sampled.append(points[-1])
            routes.append({
                "id": path.stem,
                "date": workout.get("date"),
                "points": [[point["lat"], point["lon"]] for point in sampled],
                "samples": [{
                    "lat": point["lat"],
                    "lon": point["lon"],
                    "speed_kmh": number(
                        finite_number(point.get("speed")) * 3.6
                        if finite_number(point.get("speed")) is not None else None,
                        1,
                    ),
                    "elevation_m": point.get("altitude"),
                } for point in sampled],
                "weather": cached_weather_summary(path.stem),
            })
        except Exception as error:
            app.logger.warning("Skipping route %s: %s", path.name, error)
    _routes_signature = signature
    _routes_cache = routes
    _tracks_signature = fit_signature
    _tracks_cache = tracks
    cache_path.write_text(json.dumps({"version": ROUTES_CACHE_VERSION, "signature": signature, "routes": routes}))
    return routes


def route_track_data():
    with _routes_lock:
        return _route_track_data()


def _route_track_data():
    global _tracks_cache, _tracks_signature
    paths = sorted(DATA.glob("*.fit"), reverse=True)
    signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
    if _tracks_cache is not None and signature == _tracks_signature:
        return _tracks_cache
    tracks = {}
    for path in paths:
        try:
            tracks[path.stem] = parse_workout(path, include_track=True)["track"]
        except Exception as error:
            app.logger.warning("Skipping track %s: %s", path.name, error)
    _tracks_signature = signature
    _tracks_cache = tracks
    return tracks


@app.get("/api/routes")
def route_overlay():
    return jsonify({"routes": route_overlay_data()})


def commute_analysis_data():
    global _commutes_cache, _commutes_signature
    timezone_name, _ = analytics_timezone()
    paths = sorted(DATA.glob("*.fit"), reverse=True)
    signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
    if LOCATION_NAMES_PATH.is_file():
        signature += ((LOCATION_NAMES_PATH.name, LOCATION_NAMES_PATH.stat().st_size, LOCATION_NAMES_PATH.stat().st_mtime_ns),)
    signature += (("timezone", timezone_name),)
    if _commutes_cache is not None and signature == _commutes_signature:
        return _commutes_cache
    cache_path = DATA / "commutes_cache.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text())
            if cached.get("version") == COMMUTES_CACHE_VERSION and tuple(tuple(item) for item in cached["signature"]) == signature:
                _commutes_signature = signature
                _commutes_cache = cached["commutes"]
                return _commutes_cache
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            pass
    _commutes_cache = build_commute_analysis(workouts(), route_overlay_data())
    _commutes_signature = signature
    cache_path.write_text(json.dumps({"version": COMMUTES_CACHE_VERSION, "signature": signature, "commutes": _commutes_cache}))
    return _commutes_cache


@app.get("/api/commutes")
def commute_analysis():
    return jsonify(commute_analysis_data())


def segment_analysis_data():
    global _segments_cache, _segments_signature
    paths = sorted(DATA.glob("*.fit"), reverse=True)
    signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
    if LOCATION_NAMES_PATH.is_file():
        signature += ((LOCATION_NAMES_PATH.name, LOCATION_NAMES_PATH.stat().st_size, LOCATION_NAMES_PATH.stat().st_mtime_ns),)
    if _segments_cache is not None and signature == _segments_signature:
        return _segments_cache
    cache_path = DATA / "segments_cache.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text())
            if cached.get("version") == SEGMENTS_CACHE_VERSION and tuple(tuple(item) for item in cached["signature"]) == signature:
                _segments_signature = signature
                _segments_cache = cached["segments"]
                return _segments_cache
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            pass
    commute = commute_analysis_data()
    _segments_cache = build_route_segments(commute["groups"], route_track_data())
    _segments_signature = signature
    cache_path.write_text(json.dumps({"version": SEGMENTS_CACHE_VERSION, "signature": signature, "segments": _segments_cache}))
    return _segments_cache


@app.get("/api/segments")
def route_segments():
    return jsonify(segment_analysis_data())


def weather_analysis_data():
    global _weather_analysis_cache, _weather_analysis_signature
    timezone_name, _ = analytics_timezone()
    paths = sorted(DATA.glob("*.fit"), reverse=True)
    signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
    weather_paths = sorted((DATA / "weather_cache").glob("*.json")) if (DATA / "weather_cache").is_dir() else []
    signature += tuple((f"weather/{path.name}", path.stat().st_size, path.stat().st_mtime_ns) for path in weather_paths)
    if LOCATION_NAMES_PATH.is_file():
        signature += ((LOCATION_NAMES_PATH.name, LOCATION_NAMES_PATH.stat().st_size, LOCATION_NAMES_PATH.stat().st_mtime_ns),)
    signature += (("timezone", timezone_name),)
    if _weather_analysis_cache is not None and signature == _weather_analysis_signature:
        return _weather_analysis_cache
    cache_path = DATA / "weather_analysis_cache.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text())
            if cached.get("version") == WEATHER_ANALYSIS_CACHE_VERSION and tuple(tuple(item) for item in cached["signature"]) == signature:
                _weather_analysis_signature = signature
                _weather_analysis_cache = cached["weather"]
                return _weather_analysis_cache
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            pass
    items = workouts()
    _weather_analysis_cache = build_weather_analysis(items, commute_analysis_data())
    _weather_analysis_signature = signature
    cache_path.write_text(json.dumps({"version": WEATHER_ANALYSIS_CACHE_VERSION, "signature": signature, "weather": _weather_analysis_cache}))
    return _weather_analysis_cache


@app.get("/api/weather")
def weather_analysis():
    return jsonify(weather_analysis_data())


@app.put("/api/commutes/locations/<location_id>")
def rename_commute_location(location_id):
    global _commutes_cache, _commutes_signature, _segments_cache, _segments_signature, _weather_analysis_cache, _weather_analysis_signature
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be an object"}), 400
    name = payload.get("name")
    if not isinstance(name, str):
        return jsonify({"error": "Location name must be a string"}), 400
    name = name.strip()
    if len(name) > 60:
        return jsonify({"error": "Location name must be 60 characters or fewer"}), 400
    location = update_location_name(location_id, name)
    if location is None:
        return jsonify({"error": "Location not found"}), 404
    _commutes_cache = None
    _commutes_signature = None
    _segments_cache = None
    _segments_signature = None
    _weather_analysis_cache = None
    _weather_analysis_signature = None
    cache_path = DATA / "commutes_cache.json"
    try:
        cache_path.unlink()
    except FileNotFoundError:
        pass
    try:
        (DATA / "segments_cache.json").unlink()
    except FileNotFoundError:
        pass
    try:
        (DATA / "weather_analysis_cache.json").unlink()
    except FileNotFoundError:
        pass
    return jsonify(commute_analysis_data())


@app.get("/api/insights")
def workout_insights():
    global _insights_cache, _insights_signature
    timezone_name, _ = analytics_timezone()
    signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in sorted(DATA.glob("*.fit")))
    signature += (("timezone", timezone_name),)
    if _insights_cache is not None and signature == _insights_signature:
        return jsonify(_insights_cache)
    cache_path = DATA / "insights_cache.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text())
            if cached.get("version") == INSIGHTS_CACHE_VERSION and tuple(tuple(item) for item in cached["signature"]) == signature:
                _insights_signature = signature
                _insights_cache = cached["insights"]
                return jsonify(_insights_cache)
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            pass
    _insights_cache = build_workout_insights(workouts())
    _insights_signature = signature
    cache_path.write_text(json.dumps({"version": INSIGHTS_CACHE_VERSION, "signature": signature, "insights": _insights_cache}))
    return jsonify(_insights_cache)


def speed_distribution(buckets):
    if not buckets:
        return []
    width = SPEED_DISTRIBUTION_BIN_KMH
    result = []
    for start in range(0, max(buckets) + width, width):
        bucket = buckets.get(start, {"point_count": 0, "ride_ids": set()})
        result.append({
            "label": f"{start:g}-{start + width:g}",
            "min_kmh": start,
            "max_kmh": start + width,
            "point_count": bucket["point_count"],
            "ride_count": len(bucket["ride_ids"]),
        })
    return result


def fastest_section_payload(target_distance, section):
    if section is None:
        return {
            "distance_km": target_distance // 1000,
            "time_seconds": None,
            "speed_kmh": None,
            "start_km": None,
            "end_km": None,
            "ride_id": None,
            "date": None,
        }
    return {
        "distance_km": target_distance // 1000,
        "time_seconds": number(section["time_seconds"], 1),
        "speed_kmh": number(section["speed_kmh"], 1),
        "start_km": number(section["start_km"], 2),
        "end_km": number(section["end_km"], 2),
        "ride_id": section["ride_id"],
        "date": section["date"],
    }


def period_summaries(items, timezone_value, period):
    buckets = {}
    for item in items:
        date = item_datetime(item)
        if date is None:
            continue
        local_date = date.astimezone(timezone_value)
        key = local_date.strftime("%Y-%m" if period == "month" else "%Y")
        bucket = buckets.setdefault(key, {
            "period": key,
            "ride_count": 0,
            "distance_km": 0.0,
            "distance_count": 0,
            "moving_seconds": 0.0,
            "moving_count": 0,
            "speeds": [],
        })
        bucket["ride_count"] += 1
        distance = finite_number(item.get("distance_km"))
        if distance is not None:
            bucket["distance_km"] += distance
            bucket["distance_count"] += 1
        moving = finite_number(item.get("moving_seconds"))
        if moving is not None and moving >= 0:
            bucket["moving_seconds"] += moving
            bucket["moving_count"] += 1
        speed = finite_number(item.get("average_speed_kmh"))
        if speed is not None and speed >= 0:
            bucket["speeds"].append(speed)

    result = []
    for key, bucket in sorted(buckets.items()):
        result.append({
            "period": key,
            "label": (
                datetime.strptime(key, "%Y-%m").strftime("%b %Y")
                if period == "month" else key
            ),
            "ride_count": bucket["ride_count"],
            "distance_km": number(bucket["distance_km"], 1) if bucket["distance_count"] else None,
            "moving_seconds": number(bucket["moving_seconds"], 0) if bucket["moving_count"] else None,
            "average_speed_kmh": number(sum(bucket["speeds"]) / len(bucket["speeds"]), 1) if bucket["speeds"] else None,
        })
    return result


def build_workout_insights(items):
    timezone_name, timezone_value = analytics_timezone()
    bins = [[] for _ in range(10)]
    speed_buckets = {}
    fastest_sections = {target: None for target in FASTEST_SECTION_DISTANCES_M}
    weekdays = [0] * 7
    departure_hours = [0] * 24
    calendar = {}
    for item in items:
        date = item_datetime(item)
        if date is not None:
            local_date = date.astimezone(timezone_value)
            weekdays[local_date.weekday()] += 1
            departure_hours[local_date.hour] += 1
            day = local_date.date().isoformat()
            entry = calendar.setdefault(day, {"date": day, "ride_count": 0, "distance_km": 0.0})
            entry["ride_count"] += 1
            distance = finite_number(item.get("distance_km"))
            if distance is not None:
                entry["distance_km"] += distance
        try:
            track = parse_workout(DATA / item["file"], include_track=True)["track"]
            progress, total_distance = track_progress(track)
            for target_distance in FASTEST_SECTION_DISTANCES_M:
                section = fastest_section_from_progress(progress, total_distance, target_distance)
                if section is None:
                    continue
                current = fastest_sections[target_distance]
                section_key = (str(item["id"]), section["start_km"])
                current_key = (str(current["ride_id"]), current["start_km"]) if current else None
                if current is None or section["time_seconds"] < current["time_seconds"] or (
                    section["time_seconds"] == current["time_seconds"] and section_key < current_key
                ):
                    fastest_sections[target_distance] = {
                        **section,
                        "ride_id": item["id"],
                        "date": item.get("date"),
                    }
            distances = [point["distance_m"] for point in track if point["distance_m"] is not None]
            total = max(distances) if distances else 0
            for point in track:
                speed = finite_number(point.get("speed"))
                if speed is not None:
                    speed_kmh = speed * 3.6
                    if 0 <= speed_kmh <= MAX_REASONABLE_SPEED_KMH:
                        start = floor(speed_kmh / SPEED_DISTRIBUTION_BIN_KMH) * SPEED_DISTRIBUTION_BIN_KMH
                        bucket = speed_buckets.setdefault(start, {"point_count": 0, "ride_ids": set()})
                        bucket["point_count"] += 1
                        bucket["ride_ids"].add(item["id"])
                if point["speed"] is not None and total:
                    index = min(9, int((point["distance_m"] or 0) / total * 10))
                    bins[index].append(point["speed"] * 3.6)
        except Exception:
            continue
    speed_items = [item for item in items if finite_number(item.get("average_speed_kmh")) is not None]
    distance_items = [item for item in items if finite_number(item.get("distance_km")) is not None]
    return {
        "timezone": timezone_name,
        "segments": [number(sum(values) / len(values), 1) if values else None for values in bins],
        "segment_rides": [len(values) for values in bins],
        "weekday_counts": weekdays,
        "departure_hour_counts": departure_hours,
        "calendar": [
            {**entry, "distance_km": number(entry["distance_km"], 2)}
            for _, entry in sorted(calendar.items())
        ],
        "monthly_summary": period_summaries(items, timezone_value, "month"),
        "yearly_summary": period_summaries(items, timezone_value, "year"),
        "fastest": max(speed_items, key=lambda item: finite_number(item["average_speed_kmh"]), default=None),
        "longest": max(distance_items, key=lambda item: finite_number(item["distance_km"]), default=None),
        "fastest_sections": [fastest_section_payload(target, fastest_sections[target]) for target in FASTEST_SECTION_DISTANCES_M],
        "speed_distribution": speed_distribution(speed_buckets),
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
