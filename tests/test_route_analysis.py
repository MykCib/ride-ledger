import unittest

from web.app import build_commute_analysis


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


if __name__ == "__main__":
    unittest.main()
