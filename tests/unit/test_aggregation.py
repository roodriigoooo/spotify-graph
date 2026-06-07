import unittest

import _path  # noqa: F401  (sets sys.path)
from taste.aggregation import (
    recency_weight,
    recency_weighted_counts,
    normalize,
    genre_distribution,
    top_items,
    SECONDS_PER_DAY,
)


class TestRecencyWeight(unittest.TestCase):
    def test_now_is_full_weight(self):
        self.assertAlmostEqual(recency_weight(1000.0, 1000.0, half_life_days=30), 1.0)

    def test_one_half_life_is_half(self):
        now = 10_000_000.0
        played = now - 30 * SECONDS_PER_DAY
        self.assertAlmostEqual(recency_weight(played, now, half_life_days=30), 0.5, places=6)

    def test_two_half_lives_is_quarter(self):
        now = 10_000_000.0
        played = now - 60 * SECONDS_PER_DAY
        self.assertAlmostEqual(recency_weight(played, now, half_life_days=30), 0.25, places=6)

    def test_future_clamped_to_now(self):
        self.assertAlmostEqual(recency_weight(2000.0, 1000.0, half_life_days=30), 1.0)


class TestAggregation(unittest.TestCase):
    def test_counts_sum_repeated_plays(self):
        now = 10_000_000.0
        events = [
            {"itemId": "a", "playedAt": now},
            {"itemId": "a", "playedAt": now},
            {"itemId": "b", "playedAt": now},
        ]
        counts = recency_weighted_counts(events, now, half_life_days=30)
        self.assertAlmostEqual(counts["a"], 2.0)
        self.assertAlmostEqual(counts["b"], 1.0)

    def test_recent_beats_old(self):
        now = 10_000_000.0
        events = [
            {"itemId": "recent", "playedAt": now},
            {"itemId": "old", "playedAt": now - 90 * SECONDS_PER_DAY},
        ]
        counts = recency_weighted_counts(events, now, half_life_days=30)
        self.assertGreater(counts["recent"], counts["old"])

    def test_skips_missing_ids(self):
        counts = recency_weighted_counts([{"playedAt": 1.0}], 1.0)
        self.assertEqual(counts, {})

    def test_normalize_sums_to_one(self):
        d = normalize({"a": 3.0, "b": 1.0})
        self.assertAlmostEqual(sum(d.values()), 1.0)
        self.assertAlmostEqual(d["a"], 0.75)

    def test_normalize_empty(self):
        self.assertEqual(normalize({}), {})

    def test_genre_distribution_splits_across_genres(self):
        artist_weights = {"x": 1.0}
        artist_genres = {"x": ["indie", "folk"]}
        dist = genre_distribution(artist_weights, artist_genres)
        self.assertAlmostEqual(dist["indie"], 0.5)
        self.assertAlmostEqual(dist["folk"], 0.5)

    def test_top_items_ordering(self):
        self.assertEqual(top_items({"a": 1.0, "b": 3.0, "c": 2.0}, n=2), ["b", "c"])


if __name__ == "__main__":
    unittest.main()
