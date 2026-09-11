#!/usr/bin/env python3
"""Incremental SQLite indexer for downloaded FIT workouts.

Parses each FIT file once in the background so Flask request handlers can
serve from ``data/ledger.db`` instead of re-parsing the whole archive.

Usage:
    python -m host.indexer --full        # rebuild everything
    python -m host.indexer --incremental # upsert new/changed only (default)
    python -m host.indexer --check       # exit 0 if DB covers all FITs, else 2
    python -m host.indexer --ride <id>   # re-ingest one ride
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow running both as `python -m host.indexer` and as `python host/indexer.py`
# (the watcher uses the latter, where sys.path[0] is host/ instead of root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEFAULT_DB = DATA / "ledger.db"
SCHEMA_VERSION = 1

SUMMARY_FIELDS = (
    "id", "file", "date", "distance_km", "moving_seconds", "elapsed_seconds",
    "average_speed_kmh", "max_speed_kmh", "ascent_m", "descent_m",
    "calories", "temperature_c", "points", "estimated_stopped_seconds",
    "moving_percent", "stop_count", "longest_stop_seconds",
)


def resolve_db_path(explicit=None):
    if explicit:
        return Path(explicit)
    env = os.environ.get("LEDGER_DB", "").strip()
    if env:
        path = Path(env)
        return path if path.is_absolute() else ROOT / path
    return DEFAULT_DB


def connect(db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS rides(
          id TEXT PRIMARY KEY,
          file TEXT NOT NULL,
          mtime_ns INTEGER NOT NULL,
          size INTEGER NOT NULL,
          date TEXT,
          distance_km REAL,
          moving_seconds REAL,
          elapsed_seconds REAL,
          average_speed_kmh REAL,
          max_speed_kmh REAL,
          ascent_m REAL,
          descent_m REAL,
          calories INTEGER,
          temperature_c REAL,
          points INTEGER,
          estimated_stopped_seconds REAL,
          moving_percent REAL,
          stop_count INTEGER,
          longest_stop_seconds INTEGER,
          quality_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS ride_tracks(
          ride_id TEXT PRIMARY KEY REFERENCES rides(id) ON DELETE CASCADE,
          track_json TEXT NOT NULL,
          stops_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS ride_weather(
          ride_id TEXT PRIMARY KEY REFERENCES rides(id) ON DELETE CASCADE,
          payload_json TEXT NOT NULL,
          updated_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS meta(
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES('dirty', '0')",
    )
    conn.commit()


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def list_fit_files(data_dir):
    return sorted(Path(data_dir).glob("*.fit"))


def read_weather_payload(data_dir, ride_id):
    path = Path(data_dir) / "weather_cache" / f"{ride_id}.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _parse_fit(path):
    # Imported lazily so unit tests can mock web.app.parse_workout
    # and so importing indexer never requires Flask at module load.
    from web.app import parse_workout

    return parse_workout(path, include_track=True)


def upsert_ride(conn, fit_path, data_dir=None, parse_fn=None):
    """Parse one FIT file and store summary + track + weather. Returns True if stored."""
    fit_path = Path(fit_path)
    data_dir = Path(data_dir) if data_dir else fit_path.parent
    stat = fit_path.stat()
    parse = parse_fn or _parse_fit
    result = parse(fit_path)
    ride_id = result.get("id") or fit_path.stem
    summary = {field: result.get(field) for field in SUMMARY_FIELDS}
    summary["id"] = ride_id
    summary["file"] = fit_path.name
    quality = result.get("data_quality") or {}
    track = result.get("track") or []
    stops = result.get("stops") or []
    weather = read_weather_payload(data_dir, ride_id)
    with conn:
        conn.execute(
            """INSERT INTO rides(id, file, mtime_ns, size, date, distance_km,
               moving_seconds, elapsed_seconds, average_speed_kmh, max_speed_kmh,
               ascent_m, descent_m, calories, temperature_c, points,
               estimated_stopped_seconds, moving_percent, stop_count,
               longest_stop_seconds, quality_json)
               VALUES(:id, :file, :mtime_ns, :size, :date, :distance_km,
               :moving_seconds, :elapsed_seconds, :average_speed_kmh, :max_speed_kmh,
               :ascent_m, :descent_m, :calories, :temperature_c, :points,
               :estimated_stopped_seconds, :moving_percent, :stop_count,
               :longest_stop_seconds, :quality_json)
               ON CONFLICT(id) DO UPDATE SET
               file=excluded.file, mtime_ns=excluded.mtime_ns, size=excluded.size,
               date=excluded.date, distance_km=excluded.distance_km,
               moving_seconds=excluded.moving_seconds, elapsed_seconds=excluded.elapsed_seconds,
               average_speed_kmh=excluded.average_speed_kmh, max_speed_kmh=excluded.max_speed_kmh,
               ascent_m=excluded.ascent_m, descent_m=excluded.descent_m,
               calories=excluded.calories, temperature_c=excluded.temperature_c,
               points=excluded.points,
               estimated_stopped_seconds=excluded.estimated_stopped_seconds,
               moving_percent=excluded.moving_percent, stop_count=excluded.stop_count,
               longest_stop_seconds=excluded.longest_stop_seconds,
               quality_json=excluded.quality_json""",
            {
                **summary,
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "quality_json": json.dumps(quality),
            },
        )
        conn.execute(
            """INSERT INTO ride_tracks(ride_id, track_json, stops_json)
               VALUES(?, ?, ?)
               ON CONFLICT(ride_id) DO UPDATE SET
               track_json=excluded.track_json, stops_json=excluded.stops_json""",
            (ride_id, json.dumps(track), json.dumps(stops)),
        )
        if weather is not None:
            conn.execute(
                """INSERT INTO ride_weather(ride_id, payload_json, updated_utc)
                   VALUES(?, ?, ?)
                   ON CONFLICT(ride_id) DO UPDATE SET
                   payload_json=excluded.payload_json, updated_utc=excluded.updated_utc""",
                (
                    ride_id,
                    json.dumps(weather),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        else:
            conn.execute("DELETE FROM ride_weather WHERE ride_id=?", (ride_id,))
    return True


def incremental(data_dir=None, db_path=None, parse_fn=None):
    """Upsert new/changed FITs, prune deleted ones, refresh weather. Returns stats dict."""
    data_dir = Path(data_dir) if data_dir else DATA
    db_path = resolve_db_path(db_path)
    lock_path = Path(data_dir) / ".indexer.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        locked = True
    except FileExistsError:
        locked = False
    if not locked:
        return {"upserted": 0, "pruned": 0, "skipped": 0, "locked": True, "total": 0}
    try:
        conn = connect(db_path)
        try:
            init_schema(conn)
            if get_meta(conn, "schema_version") != str(SCHEMA_VERSION):
                raise RuntimeError(
                    f"ledger.db schema {get_meta(conn, 'schema_version')} != {SCHEMA_VERSION}; run --full"
                )
            existing = {
                row["id"]: (row["mtime_ns"], row["size"])
                for row in conn.execute("SELECT id, mtime_ns, size FROM rides")
            }
            # Also index by filename so renames/id changes are handled.
            existing_by_file = {
                row["file"]: (row["id"], row["mtime_ns"], row["size"])
                for row in conn.execute("SELECT id, file, mtime_ns, size FROM rides")
            }
            upserted = 0
            skipped = 0
            failed = 0
            seen_ids = set()
            for fit_path in list_fit_files(data_dir):
                stat = fit_path.stat()
                seen_ids.add(fit_path.stem)
                known = existing.get(fit_path.stem) or (
                    (existing_by_file[fit_path.name][1], existing_by_file[fit_path.name][2])
                    if fit_path.name in existing_by_file else None
                )
                if known and known[0] == stat.st_mtime_ns and known[1] == stat.st_size:
                    # Still refresh weather if the sidecar is newer than DB row.
                    weather = read_weather_payload(data_dir, fit_path.stem)
                    if weather is not None:
                        row = conn.execute(
                            "SELECT payload_json FROM ride_weather WHERE ride_id=?",
                            (fit_path.stem,),
                        ).fetchone()
                        current = row["payload_json"] if row else None
                        if current != json.dumps(weather):
                            with conn:
                                conn.execute(
                                    """INSERT INTO ride_weather(ride_id, payload_json, updated_utc)
                                       VALUES(?, ?, ?)
                                       ON CONFLICT(ride_id) DO UPDATE SET
                                       payload_json=excluded.payload_json,
                                       updated_utc=excluded.updated_utc""",
                                    (
                                        fit_path.stem,
                                        json.dumps(weather),
                                        datetime.now(timezone.utc).isoformat(),
                                    ),
                                )
                            upserted += 1
                            continue
                    skipped += 1
                    continue
                try:
                    upsert_ride(conn, fit_path, data_dir, parse_fn=parse_fn)
                    upserted += 1
                except Exception as error:
                    failed += 1
                    print(f"Skipping {fit_path.name}: {error}", file=sys.stderr)
            # Prune rides whose FIT file no longer exists.
            pruned = 0
            for row in conn.execute("SELECT id, file FROM rides"):
                if not (Path(data_dir) / row["file"]).is_file():
                    with conn:
                        conn.execute("DELETE FROM rides WHERE id=?", (row["id"],))
                    pruned += 1
            total = conn.execute("SELECT COUNT(*) AS n FROM rides").fetchone()["n"]
            with conn:
                set_meta(conn, "dirty", "1" if failed else "0")
                set_meta(conn, "last_check_utc", datetime.now(timezone.utc).isoformat())
                set_meta(conn, "last_total", str(total))
            return {
                "upserted": upserted,
                "pruned": pruned,
                "skipped": skipped,
                "failed": failed,
                "locked": False,
                "total": total,
            }
        finally:
            conn.close()
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def rebuild(data_dir=None, db_path=None, parse_fn=None):
    data_dir = Path(data_dir) if data_dir else DATA
    db_path = resolve_db_path(db_path)
    conn = connect(db_path)
    try:
        conn.executescript(
            "DROP TABLE IF EXISTS ride_weather;"
            "DROP TABLE IF EXISTS ride_tracks;"
            "DROP TABLE IF EXISTS rides;"
            "DROP TABLE IF EXISTS meta;"
        )
        conn.commit()
        init_schema(conn)
    finally:
        conn.close()
    return incremental(data_dir=data_dir, db_path=db_path, parse_fn=parse_fn)


def check(data_dir=None, db_path=None):
    data_dir = Path(data_dir) if data_dir else DATA
    db_path = resolve_db_path(db_path)
    if not Path(db_path).is_file():
        return False
    conn = connect(db_path)
    try:
        try:
            rows = {
                row["id"]: (row["mtime_ns"], row["size"])
                for row in conn.execute("SELECT id, mtime_ns, size FROM rides")
            }
        except sqlite3.OperationalError:
            return False
        fits = list_fit_files(data_dir)
        if len(fits) != len(rows):
            return False
        for fit_path in fits:
            stat = fit_path.stat()
            known = rows.get(fit_path.stem)
            if not known or known[0] != stat.st_mtime_ns or known[1] != stat.st_size:
                return False
        return True
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Index FIT files into data/ledger.db")
    parser.add_argument("--full", action="store_true", help="drop and rebuild the database")
    parser.add_argument("--incremental", action="store_true", help="upsert new/changed only (default)")
    parser.add_argument("--check", action="store_true", help="exit 0 if DB is current, 2 if stale")
    parser.add_argument("--ride", help="re-ingest a single ride id")
    parser.add_argument("--quiet", action="store_true", help="only print when files were added, removed, or failed")
    parser.add_argument("--db", help="override ledger.db path")
    parser.add_argument("--data", help="override data directory")
    args = parser.parse_args(argv)
    data_dir = Path(args.data) if args.data else DATA
    db_path = resolve_db_path(args.db)

    if args.check:
        ok = check(data_dir=data_dir, db_path=db_path)
        print("ledger.db current" if ok else "ledger.db stale", flush=True)
        return 0 if ok else 2

    if args.ride:
        conn = connect(db_path)
        try:
            init_schema(conn)
        finally:
            conn.close()
        fit_path = Path(data_dir) / f"{args.ride}.fit"
        if not fit_path.is_file():
            print(f"No such FIT: {fit_path.name}", file=sys.stderr)
            return 1
        conn = connect(db_path)
        try:
            upsert_ride(conn, fit_path, data_dir)
            with conn:
                set_meta(conn, "last_check_utc", datetime.now(timezone.utc).isoformat())
        finally:
            conn.close()
        print(f"indexer: upserted {fit_path.name}", flush=True)
        return 0

    if args.full:
        stats = rebuild(data_dir=data_dir, db_path=db_path)
    else:
        stats = incremental(data_dir=data_dir, db_path=db_path)
    if stats.get("locked"):
        if not args.quiet:
            print("indexer: another run holds the lock, skipping", flush=True)
        return 0
    if args.quiet and not stats.get("upserted") and not stats.get("pruned") and not stats.get("failed"):
        return 0
    print(
        f"indexer: upserted {stats['upserted']}, pruned {stats['pruned']}, "
        f"skipped {stats['skipped']}, total {stats['total']}",
        flush=True,
    )
    return 0 if not stats.get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
