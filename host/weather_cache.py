#!/usr/bin/env python3
"""Cache historical weather summaries for downloaded FIT workouts."""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fitparse import FitFile

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "weather_cache"


def degrees(value):
    return value * 180 / 2**31 if value is not None else None


def ride_points(path):
    points = []
    for message in FitFile(str(path)).get_messages("record"):
        values = {field.name: field.value for field in message if field.value is not None}
        lat = degrees(values.get("position_lat"))
        lon = degrees(values.get("position_long"))
        timestamp = values.get("timestamp")
        if lat is not None and lon is not None and timestamp:
            points.append((lat, lon, timestamp.replace(tzinfo=timezone.utc)))
    if not points:
        return []
    return [points[0], points[len(points) // 2], points[-1]]


def fetch(point):
    lat, lon, timestamp = point
    date = timestamp.date().isoformat()
    query = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "start_date": date, "end_date": date,
        "hourly": "temperature_2m,apparent_temperature,precipitation,wind_speed_10m,weather_code",
        "timezone": "UTC",
    })
    with urllib.request.urlopen(f"https://archive-api.open-meteo.com/v1/archive?{query}", timeout=20) as response:
        data = json.load(response)
    hour = timestamp.replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
    times = data.get("hourly", {}).get("time", [])
    if not times:
        return None
    index = min(range(len(times)), key=lambda i: abs(datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc) - timestamp))
    hourly = data["hourly"]
    return {"temperature_c": hourly["temperature_2m"][index], "feels_like_c": hourly["apparent_temperature"][index], "precipitation_mm": hourly["precipitation"][index], "wind_kmh": hourly["wind_speed_10m"][index], "weather_code": hourly["weather_code"][index]}


def enrich(path):
    output = CACHE / f"{path.stem}.json"
    if output.exists():
        return False
    points = ride_points(path)
    if not points:
        return False
    samples = [sample for point in points if (sample := fetch(point))]
    if not samples:
        return False
    result = {key: round(sum(sample[key] for sample in samples) / len(samples), 1) for key in samples[0]}
    result["samples"] = len(samples)
    result["source"] = "Open-Meteo historical archive"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Weather cached: {path.name}")
    return True


if __name__ == "__main__":
    CACHE.mkdir(exist_ok=True)
    files = [DATA / name for name in sys.argv[1:]] if len(sys.argv) > 1 else sorted(DATA.glob("*.fit"))
    for path in files:
        try:
            enrich(path)
        except Exception as error:
            print(f"Weather failed for {path.name}: {error}", file=sys.stderr)
