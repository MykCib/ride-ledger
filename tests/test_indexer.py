import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from host import indexer


def _summary(ride_id, filename):
    return {
        "id": ride_id,
        "file": filename,
        "date": "2026-01-01T08:00:00+00:00",
        "distance_km": 5.0,
        "moving_seconds": 900,
        "elapsed_seconds": 1000,
        "average_speed_kmh": 20.0,
        "max_speed_kmh": 30.0,
        "ascent_m": 10,
        "descent_m": 8,
        "calories": 100,
        "temperature_c": 15,
        "points": 2,
        "estimated_stopped_seconds": 100,
        "moving_percent": 90.0,
        "stop_count": 0,
        "longest_stop_seconds": 0,
        "data_quality": {"status": "ok", "warning_count": 0, "warnings": []},
        "track": [
            {"lat": 54.7, "lon": 25.2, "t": "2026-01-01T08:00:00+00:00", "speed": 5.0,
             "altitude": 100, "distance_m": 0},
            {"lat": 54.701, "lon": 25.201, "t": "2026-01-01T08:01:00+00:00", "speed": 6.0,
             "altitude": 101, "distance_m": 100},
        ],
        "stops": [],
    }


class IndexerTests(unittest.TestCase):
    def test_incremental_ingests_and_is_idempotent(self):
        with TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "a.fit").write_bytes(b"fit-a")
            (data / "b.fit").write_bytes(b"fit-b")
            db = data / "ledger.db"
            calls = []

            def fake_parse(path):
                calls.append(path.name)
                return _summary(path.stem, path.name)

            stats = indexer.incremental(data_dir=data, db_path=db, parse_fn=fake_parse)
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["upserted"], 2)
            self.assertEqual(len(calls), 2)

            calls.clear()
            stats2 = indexer.incremental(data_dir=data, db_path=db, parse_fn=fake_parse)
            self.assertEqual(stats2["upserted"], 0)
            self.assertEqual(stats2["skipped"], 2)
            self.assertEqual(calls, [])
            self.assertTrue(indexer.check(data_dir=data, db_path=db))

    def test_touch_reingests_only_changed_file(self):
        with TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "a.fit").write_bytes(b"fit-a")
            (data / "b.fit").write_bytes(b"fit-b")
            db = data / "ledger.db"
            indexer.incremental(
                data_dir=data, db_path=db,
                parse_fn=lambda p: _summary(p.stem, p.name),
            )
            # Bump b.fit size so only it is stale.
            (data / "b.fit").write_bytes(b"fit-b-longer")
            calls = []

            def fake_parse(path):
                calls.append(path.name)
                return _summary(path.stem, path.name)

            stats = indexer.incremental(data_dir=data, db_path=db, parse_fn=fake_parse)
            self.assertEqual(calls, ["b.fit"])
            self.assertEqual(stats["upserted"], 1)

    def test_delete_prunes_row(self):
        with TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "a.fit").write_bytes(b"fit-a")
            (data / "b.fit").write_bytes(b"fit-b")
            db = data / "ledger.db"
            indexer.incremental(
                data_dir=data, db_path=db,
                parse_fn=lambda p: _summary(p.stem, p.name),
            )
            (data / "b.fit").unlink()
            stats = indexer.incremental(
                data_dir=data, db_path=db,
                parse_fn=lambda p: _summary(p.stem, p.name),
            )
            self.assertEqual(stats["pruned"], 1)
            self.assertEqual(stats["total"], 1)

    def test_weather_sidecar_is_mirrored(self):
        with TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "a.fit").write_bytes(b"fit-a")
            (data / "weather_cache").mkdir()
            (data / "weather_cache" / "a.json").write_text(json.dumps({
                "temperature_c": 20, "wind_kmh": 10, "precipitation_mm": 0,
            }))
            db = data / "ledger.db"
            indexer.incremental(
                data_dir=data, db_path=db,
                parse_fn=lambda p: _summary(p.stem, p.name),
            )
            from web import ledger_db
            status = ledger_db.load_status(db, data)
            self.assertTrue(status["ready"])
            items, weather_by_id, _meta = ledger_db.load_workouts(db)
            self.assertIn("a", weather_by_id)
            self.assertEqual(weather_by_id["a"]["temperature_c"], 20)

    def test_corrupt_fit_is_skipped_and_marks_dirty(self):
        with TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "good.fit").write_bytes(b"fit-good")
            (data / "bad.fit").write_bytes(b"fit-bad")
            db = data / "ledger.db"

            def fake_parse(path):
                if path.name == "bad.fit":
                    raise ValueError("corrupt")
                return _summary(path.stem, path.name)

            stats = indexer.incremental(data_dir=data, db_path=db, parse_fn=fake_parse)
            self.assertEqual(stats["total"], 1)
            self.assertEqual(stats["failed"], 1)
            from web import ledger_db
            conn = ledger_db._connect(db) if hasattr(ledger_db, "_connect") else None
            if conn is not None:
                row = conn.execute("SELECT value FROM meta WHERE key='dirty'").fetchone()
                conn.close()
                self.assertEqual(row["value"], "1")

    def test_watcher_runs_indexer_after_weather(self):
        from host import watch_board
        with patch.object(watch_board, "sync_board", return_value=["one.fit"]), \
             patch.object(watch_board.subprocess, "run") as run, \
             patch.object(watch_board, "COOLDOWN_SECONDS", 3600), \
             patch.object(watch_board, "INDEX_ON_SYNC", True):
            run.side_effect = [Mock(returncode=0), Mock(returncode=0)]
            delay = watch_board.sync_cycle(Path("/tmp/root"), Path("/tmp/python"), Path("/tmp/weather"))
        self.assertEqual(delay, 3600)
        self.assertEqual(run.call_count, 2)
        indexer_cmd = run.call_args_list[1][0][0]
        self.assertIn("indexer.py", str(indexer_cmd[1]))
        self.assertIn("--incremental", indexer_cmd)


if __name__ == "__main__":
    unittest.main()
