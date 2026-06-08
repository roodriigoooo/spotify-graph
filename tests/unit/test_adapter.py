"""
Adapter tests — DynamoDB shapes (v1 snapshot + v2 footprint) -> UserTasteProfile.

These guard the migration seam: the graph must keep working whether a user has only the old
snapshot, only the new play history, or both, and must never raise on a Decimal or a missing
field.
"""
import unittest
from decimal import Decimal

import _path  # noqa: F401  (sets sys.path)

from taste import build_profile, EngineParams, score_pair
from taste.whitening import WhiteningParams


NOW = 1_700_000_000.0
DAY = 86400.0


class TestSnapshotFallback(unittest.TestCase):
    def test_v1_record_only(self):
        record = {
            "userId": "u1",
            "topArtists": {
                "long_term": [{"id": "a1", "name": "A", "genres": ["indie folk"]}],
                "short_term": [{"id": "a2", "name": "B", "genres": ["slowcore"]}],
            },
            "followedArtists": [{"id": "a3", "name": "C"}],
            "genreVector": {"indie folk": Decimal("0.6"), "slowcore": Decimal("0.4")},
        }
        p = build_profile(record, now_ts=NOW)
        self.assertEqual(p.user_id, "u1")
        # long_term weight 3 > short_term 1 > followed 1
        self.assertGreater(p.artist_weights["a1"], p.artist_weights["a2"])
        self.assertIn("a3", p.artist_weights)
        # genre dist taken straight from the stored vector, renormalized
        self.assertAlmostEqual(sum(p.genre_dist.values()), 1.0, places=6)
        # no embeddings -> lyric facet will be dropped
        self.assertEqual(p.track_embeddings, [])

    def test_empty_record_is_safe(self):
        p = build_profile(None, now_ts=NOW)
        self.assertEqual(p.artist_weights, {})
        self.assertEqual(p.genre_dist, {})
        self.assertEqual(p.track_embeddings, [])
        self.assertIsNone(p.gaussian)


class TestContinuousFootprint(unittest.TestCase):
    def test_recency_weights_artists(self):
        # a1 played today, a2 played 60 days ago -> a1 should dominate
        events = [
            {"trackId": "t1", "artistIds": ["a1"], "playedAt": NOW},
            {"trackId": "t2", "artistIds": ["a2"], "playedAt": NOW - 60 * DAY},
        ]
        p = build_profile({"userId": "u"}, play_events=events, now_ts=NOW)
        self.assertGreater(p.artist_weights["a1"], p.artist_weights["a2"])

    def test_events_override_snapshot(self):
        record = {
            "userId": "u",
            "topArtists": {"long_term": [{"id": "old", "name": "Old", "genres": ["jazz"]}]},
            "genreVector": {"jazz": Decimal("1.0")},
        }
        events = [{"trackId": "t1", "artistIds": ["new"], "playedAt": NOW}]
        p = build_profile(record, play_events=events, now_ts=NOW)
        # artist weights now come from events, not the snapshot
        self.assertIn("new", p.artist_weights)
        self.assertNotIn("old", p.artist_weights)

    def test_genre_dist_from_events_uses_record_genre_map(self):
        record = {
            "userId": "u",
            "topArtists": {"long_term": [{"id": "a1", "genres": ["indie folk", "slowcore"]}]},
        }
        events = [{"trackId": "t1", "artistIds": ["a1"], "playedAt": NOW}]
        p = build_profile(record, play_events=events, now_ts=NOW)
        self.assertAlmostEqual(sum(p.genre_dist.values()), 1.0, places=6)
        # one artist, two genres, split evenly
        self.assertAlmostEqual(p.genre_dist["indie folk"], p.genre_dist["slowcore"], places=6)


class TestLyricEmbeddings(unittest.TestCase):
    def test_embeddings_whitened_and_weighted_by_recency(self):
        # identity whitening (no params) -> embeddings pass through
        record = {"userId": "u"}
        embs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        ids = ["t1", "t2"]
        events = [
            {"trackId": "t1", "artistIds": ["a"], "playedAt": NOW},
            {"trackId": "t2", "artistIds": ["a"], "playedAt": NOW - 90 * DAY},
        ]
        p = build_profile(record, play_events=events, track_embeddings=embs,
                          track_ids=ids, now_ts=NOW)
        self.assertEqual(len(p.track_embeddings), 2)
        self.assertEqual(len(p.track_weights), 2)
        self.assertGreater(p.track_weights[0], p.track_weights[1])  # recency
        self.assertIsNotNone(p.gaussian)

    def test_whitening_is_applied(self):
        # a real (centering) transform should change the vectors
        wp = WhiteningParams(mean=[1.0, 1.0], components=[[1.0, 0.0], [0.0, 1.0]])
        params = EngineParams(whitening=wp)
        record = {"userId": "u", "trackEmbeddings": [[2.0, 3.0]]}
        p = build_profile(record, params=params, now_ts=NOW)
        self.assertEqual(p.track_embeddings[0], [1.0, 2.0])  # (x - mean)

    def test_decimal_embeddings_coerced(self):
        record = {"userId": "u", "trackEmbeddings": [[Decimal("0.5"), Decimal("0.5")]],
                  "trackWeights": [Decimal("2.0")]}
        p = build_profile(record, now_ts=NOW)
        self.assertEqual(p.track_embeddings[0], [0.5, 0.5])
        self.assertEqual(p.track_weights[0], 2.0)


class TestEndToEnd(unittest.TestCase):
    def test_two_built_profiles_score(self):
        ra = {
            "userId": "a",
            "topArtists": {"long_term": [{"id": "x", "genres": ["indie folk"]}]},
            "genreVector": {"indie folk": Decimal("1.0")},
            "trackEmbeddings": [[1.0, 0.0, 0.0]],
        }
        rb = {
            "userId": "b",
            "topArtists": {"long_term": [{"id": "x", "genres": ["indie folk"]}]},
            "genreVector": {"indie folk": Decimal("1.0")},
            "trackEmbeddings": [[0.9, 0.1, 0.0]],
        }
        pa, pb = build_profile(ra, now_ts=NOW), build_profile(rb, now_ts=NOW)
        res = score_pair(pa, pb, EngineParams())
        self.assertIn("artist", res["facets"])
        self.assertIn("genre", res["facets"])
        self.assertIn("lyric", res["facets"])
        self.assertGreaterEqual(res["similarity"], 0.0)
        self.assertLessEqual(res["similarity"], 1.0)


if __name__ == "__main__":
    unittest.main()
