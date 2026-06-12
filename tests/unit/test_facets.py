"""
Facet tests — focused on the genre facet's family-aware matching.

The fix that matters: genre similarity must not collapse to 0 just because two listeners use
different-but-related Spotify tags. We compare genre *vocabularies* (full tags + word tokens),
so adjacent styles draw close while unrelated ones stay apart. This is what stops a real user
from landing equidistant from every archetype.
"""
import unittest

import _path  # noqa: F401
from taste.facets import UserTasteProfile, genre_facet


def _p(genres):
    return UserTasteProfile(user_id="x", genre_dist=genres)


class TestGenreFacet(unittest.TestCase):
    def test_identical_tags_score_one(self):
        a = _p({"indie rock": 1.0})
        self.assertAlmostEqual(genre_facet(a, a), 1.0, places=6)

    def test_related_tags_partially_match(self):
        # "art rock" and "indie rock" share the `rock` token -> nonzero, but below identical.
        s = genre_facet(_p({"art rock": 1.0}), _p({"indie rock": 1.0}))
        self.assertGreater(s, 0.0)
        self.assertLess(s, 1.0)

    def test_compound_meets_umbrella(self):
        # a "latin pop" listener should register against a "pop" archetype via the `pop` token.
        self.assertGreater(genre_facet(_p({"latin pop": 1.0}), _p({"pop": 1.0})), 0.0)

    def test_unrelated_families_stay_zero(self):
        # no shared full tag and no shared token -> genuinely 0 (we don't fabricate closeness).
        self.assertEqual(genre_facet(_p({"reggaeton": 1.0}), _p({"black metal": 1.0})), 0.0)

    def test_related_beats_unrelated(self):
        me = _p({"indie rock": 1.0, "art rock": 0.5})
        near = _p({"indie pop": 1.0, "indie rock": 0.5})   # shares indie/rock vocabulary
        far = _p({"deep house": 1.0, "techno": 0.5})       # disjoint
        self.assertGreater(genre_facet(me, near), genre_facet(me, far))

    def test_empty_is_zero(self):
        self.assertEqual(genre_facet(_p({}), _p({"pop": 1.0})), 0.0)


if __name__ == "__main__":
    unittest.main()
