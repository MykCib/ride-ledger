from datetime import datetime, timezone
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


def degrees(value):
    return value * 180.0 / 2**31 if value is not None else None


def number(value, digits=1):
    return round(float(value), digits) if value is not None else None


def parse_workout(path, include_track=False):
    fit = FitFile(str(path))
    records = []
    point_count = 0
    first_point_time = None
    session = {}
    for message in fit.get_messages():
        if message.name == "record":
            values = {field.name: field.value for field in message if field.value is not None}
            lat = degrees(values.get("position_lat"))
            lon = degrees(values.get("position_long"))
            if lat is not None and lon is not None:
                point_count += 1
                timestamp = values.get("timestamp")
                timestamp = timestamp.replace(tzinfo=timezone.utc).isoformat() if timestamp else None
                if first_point_time is None:
                    first_point_time = timestamp
                if include_track:
                    records.append({
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "t": timestamp,
                        "speed": number(values.get("enhanced_speed", values.get("speed")), 2),
                        "altitude": number(values.get("enhanced_altitude", values.get("altitude")), 1),
                        "distance_m": values.get("distance"),
                    })
        elif message.name == "session":
            session = {field.name: field.value for field in message if field.value is not None}

    start = session.get("start_time") or first_point_time
    if isinstance(start, datetime):
        start = start.replace(tzinfo=timezone.utc).isoformat()
    elapsed = session.get("total_elapsed_time")
    moving = session.get("total_moving_time")
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
    }
    if include_track:
        result["track"] = records
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
            if tuple(tuple(item) for item in cached["signature"]) == signature:
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
    cache_path.write_text(json.dumps({"signature": signature, "workouts": result}))
    return result


@app.get("/")
def index():
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
