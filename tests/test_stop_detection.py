import unittest
from datetime import datetime, timedelta, timezone

from web.app import detect_stops


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def sample(seconds, speed, distance):
    return {
        "timestamp": START + timedelta(seconds=seconds),
        "speed": speed,
        "distance_m": distance,
    }


class StopDetectionTests(unittest.TestCase):
    def test_detects_gap_with_unchanged_distance(self):
        stops = detect_stops([
            sample(0, 3.0, 0),
            sample(1, 3.0, 3),
            sample(12, 3.0, 3),
            sample(13, 3.0, 6),
        ])

        self.assertEqual(stops, [{
            "start": "2026-01-01T00:00:02+00:00",
            "end": "2026-01-01T00:00:12+00:00",
            "duration_seconds": 10,
        }])

    def test_ignores_gap_with_distance_progress(self):
        stops = detect_stops([
            sample(0, 3.0, 0),
            sample(1, 3.0, 3),
            sample(12, 3.0, 36),
            sample(13, 3.0, 39),
        ])

        self.assertEqual(stops, [])

    def test_merges_start_and_low_speed_intervals(self):
        stops = detect_stops(
            [
                sample(5, 0.0, 0),
                sample(6, 0.0, 0),
                sample(20, 3.0, 0),
                sample(21, 3.0, 3),
            ],
            session_start=START,
            elapsed_seconds=21,
        )

        self.assertEqual(stops, [{
            "start": "2026-01-01T00:00:00+00:00",
            "end": "2026-01-01T00:00:20+00:00",
            "duration_seconds": 20,
        }])

    def test_drops_short_low_speed_run(self):
        stops = detect_stops([
            sample(0, 0.0, 0),
            sample(1, 0.0, 0),
            sample(2, 3.0, 3),
        ])

        self.assertEqual(stops, [])


if __name__ == "__main__":
    unittest.main()
