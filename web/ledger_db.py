"""Read-only SQLite access for Flask request handlers.

The indexer (host/indexer.py) is the only writer. These helpers serve the
same JSON shapes the legacy FIT-parsing path produced, but from
``data/ledger.db`` with a single cheap DB-file stat for cache keys.
"""

import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def resolve_db_path(explicit=None):
    if explicit:
        return Path(explicit)
    env = os.environ.get("LEDGER_DB", "").strip()
    if env:
        path = Path(env)
        return path if path.is_absolute() else ROOT / path
    return DATA / "ledger.db"


def db_path_for(data_dir=None):
    if data_dir is not None and Path(data_dir).resolve() != DATA.resolve():
        return Path(data_dir) / "ledger.db"
    return resolve_db_path()


def _connect(db_path):
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def is_ready(db_path=None):
    db_path = resolve_db_path(db_path) if db_path is None or isinstance(db_path, str) else db_path
    db_path = Path(db_path)
    if not db_path.is_file():
        return False
    try:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
            if not row or row["value"] != "1":
                return False
            conn.execute("SELECT id FROM rides LIMIT 1").fetchone()
            return True
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def db_mtime_ns(db_path):
    try:
        return Path(db_path).stat().st_mtime_ns
    except OSError:
        return 0


def _row_to_workout(row, weather_by_id=None):
    data = {
        "id": row["id"],
        "file": row["file"],
        "date": row["date"],
        "distance_km": row["distance_km"],
        "moving_seconds": row["moving_seconds"],
        "elapsed_seconds": row["elapsed_seconds"],
        "average_speed_kmh": row["average_speed_kmh"],
        "max_speed_kmh": row["max_speed_kmh"],
        "ascent_m": row["ascent_m"],
        "descent_m": row["descent_m"],
        "climbing_rate_m_per_hour": None,
        "descent_rate_m_per_hour": None,
        "calories": row["calories"],
        "temperature_c": row["temperature_c"],
        "points": row["points"],
        "estimated_stopped_seconds": row["estimated_stopped_seconds"],
        "moving_percent": row["moving_percent"],
        "stop_count": row["stop_count"],
        "longest_stop_seconds": row["longest_stop_seconds"],
        "data_quality": {},
    }
    try:
        data["data_quality"] = json.loads(row["quality_json"] or "{}")
    except (ValueError, TypeError):
        data["data_quality"] = {}
    # Recompute climbing rates the same way parse_workout does, since they
    # are derived from ascent/moving rather than stored.
    try:
        from web.app import vertical_rate
    except ImportError:  # pragma: no cover - fallback for tests without app
        vertical_rate = None
    if vertical_rate is not None:
        data["climbing_rate_m_per_hour"] = vertical_rate(
            row["ascent_m"], row["moving_seconds"]
        )
        data["descent_rate_m_per_hour"] = vertical_rate(
            row["descent_m"], row["moving_seconds"]
        )
    if weather_by_id and row["id"] in weather_by_id:
        data["_weather_payload"] = weather_by_id[row["id"]]
    return data


def load_workouts(db_path):
    """Return (items, weather_payloads, tracks_meta). Items match legacy shape minus weather."""
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM rides ORDER BY file DESC").fetchall()
        weather_rows = conn.execute("SELECT ride_id, payload_json FROM ride_weather").fetchall()
        meta = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM meta")
        }
    finally:
        conn.close()
    weather_by_id = {}
    for row in weather_rows:
        try:
            weather_by_id[row["ride_id"]] = json.loads(row["payload_json"])
        except (ValueError, TypeError):
            continue
    items = [_row_to_workout(row, weather_by_id) for row in rows]
    return items, weather_by_id, meta


def load_tracks(db_path):
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT ride_id, track_json, stops_json FROM ride_tracks").fetchall()
    finally:
        conn.close()
    tracks = {}
    stops = {}
    for row in rows:
        try:
            tracks[row["ride_id"]] = json.loads(row["track_json"] or "[]")
        except (ValueError, TypeError):
            tracks[row["ride_id"]] = []
        try:
            stops[row["ride_id"]] = json.loads(row["stops_json"] or "[]")
        except (ValueError, TypeError):
            stops[row["ride_id"]] = []
    return tracks, stops


def load_detail(db_path, workout_id):
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM rides WHERE id=?", (workout_id,)).fetchone()
        if not row:
            return None
        track_row = conn.execute(
            "SELECT track_json, stops_json FROM ride_tracks WHERE ride_id=?",
            (workout_id,),
        ).fetchone()
        weather_row = conn.execute(
            "SELECT payload_json FROM ride_weather WHERE ride_id=?", (workout_id,)
        ).fetchone()
    finally:
        conn.close()
    item = _row_to_workout(row)
    try:
        item["track"] = json.loads(track_row["track_json"]) if track_row else []
    except (ValueError, TypeError):
        item["track"] = []
    try:
        item["stops"] = json.loads(track_row["stops_json"]) if track_row else []
    except (ValueError, TypeError):
        item["stops"] = []
    if weather_row:
        try:
            item["weather"] = json.loads(weather_row["payload_json"])
        except (ValueError, TypeError):
            item["weather"] = None
    else:
        item["weather"] = None
    # File mtime/size for detail cache signatures.
    item["_mtime_ns"] = row["mtime_ns"]
    item["_size"] = row["size"]
    return item


def load_status(db_path, data_dir=None):
    db_path = Path(db_path)
    data_dir = Path(data_dir) if data_dir else DATA
    fit_count = len(list(Path(data_dir).glob("*.fit")))
    if not is_ready(db_path):
        return {
            "ready": False,
            "total": fit_count,
            "indexed": 0,
            "dirty": True,
            "data_updated": None,
            "updated": None,
        }
    conn = _connect(db_path)
    try:
        indexed = conn.execute("SELECT COUNT(*) AS n FROM rides").fetchone()["n"]
        latest = conn.execute(
            "SELECT date FROM rides WHERE date IS NOT NULL ORDER BY date DESC LIMIT 1"
        ).fetchone()
        meta = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM meta")
        }
    finally:
        conn.close()
    # data_updated mirrors legacy /api/workouts data_updated: newest FIT mtime.
    data_updated = None
    try:
        newest = max(
            (p.stat().st_mtime for p in Path(data_dir).glob("*.fit")),
            default=None,
        )
        if newest is not None:
            from datetime import datetime, timezone

            data_updated = datetime.fromtimestamp(newest, timezone.utc).isoformat()
    except OSError:
        data_updated = None
    dirty = meta.get("dirty", "0") == "1" or indexed != fit_count
    return {
        "ready": True,
        "total": fit_count,
        "indexed": indexed,
        "dirty": dirty,
        "data_updated": data_updated or (latest["date"] if latest else None),
        "updated": meta.get("last_check_utc"),
    }
