import unittest
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from web.app import COMMUTES_CACHE_VERSION, INSIGHTS_CACHE_VERSION, WORKOUTS_CACHE_VERSION, app, build_commute_analysis, build_data_quality, build_route_segments, build_weather_analysis, build_workout_insights, route_performance, vertical_rate


def ride(ride_id, date, distance=5.0, speed=20.0):
    return {
        "id": ride_id,
        "date": date,
        "distance_km": distance,
        "average_speed_kmh": speed,
        "moving_seconds": 900,
        "elapsed_seconds": 1000,
        "estimated_stopped_seconds": 100,
    }


class RouteAnalysisTests(unittest.TestCase):
    def test_groups_reverse_directions_and_uses_earlier_departure_as_outbound(self):
        routes = [
            {"id": "outbound-1", "points": [[54.7000, 25.2100], [54.7050, 25.2200], [54.7100, 25.2900]]},
            {"id": "outbound-2", "points": [[54.7001, 25.2101], [54.7050, 25.2200], [54.7101, 25.2901]]},
            {"id": "return-1", "points": [[54.7101, 25.2901], [54.7050, 25.2200], [54.7001, 25.2101]]},
            {"id": "loop", "points": [[54.7000, 25.2100], [54.7050, 25.2200], [54.7000, 25.2100]]},
        ]
        items = [
            ride("outbound-1", "2026-08-31T06:00:00+00:00"),
            ride("outbound-2", "2026-08-30T07:00:00+00:00"),
            ride("return-1", "2026-08-30T17:00:00+00:00"),
            ride("loop", "2026-08-29T12:00:00+00:00"),
        ]

        result = build_commute_analysis(items, routes)

        self.assertEqual(len(result["groups"]), 1)
        group = result["groups"][0]
        self.assertEqual(group["outbound"]["count"], 2)
        self.assertEqual(group["return"]["count"], 1)
        self.assertEqual(set(group["outbound"]["ride_ids"]), {"outbound-1", "outbound-2"})
        self.assertEqual(result["assignments"]["outbound-1"]["direction"], "outbound")
        self.assertEqual(result["assignments"]["return-1"]["direction"], "return")
        self.assertEqual(result["assignments"]["loop"]["direction"], "loop")

    def test_single_direction_is_still_grouped(self):
        routes = [{"id": "one-way", "points": [[54.7000, 25.2100], [54.7100, 25.2900]]}]
        result = build_commute_analysis([ride("one-way", "2026-08-31T08:00:00+00:00")], routes)

        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(result["groups"][0]["outbound"]["count"], 1)
        self.assertEqual(result["groups"][0]["return"]["count"], 0)
        self.assertEqual(result["assignments"]["one-way"]["direction"], "outbound")
        self.assertIsNone(result["groups"][0]["return"]["typical_departure_time"])
        self.assertIsNone(result["groups"][0]["return"]["typical_arrival_time"])
        self.assertIsNone(result["groups"][0]["return"]["average_commute_seconds"])
        self.assertIsNone(result["groups"][0]["return"]["distance_variation_km"])

    def test_route_performance_includes_typical_times_and_distance_variation(self):
        routes = [
            {"id": "morning-1", "points": [[54.7000, 25.2100], [54.7100, 25.2900]]},
            {"id": "morning-2", "points": [[54.7001, 25.2101], [54.7101, 25.2901]]},
            {"id": "morning-3", "points": [[54.7002, 25.2102], [54.7102, 25.2902]]},
        ]
        items = [
            ride("morning-1", "2026-08-31T08:00:00+00:00", distance=5.0),
            ride("morning-2", "2026-08-30T08:30:00+00:00", distance=7.0),
            ride("morning-3", "2026-08-29T09:00:00+00:00", distance=7.0),
        ]
        items[0]["elapsed_seconds"] = 1800
        items[1]["elapsed_seconds"] = 2400
        items[2]["elapsed_seconds"] = 3000

        with patch.dict(os.environ, {"RIDE_LEDGER_TIMEZONE": "UTC"}):
            result = build_commute_analysis(items, routes)
        performance = result["groups"][0]["outbound"]

        self.assertEqual(result["timezone"], "UTC")
        self.assertEqual(performance["typical_departure_time"], "08:30")
        self.assertEqual(performance["typical_arrival_time"], "09:10")
        self.assertEqual(performance["average_commute_seconds"], 2400.0)
        self.assertEqual(performance["distance_variation_km"], 0.94)

    def test_route_performance_uses_elapsed_time_and_excludes_invalid_values(self):
        items = [
            ride("zero", "2026-01-01T23:55:00+00:00", distance=5.0),
            ride("no-date", None, distance=None),
            ride("negative", "2026-01-01T00:05:00+00:00", distance=7.0),
            ride("invalid", "2026-01-01T00:10:00+00:00", distance=None),
        ]
        items[0]["elapsed_seconds"] = 0
        items[0]["moving_seconds"] = 900
        items[1]["elapsed_seconds"] = 60
        items[2]["elapsed_seconds"] = -1
        items[3]["elapsed_seconds"] = "not-a-number"

        performance = route_performance(items, timezone.utc)

        self.assertEqual(performance["average_commute_seconds"], 30.0)
        self.assertEqual(performance["average_elapsed_seconds"], 30.0)
        self.assertEqual(performance["typical_departure_time"], "00:05")
        self.assertEqual(performance["typical_arrival_time"], "23:55")
        self.assertEqual(performance["distance_variation_km"], 1.0)

    def test_typical_times_use_circular_median_and_handle_midnight_rollover(self):
        items = [
            ride("late", "2026-01-01T23:55:00+00:00"),
            ride("early", "2026-01-02T00:05:00+00:00"),
            ride("early-2", "2026-01-02T00:10:00+00:00"),
        ]
        for item in items:
            item["elapsed_seconds"] = 0

        performance = route_performance(items, timezone.utc)

        self.assertEqual(performance["typical_departure_time"], "00:05")
        self.assertEqual(performance["typical_arrival_time"], "00:05")

        rollover = route_performance([{
            **ride("rollover", "2026-01-01T23:55:00+00:00"),
            "elapsed_seconds": 600,
        }], timezone.utc)
        self.assertEqual(rollover["typical_arrival_time"], "00:05")

    def test_typical_times_convert_instants_before_calculating_local_time(self):
        performance = route_performance([{
            **ride("dst", "2026-03-29T00:30:00+00:00"),
            "elapsed_seconds": 3600,
        }], ZoneInfo("Europe/Vilnius"))

        self.assertEqual(performance["typical_departure_time"], "02:30")
        self.assertEqual(performance["typical_arrival_time"], "04:30")

    def test_commute_cache_version_matches_current_metric_schema(self):
        self.assertEqual(COMMUTES_CACHE_VERSION, 4)
        self.assertEqual(WORKOUTS_CACHE_VERSION, 5)
        self.assertEqual(INSIGHTS_CACHE_VERSION, 2)

    def test_vertical_rate_uses_moving_time(self):
        self.assertEqual(vertical_rate(100, 1800), 200.0)
        self.assertEqual(vertical_rate(0, 1800), 0.0)
        self.assertIsNone(vertical_rate(100, 0))
        self.assertIsNone(vertical_rate("invalid", 1800))

    def test_data_quality_ignores_gaps_covered_by_detected_stops(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = [
            {"timestamp": start, "speed": 0.1, "distance_m": 0},
            {"timestamp": start + timedelta(seconds=12), "speed": 0.1, "distance_m": 0},
        ]
        result = build_data_quality(
            samples,
            2,
            {"start_time": start, "total_elapsed_time": 12, "total_moving_time": 0, "total_distance": 0},
            start,
            12,
            0,
            [{"start": start.isoformat(), "end": (start + timedelta(seconds=12)).isoformat(), "duration_seconds": 12}],
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["warnings"], [])

    def test_data_quality_reports_bad_points_and_metrics(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = [
            {"timestamp": start, "speed": 4, "distance_m": 0, "lat": 54.7, "lon": 25.2, "coordinate_present": True},
            {"timestamp": start + timedelta(seconds=1), "speed": 40, "distance_m": 100, "lat": 54.701, "lon": 25.2, "coordinate_present": True},
            {"timestamp": start + timedelta(seconds=12), "speed": 4, "distance_m": 200, "lat": 54.702, "lon": 25.2, "coordinate_present": True},
            {"timestamp": start + timedelta(seconds=13), "speed": -1, "distance_m": -1, "lat": 95, "lon": 25.2, "coordinate_present": True},
            {"timestamp": start + timedelta(seconds=14), "speed": 4, "distance_m": 80, "lat": 54.704, "lon": 25.2, "coordinate_present": True},
        ]
        result = build_data_quality(
            samples,
            4,
            {"start_time": start, "total_elapsed_time": 20, "total_moving_time": 25, "total_distance": 1000},
            start,
            20,
            25,
            [{"start": (start + timedelta(seconds=30)).isoformat(), "end": (start + timedelta(seconds=931)).isoformat(), "duration_seconds": 901}],
        )

        codes = {warning["code"] for warning in result["warnings"]}
        self.assertEqual(result["status"], "warning")
        self.assertEqual(codes, {"invalid_gps", "gps_gap", "speed_spike", "long_stop", "suspicious_distance", "incomplete_recording"})

    def test_original_fit_download_is_limited_to_data_directory(self):
        with TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "ride.fit").write_bytes(b"original fit bytes")
            with patch("web.app.DATA", data):
                with app.test_client() as client:
                    response = client.get("/api/workouts/ride/download")
                    missing = client.get("/api/workouts/missing/download")
                    traversal = client.get("/api/workouts/../ride/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"original fit bytes")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        response.close()
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(traversal.status_code, 404)

    def test_weather_analysis_compares_conditions_and_route_directions(self):
        items = [
            ride("fast", "2026-08-31T08:00:00+00:00", speed=30.0),
            ride("dry", "2026-08-30T08:00:00+00:00", speed=25.0),
            ride("wet", "2026-08-29T17:00:00+00:00", speed=20.0),
        ]
        weather = {
            "fast": {"temperature_c": 20, "wind_kmh": 10, "precipitation_mm": 0},
            "dry": {"temperature_c": 22, "wind_kmh": 5, "precipitation_mm": 0},
            "wet": {"temperature_c": 15, "wind_kmh": 15, "precipitation_mm": 1},
        }
        commute = {
            "groups": [{
                "id": "route-1-2",
                "label": "A <-> B",
                "outbound": {"ride_ids": ["fast", "dry"]},
                "return": {"ride_ids": ["wet"]},
            }],
        }
        with TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "weather_cache").mkdir()
            for ride_id, values in weather.items():
                (data / "weather_cache" / f"{ride_id}.json").write_text(json.dumps(values))
            with patch("web.app.DATA", data):
                result = build_weather_analysis(items, commute)

        self.assertEqual(result["available_rides"], 3)
        self.assertEqual(result["conditions"]["dry"]["count"], 2)
        self.assertEqual(result["conditions"]["dry"]["average_speed_kmh"], 27.5)
        self.assertEqual(result["conditions"]["wet"]["count"], 1)
        self.assertEqual(result["fastest"]["ride_id"], "fast")
        self.assertEqual(result["directions"][0]["outbound"]["count"], 2)
        self.assertEqual(result["directions"][0]["return"]["average_speed_kmh"], 20.0)
        self.assertEqual(result["temperature_bins"][0]["label"], "15-20 C")

    def test_activity_insights_include_local_weekday_hours_and_calendar(self):
        items = [
            ride("monday", "2026-08-31T08:15:00+00:00", distance=5.0),
            ride("monday-late", "2026-08-31T17:15:00+00:00", distance=6.0),
            ride("tuesday", "2026-09-01T08:15:00+00:00", distance=7.0),
        ]
        with TemporaryDirectory() as directory:
            with patch("web.app.DATA", Path(directory)):
                with patch.dict(os.environ, {"RIDE_LEDGER_TIMEZONE": "UTC"}):
                    result = build_workout_insights(items)

        self.assertEqual(result["timezone"], "UTC")
        self.assertEqual(result["weekday_counts"][:2], [2, 1])
        self.assertEqual(result["departure_hour_counts"][8], 2)
        self.assertEqual(result["departure_hour_counts"][17], 1)
        self.assertEqual(result["calendar"], [
            {"date": "2026-08-31", "ride_count": 2, "distance_km": 11.0},
            {"date": "2026-09-01", "ride_count": 1, "distance_km": 7.0},
        ])

    def test_repeated_routes_are_divided_into_supported_geographic_segments(self):
        def track(offset, seconds_per_point):
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            return [
                {
                    "lat": 54.7000 + offset + index * 0.001,
                    "lon": 25.2100,
                    "distance_m": index * 100,
                    "t": (start + timedelta(seconds=index * seconds_per_point)).isoformat(),
                }
                for index in range(11)
            ]

        groups = [{
            "id": "route-1-2",
            "label": "A <-> B",
            "outbound": {"ride_ids": ["ride-a", "ride-b"], "count": 2},
            "return": {"ride_ids": [], "count": 0},
        }]
        result = build_route_segments(groups, {"ride-a": track(0, 10), "ride-b": track(0.0001, 20)})

        self.assertEqual(result["segment_count"], 10)
        self.assertEqual(len(result["segments"]), 10)
        first = result["segments"][0]
        self.assertEqual(first["id"], "route-1-2-outbound-1")
        self.assertEqual(first["progress_start"], 0)
        self.assertEqual(first["progress_end"], 10)
        self.assertEqual(first["ride_count"], 2)
        self.assertEqual(first["total_rides"], 2)
        self.assertEqual(first["coverage_percent"], 100.0)
        self.assertEqual(first["distance_km"], 0.1)
        self.assertEqual(first["performance_count"], 2)
        self.assertEqual(first["average_time_seconds"], 15.0)
        self.assertEqual(first["average_speed_kmh"], 27.0)
        self.assertEqual(first["fastest_time_seconds"], 10.0)
        self.assertEqual(first["record_ride_id"], "ride-a")

    def test_saved_location_name_is_applied_to_group_and_assignment(self):
        routes = [
            {"id": "outbound", "points": [[54.7000, 25.2100], [54.7100, 25.2900]]},
            {"id": "return", "points": [[54.7100, 25.2900], [54.7000, 25.2100]]},
        ]
        items = [
            ride("outbound", "2026-08-31T08:00:00+00:00"),
            ride("return", "2026-08-31T17:00:00+00:00"),
        ]
        with TemporaryDirectory() as directory:
            names_path = Path(directory) / "location_names.json"
            names_path.write_text(json.dumps({"locations": [{"lat": 54.7001, "lon": 25.2101, "name": "Home"}]}))
            with patch("web.app.LOCATION_NAMES_PATH", names_path):
                result = build_commute_analysis(items, routes)

        self.assertIn("Home", result["groups"][0]["label"])
        self.assertTrue(any("Home" in assignment["label"] for assignment in result["assignments"].values()))


if __name__ == "__main__":
    unittest.main()
