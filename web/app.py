from datetime import datetime, timedelta, timezone
import json
from math import atan2, cos, isfinite, radians, sin, sqrt
import os
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, render_template, request
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
_detail_cache = {}
_routes_lock = Lock()
WORKOUTS_CACHE_VERSION = 2
COMMUTES_CACHE_VERSION = 4
SEGMENTS_CACHE_VERSION = 2
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


def degrees(value):
    return value * 180.0 / 2**31 if value is not None else None


def number(value, digits=1):
    return round(float(value), digits) if value is not None else None


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
    value = item.get("elapsed_seconds")
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) and value >= 0 else None


def numeric_values(items, field):
    values = []
    for item in items:
        value = item.get(field)
        if isinstance(value, bool):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if isfinite(value):
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
        {"point": record["point"], "distance": distance, "timestamp": record["timestamp"]}
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
            speed = number(values.get("enhanced_speed", values.get("speed")), 2)
            distance = values.get("distance")
            if timestamp is not None:
                samples.append({"timestamp": timestamp, "speed": speed, "distance_m": distance})
            lat = degrees(values.get("position_lat"))
            lon = degrees(values.get("position_long"))
            if lat is not None and lon is not None:
                point_count += 1
                timestamp = timestamp_iso(timestamp)
                if first_point_time is None:
                    first_point_time = timestamp
                if include_track:
                    records.append({
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "t": timestamp,
                        "speed": speed,
                        "altitude": number(values.get("enhanced_altitude", values.get("altitude")), 1),
                        "distance_m": distance,
                    })
        elif message.name == "session":
            session = {field.name: field.value for field in message if field.value is not None}

    session_start = as_utc(session.get("start_time"))
    if session_start is None and first_point_time:
        session_start = datetime.fromisoformat(first_point_time)
    start = timestamp_iso(session_start)
    elapsed = session.get("total_elapsed_time")
    moving = session.get("total_moving_time")
    stops = detect_stops(samples, session_start, elapsed)
    detected_stopped = sum(stop["duration_seconds"] for stop in stops)
    estimated_stopped = (
        max(float(elapsed) - float(moving), 0)
        if elapsed is not None and moving is not None
        else detected_stopped or None
    )
    moving_percent = float(moving) / float(elapsed) * 100 if moving is not None and elapsed else None
    result = {
        "id": path.stem,
        "file": path.name,
        "date": start,
        "distance_km": number(session.get("total_distance") / 1000 if session.get("total_distance") is not None else None, 2),
        "moving_seconds": number(moving, 0),
        "elapsed_seconds": number(elapsed, 0),
        "average_speed_kmh": number(session.get("enhanced_avg_speed", session.get("avg_speed")) * 3.6 if session.get("enhanced_avg_speed", session.get("avg_speed")) is not None else None, 1),
        "max_speed_kmh": number(session.get("enhanced_max_speed", session.get("max_speed")) * 3.6 if session.get("enhanced_max_speed", session.get("max_speed")) is not None else None, 1),
        "ascent_m": number(session.get("total_ascent"), 0),
        "descent_m": number(session.get("total_descent"), 0),
        "calories": session.get("total_calories"),
        "temperature_c": number(session.get("avg_temperature"), 0),
        "points": point_count,
        "estimated_stopped_seconds": number(estimated_stopped, 0),
        "moving_percent": number(moving_percent, 1),
        "stop_count": len(stops),
        "longest_stop_seconds": max((stop["duration_seconds"] for stop in stops), default=0),
    }
    if include_track:
        result["track"] = records
        result["stops"] = stops
    return result


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
    return jsonify({"workouts": items, "count": len(items), "updated": datetime.now(timezone.utc).isoformat()})


@app.get("/api/workouts/<workout_id>")
def workout_detail(workout_id):
    path = DATA / f"{workout_id}.fit"
    if not path.is_file() or path.parent != DATA:
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
    result["weather"] = json.loads(weather_path.read_text()) if weather_path.is_file() else None
    _detail_cache[workout_id] = (signature, result)
    return jsonify(result)


def route_overlay_data():
    with _routes_lock:
        return _route_overlay_data()


def _route_overlay_data():
    global _routes_cache, _routes_signature, _tracks_cache, _tracks_signature
    paths = sorted(DATA.glob("*.fit"), reverse=True)
    signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
    if _routes_cache is not None and signature == _routes_signature:
        return _routes_cache
    cache_path = DATA / "routes_cache.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text())
            if tuple(tuple(item) for item in cached["signature"]) == signature:
                _routes_signature = signature
                _routes_cache = cached["routes"]
                if _tracks_signature != signature:
                    _tracks_cache = None
                return _routes_cache
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            pass
    routes = []
    tracks = {}
    for path in paths:
        try:
            points = parse_workout(path, include_track=True)["track"]
            tracks[path.stem] = points
            stride = max(1, len(points) // 300)
            routes.append({"id": path.stem, "points": [[point["lat"], point["lon"]] for point in points[::stride]]})
        except Exception as error:
            app.logger.warning("Skipping route %s: %s", path.name, error)
    _routes_signature = signature
    _routes_cache = routes
    _tracks_signature = signature
    _tracks_cache = tracks
    cache_path.write_text(json.dumps({"signature": signature, "routes": routes}))
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


@app.put("/api/commutes/locations/<location_id>")
def rename_commute_location(location_id):
    global _commutes_cache, _commutes_signature, _segments_cache, _segments_signature
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
    cache_path = DATA / "commutes_cache.json"
    try:
        cache_path.unlink()
    except FileNotFoundError:
        pass
    try:
        (DATA / "segments_cache.json").unlink()
    except FileNotFoundError:
        pass
    return jsonify(commute_analysis_data())


@app.get("/api/insights")
def workout_insights():
    global _insights_cache, _insights_signature
    signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in sorted(DATA.glob("*.fit")))
    if _insights_cache is not None and signature == _insights_signature:
        return jsonify(_insights_cache)
    cache_path = DATA / "insights_cache.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text())
            if tuple(tuple(item) for item in cached["signature"]) == signature:
                _insights_signature = signature
                _insights_cache = cached["insights"]
                return jsonify(_insights_cache)
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            pass
    items = workouts()
    bins = [[] for _ in range(10)]
    weekdays = [0] * 7
    for item in items:
        if item["date"]:
            weekday = datetime.fromisoformat(item["date"]).weekday()
            weekdays[weekday] += 1
        try:
            track = parse_workout(DATA / item["file"], include_track=True)["track"]
            distances = [point["distance_m"] for point in track if point["distance_m"] is not None]
            total = max(distances) if distances else 0
            for point in track:
                if point["speed"] is not None and total:
                    index = min(9, int((point["distance_m"] or 0) / total * 10))
                    bins[index].append(point["speed"] * 3.6)
        except Exception:
            continue
    _insights_signature = signature
    _insights_cache = {
        "segments": [number(sum(values) / len(values), 1) if values else None for values in bins],
        "segment_rides": [len(values) for values in bins],
        "weekday_counts": weekdays,
        "fastest": max(items, key=lambda x: x["average_speed_kmh"] or 0, default=None),
        "longest": max(items, key=lambda x: x["distance_km"] or 0, default=None),
    }
    cache_path.write_text(json.dumps({"signature": signature, "insights": _insights_cache}))
    return jsonify(_insights_cache)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
