from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from flask import Flask, jsonify, render_template
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
_detail_cache = {}
WORKOUTS_CACHE_VERSION = 2
STOP_SPEED_MPS = 0.5
MIN_STOP_SECONDS = 5
DISTANCE_TOLERANCE_M = 1.0
MAX_STOP_DISTANCE_M = 5.0
RECORD_INTERVAL_SECONDS = 1


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


@app.get("/api/routes")
def route_overlay():
    global _routes_cache, _routes_signature
    paths = sorted(DATA.glob("*.fit"), reverse=True)
    signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in paths)
    if _routes_cache is not None and signature == _routes_signature:
        return jsonify({"routes": _routes_cache})
    cache_path = DATA / "routes_cache.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text())
            if tuple(tuple(item) for item in cached["signature"]) == signature:
                _routes_signature = signature
                _routes_cache = cached["routes"]
                return jsonify({"routes": _routes_cache})
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            pass
    routes = []
    for path in paths:
        try:
            points = parse_workout(path, include_track=True)["track"]
            stride = max(1, len(points) // 300)
            routes.append({"id": path.stem, "points": [[point["lat"], point["lon"]] for point in points[::stride]]})
        except Exception as error:
            app.logger.warning("Skipping route %s: %s", path.name, error)
    _routes_signature = signature
    _routes_cache = routes
    cache_path.write_text(json.dumps({"signature": signature, "routes": routes}))
    return jsonify({"routes": routes})


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
