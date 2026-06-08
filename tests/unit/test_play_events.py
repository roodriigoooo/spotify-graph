"""
play_events tests — Spotify recently-played items -> PlayEvents rows (the v2 write path).
"""
import unittest

import _path  # noqa: F401  (sets sys.path to the layer)

from play_events import to_play_events, parse_played_at


NOW = 1_700_000_000.0
DAY = 86400.0


def _item(track_id, played_at, artists=(("a1", "Artist One"),), name="Song"):
    return {
        "track": {
            "id": track_id,
            "name": name,
            "artists": [{"id": aid, "name": an} for aid, an in artists],
        },
        "played_at": played_at,
    }


class TestParsePlayedAt(unittest.TestCase):
    def test_zulu(self):
        self.assertIsNotNone(parse_played_at("2024-01-02T03:04:05Z"))

    def test_fractional_zulu(self):
        a = parse_played_at("2024-01-02T03:04:05.678Z")
        b = parse_played_at("2024-01-02T03:04:05Z")
        self.assertAlmostEqual(a - b, 0.678, places=3)

    def test_explicit_offset(self):
        self.assertIsNotNone(parse_played_at("2024-01-02T03:04:05+00:00"))

    def test_bad_input(self):
        self.assertIsNone(parse_played_at(""))
        self.assertIsNone(parse_played_at("not a date"))
        self.assertIsNone(parse_played_at(None))


class TestToPlayEvents(unittest.TestCase):
    def test_basic_row_shape(self):
        items = [_item("t1", "2024-01-02T03:04:05Z", artists=(("a1", "A"), ("a2", "B")))]
        rows = to_play_events(items, "u", now_ts=NOW)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["userId"], "u")
        self.assertEqual(r["trackId"], "t1")
        self.assertEqual(r["artistIds"], ["a1", "a2"])
        self.assertEqual(r["artistName"], "A")
        self.assertTrue(r["sk"].endswith("#t1"))
        self.assertEqual(len(r["sk"].split("#")[0]), 13)  # zero-padded ms
        self.assertGreater(r["ttl"], r["playedAt"])

    def test_sort_key_orders_by_time(self):
        items = [
            _item("old", "2023-01-01T00:00:00Z"),
            _item("new", "2024-06-01T00:00:00Z"),
        ]
        rows = sorted(to_play_events(items, "u", now_ts=NOW), key=lambda r: r["sk"])
        self.assertEqual(rows[0]["trackId"], "old")
        self.assertEqual(rows[1]["trackId"], "new")

    def test_skips_missing_id_or_timestamp(self):
        items = [
            {"track": {"name": "no id"}, "played_at": "2024-01-02T03:04:05Z"},
            _item("ok", "2024-01-02T03:04:05Z"),
            _item("bad_time", "garbage"),
        ]
        rows = to_play_events(items, "u", now_ts=NOW)
        self.assertEqual([r["trackId"] for r in rows], ["ok"])

    def test_dedup_by_sort_key(self):
        # same track + same timestamp (page boundary repeat) -> one row
        items = [_item("t1", "2024-01-02T03:04:05Z"), _item("t1", "2024-01-02T03:04:05Z")]
        rows = to_play_events(items, "u", now_ts=NOW)
        self.assertEqual(len(rows), 1)

    def test_ttl_uses_ttl_days(self):
        rows = to_play_events([_item("t1", "2024-01-02T03:04:05Z")], "u",
                              now_ts=NOW, ttl_days=10)
        self.assertEqual(rows[0]["ttl"], int(NOW + 10 * DAY))

    def test_empty_inputs(self):
        self.assertEqual(to_play_events([], "u", now_ts=NOW), [])
        self.assertEqual(to_play_events([_item("t", "2024-01-02T03:04:05Z")], "", now_ts=NOW), [])


if __name__ == "__main__":
    unittest.main()
