import unittest

import _path  # noqa: F401
from taste import UserTasteProfile, EngineParams, score_pair
from taste.calibration import PercentileCalibrator


def make_profile(uid, artists, genres, tracks):
    return UserTasteProfile(
        user_id=uid,
        artist_weights={a: 1.0 for a in artists},
        genre_dist=genres,
        track_embeddings=tracks,
        track_weights=[1.0] * len(tracks),
    )


class TestScorePair(unittest.TestCase):
    def setUp(self):
        self.alice = make_profile(
            "alice", ["a", "b"], {"indie": 0.5, "folk": 0.5},
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )
        self.alice_twin = make_profile(
            "twin", ["a", "b"], {"indie": 0.5, "folk": 0.5},
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )
        self.bob = make_profile(
            "bob", ["x", "y"], {"pop": 1.0},
            [[0.0, 0.0, 1.0]],
        )

    def test_identical_profiles_score_high(self):
        r = score_pair(self.alice, self.alice_twin)
        self.assertGreater(r["similarity"], 0.8)

    def test_facets_present(self):
        r = score_pair(self.alice, self.alice_twin)
        self.assertIn("artist", r["facets"])
        self.assertIn("genre", r["facets"])
        self.assertIn("lyric", r["facets"])

    def test_weights_sum_to_one(self):
        r = score_pair(self.alice, self.alice_twin)
        self.assertAlmostEqual(sum(r["weights"].values()), 1.0, places=5)

    def test_disjoint_scores_lower(self):
        same = score_pair(self.alice, self.alice_twin)["similarity"]
        diff = score_pair(self.alice, self.bob)["similarity"]
        self.assertLess(diff, same)
        self.assertLess(diff, 0.5)

    def test_lyric_facet_dropped_when_missing(self):
        no_lyrics = make_profile("nl", ["a"], {"indie": 1.0}, [])
        r = score_pair(self.alice, no_lyrics)
        self.assertNotIn("lyric", r["facets"])
        self.assertIn("artist", r["facets"])

    def test_calibration_changes_to_percentile(self):
        params = EngineParams(calibrator=PercentileCalibrator.fit([0.0, 0.1, 0.2, 0.3]))
        r = score_pair(self.alice, self.bob, params)
        # raw blended is low but above 0.3 sample max? percentile should be well-defined in [0,1]
        self.assertGreaterEqual(r["similarity"], 0.0)
        self.assertLessEqual(r["similarity"], 1.0)
        self.assertNotEqual(r["similarity"], r["blended"])


if __name__ == "__main__":
    unittest.main()
