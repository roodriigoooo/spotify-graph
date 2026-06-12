"""
graph_core tests — the pure GET /graph logic, no DynamoDB.

Covers node assembly, the per-facet edge breakdown the v2 UI needs, the taste/lyric mode
split, graceful handling of profile-less users, and ENGINE_PARAMS loading.
"""
import os
import sys
import unittest
from decimal import Decimal

# graph_core imports `common.*` (from the layer) and lives in src/graph. Put the layer dir
# (for the `common` package) and src/graph (for graph_core itself) on the path — mirrors how
# the Lambda bundle resolves them (layer at /opt/python, handler co-located).
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for _p in (os.path.join(_ROOT, "layers", "common"), os.path.join(_ROOT, "src", "graph")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from graph_core import build_graph, load_params  # noqa: E402
from common.taste import EngineParams  # noqa: E402
from common.taste.calibration import PercentileCalibrator  # noqa: E402
import archetypes  # noqa: E402


def _record(uid, genre, emb=None):
    rec = {
        "userId": uid,
        "topArtists": {"long_term": [{"id": "a_" + uid, "name": "Artist " + uid, "genres": [genre]}]},
        "genreVector": {genre: Decimal("1.0")},
        "lyricStatus": "ready" if emb else "pending",
        "lastUpdated": Decimal("1000"),
    }
    if emb:
        rec["trackEmbeddings"] = emb
    return rec


class TestBuildGraph(unittest.TestCase):
    def setUp(self):
        self.users = {
            "me": {"userId": "me", "displayName": "Me", "spotifyId": "sp_me"},
            "f1": {"userId": "f1", "displayName": "Friend One", "spotifyId": "sp_f1"},
            "f2": {"userId": "f2", "displayName": "Friend Two", "spotifyId": "sp_f2"},
        }

    def test_nodes_and_edges_shape(self):
        records = {
            "me": _record("me", "indie folk", [[1.0, 0.0, 0.0]]),
            "f1": _record("f1", "indie folk", [[0.9, 0.1, 0.0]]),
            "f2": _record("f2", "techno", [[0.0, 0.0, 1.0]]),
        }
        g = build_graph("me", ["me", "f1", "f2"], records, self.users, mode="taste")
        self.assertEqual(g["mode"], "taste")
        self.assertEqual(len(g["nodes"]), 3)
        me = next(n for n in g["nodes"] if n["userId"] == "me")
        self.assertTrue(me["isCurrentUser"])
        self.assertEqual(me["displayName"], "Me")
        # 3 users -> 3 unique pairs
        self.assertEqual(len(g["edges"]), 3)
        for e in g["edges"]:
            self.assertIn("similarity", e)
            self.assertIn("facets", e)
            self.assertIn("weights", e)
            self.assertIn("blended", e)
            self.assertTrue(0.0 <= e["similarity"] <= 1.0)

    def test_calibrated_flag(self):
        records = {
            "me": _record("me", "indie folk", [[1.0, 0.0, 0.0]]),
            "f1": _record("f1", "indie folk", [[0.9, 0.1, 0.0]]),
        }
        # default (empty calibrator) -> not calibrated; UI spreads scores relative to the field
        g = build_graph("me", ["me", "f1"], records, self.users, mode="taste")
        self.assertFalse(g["calibrated"])
        # a fitted calibrator -> calibrated; UI can show absolute %s
        params = EngineParams(calibrator=PercentileCalibrator.fit([0.1, 0.3, 0.5, 0.7, 0.9]))
        g2 = build_graph("me", ["me", "f1"], records, self.users, mode="taste", engine_params=params)
        self.assertTrue(g2["calibrated"])

    def test_shared_genre_scores_higher(self):
        records = {
            "me": _record("me", "indie folk", [[1.0, 0.0, 0.0]]),
            "f1": _record("f1", "indie folk", [[0.95, 0.05, 0.0]]),
            "f2": _record("f2", "death metal", [[0.0, 0.0, 1.0]]),
        }
        g = build_graph("me", ["me", "f1", "f2"], records, self.users, mode="taste")
        by_pair = {(e["source"], e["target"]): e["similarity"] for e in g["edges"]}
        self.assertGreater(by_pair[("me", "f1")], by_pair[("me", "f2")])

    def test_lyric_mode_drops_pairs_without_lyric(self):
        records = {
            "me": _record("me", "indie folk", [[1.0, 0.0, 0.0]]),
            "f1": _record("f1", "indie folk"),  # no embeddings -> no lyric facet
        }
        g = build_graph("me", ["me", "f1"], records, self.users, mode="lyric")
        self.assertEqual(len(g["edges"]), 0)

    def test_lyric_mode_keeps_pairs_with_lyric(self):
        records = {
            "me": _record("me", "indie folk", [[1.0, 0.0, 0.0]]),
            "f1": _record("f1", "indie folk", [[0.8, 0.2, 0.0]]),
        }
        g = build_graph("me", ["me", "f1"], records, self.users, mode="lyric")
        self.assertEqual(len(g["edges"]), 1)
        self.assertIn("lyric", g["edges"][0]["facets"])

    def test_profileless_user_yields_node_no_edges(self):
        records = {"me": _record("me", "indie folk", [[1.0, 0.0, 0.0]])}
        g = build_graph("me", ["me", "f1"], records, self.users, mode="taste")
        self.assertEqual(len(g["nodes"]), 2)
        f1 = next(n for n in g["nodes"] if n["userId"] == "f1")
        self.assertFalse(f1["hasProfile"])
        self.assertEqual(len(g["edges"]), 0)  # f1 has no profile -> pair skipped


class TestNodeSummaries(unittest.TestCase):
    """Per-node taste summaries — the data the comparative-imagery panels render from."""

    def setUp(self):
        self.users = {
            "me": {"userId": "me", "displayName": "Me", "spotifyId": "sp_me"},
            "f1": {"userId": "f1", "displayName": "Friend One", "spotifyId": "sp_f1"},
        }

    def test_nodes_carry_top_genres_and_artists(self):
        records = {
            "me": _record("me", "indie folk"),
            "f1": _record("f1", "techno"),
        }
        g = build_graph("me", ["me", "f1"], records, self.users, mode="taste")
        me = next(n for n in g["nodes"] if n["userId"] == "me")
        self.assertEqual(me["topGenres"], [["indie folk", 1.0]])
        self.assertEqual(me["topArtists"], ["Artist me"])

    def test_profileless_node_has_empty_summaries(self):
        records = {"me": _record("me", "indie folk")}
        g = build_graph("me", ["me", "f1"], records, self.users, mode="taste")
        f1 = next(n for n in g["nodes"] if n["userId"] == "f1")
        self.assertEqual(f1["topGenres"], [])
        self.assertEqual(f1["topArtists"], [])

    def test_top_genres_sorted_and_capped(self):
        rec = _record("me", "indie folk")
        rec["genreVector"] = {f"g{i:02d}": Decimal(str(0.01 * (i + 1))) for i in range(12)}
        g = build_graph("me", ["me"], {"me": rec}, self.users, mode="taste")
        me = g["nodes"][0]
        self.assertEqual(len(me["topGenres"]), 8)
        weights = [w for _, w in me["topGenres"]]
        self.assertEqual(weights, sorted(weights, reverse=True))

    def test_archetype_nodes_carry_genre_summary(self):
        records = {"me": _record("me", "indie rock")}
        users = dict(self.users)
        all_ids = ["me"]
        for aid, rec in archetypes.archetype_profile_records().items():
            records[aid] = rec
            all_ids.append(aid)
        for aid, urec in archetypes.archetype_user_records().items():
            users[aid] = urec
        g = build_graph("me", all_ids, records, users, mode="taste")
        for n in g["nodes"]:
            if n["kind"] == "archetype":
                self.assertTrue(n["topGenres"])  # genre-defined, so always present
                self.assertEqual(n["topArtists"], [])


class TestScoreCache(unittest.TestCase):
    """The warm-container memo: hit on identical profiles, rotate on profile refresh."""

    def setUp(self):
        self.users = {
            "me": {"userId": "me", "displayName": "Me", "spotifyId": "sp_me"},
            "f1": {"userId": "f1", "displayName": "Friend One", "spotifyId": "sp_f1"},
        }
        self.records = {
            "me": _record("me", "indie folk", [[1.0, 0.0, 0.0]]),
            "f1": _record("f1", "indie folk", [[0.9, 0.1, 0.0]]),
        }

    def test_cache_populated_and_reused(self):
        cache = {}
        g1 = build_graph("me", ["me", "f1"], self.records, self.users, score_cache=cache)
        self.assertEqual(len(cache), 1)
        # poison the cached result; a second build must serve the poisoned value (proof of reuse)
        key = next(iter(cache))
        cache[key] = dict(cache[key], similarity=0.123, blended=0.123)
        g2 = build_graph("me", ["me", "f1"], self.records, self.users, score_cache=cache)
        self.assertEqual(g2["edges"][0]["similarity"], 0.123)
        self.assertNotEqual(g1["edges"][0]["similarity"], g2["edges"][0]["similarity"])

    def test_profile_refresh_rotates_key(self):
        cache = {}
        build_graph("me", ["me", "f1"], self.records, self.users, score_cache=cache)
        refreshed = dict(self.records)
        refreshed["f1"] = dict(refreshed["f1"], lastUpdated=Decimal("2000"))
        build_graph("me", ["me", "f1"], refreshed, self.users, score_cache=cache)
        self.assertEqual(len(cache), 2)  # old + new version keys

    def test_results_identical_with_and_without_cache(self):
        g_plain = build_graph("me", ["me", "f1"], self.records, self.users)
        g_cached = build_graph("me", ["me", "f1"], self.records, self.users, score_cache={})
        self.assertEqual(g_plain["edges"], g_cached["edges"])


class TestArchetypes(unittest.TestCase):
    """Archetype landmarks: genre-defined, additive, honestly scored, friend-mechanism-safe."""

    def _inject(self, all_ids, records, users):
        """Mirror the handler's merge so we test what /graph actually builds."""
        for aid, rec in archetypes.archetype_profile_records().items():
            records[aid] = rec
            all_ids.append(aid)
        for aid, urec in archetypes.archetype_user_records().items():
            users[aid] = urec

    def test_records_are_genre_only(self):
        # No artistWeights / topArtists / embeddings -> artist + lyric facets must self-drop,
        # so an archetype is never penalised by a misleading 0% on a signal it doesn't express.
        for rec in archetypes.archetype_profile_records().values():
            self.assertIn("genreVector", rec)
            self.assertNotIn("artistWeights", rec)
            self.assertNotIn("topArtists", rec)
            self.assertNotIn("trackEmbeddings", rec)

    def test_injected_nodes_tagged_and_described(self):
        records = {"me": _record("me", "indie folk", [[1.0, 0.0, 0.0]])}
        users = {"me": {"userId": "me", "displayName": "Me", "spotifyId": "sp_me"}}
        all_ids = ["me"]
        self._inject(all_ids, records, users)

        g = build_graph("me", all_ids, records, users, mode="taste")
        arch_nodes = [n for n in g["nodes"] if n["kind"] == "archetype"]
        self.assertEqual(len(arch_nodes), len(archetypes.archetype_ids()))
        for n in arch_nodes:
            self.assertTrue(n["userId"].startswith("archetype:"))
            self.assertFalse(n["isCurrentUser"])
            self.assertTrue(n["description"])  # node card has something to show

        me = next(n for n in g["nodes"] if n["userId"] == "me")
        self.assertEqual(me["kind"], "user")
        self.assertEqual(me["description"], "")

    def test_edge_to_archetype_is_genre_only(self):
        # An indie-folk listener vs the indie archetype: an edge exists, scored on genre alone
        # (artist + lyric dropped) — the breakdown panel will show just "genres".
        records = {"me": _record("me", "indie rock", [[1.0, 0.0, 0.0]])}
        users = {"me": {"userId": "me", "displayName": "Me", "spotifyId": "sp_me"}}
        all_ids = ["me"]
        self._inject(all_ids, records, users)

        g = build_graph("me", all_ids, records, users, mode="taste")
        indie = archetypes.archetype_id("indie")
        edge = next((e for e in g["edges"]
                     if indie in (e["source"], e["target"]) and "me" in (e["source"], e["target"])), None)
        self.assertIsNotNone(edge)
        self.assertIn("genre", edge["facets"])
        self.assertNotIn("artist", edge["facets"])
        self.assertNotIn("lyric", edge["facets"])
        self.assertGreater(edge["similarity"], 0.0)

    def test_genre_match_ranks_above_mismatch(self):
        # The indie listener should sit closer to the indie archetype than to the metal one.
        records = {"me": _record("me", "indie rock", [[1.0, 0.0, 0.0]])}
        users = {"me": {"userId": "me", "displayName": "Me", "spotifyId": "sp_me"}}
        all_ids = ["me"]
        self._inject(all_ids, records, users)

        g = build_graph("me", all_ids, records, users, mode="taste")
        sims = {}
        for e in g["edges"]:
            pair = (e["source"], e["target"])
            if "me" in pair:
                other = pair[0] if pair[1] == "me" else pair[1]
                sims[other] = e["similarity"]
        self.assertGreater(sims[archetypes.archetype_id("indie")], sims[archetypes.archetype_id("metal")])


class TestLoadParams(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("ENGINE_PARAMS", None)

    def test_default_when_absent(self):
        os.environ.pop("ENGINE_PARAMS", None)
        p = load_params()
        self.assertIsInstance(p, EngineParams)

    def test_parses_env_blob(self):
        os.environ["ENGINE_PARAMS"] = '{"half_life_days": 14.0, "lyric_mode": "gaussian"}'
        p = load_params()
        self.assertEqual(p.half_life_days, 14.0)
        self.assertEqual(p.lyric_mode, "gaussian")

    def test_bad_blob_falls_back(self):
        os.environ["ENGINE_PARAMS"] = "{not valid json"
        p = load_params()  # should not raise
        self.assertIsInstance(p, EngineParams)


if __name__ == "__main__":
    unittest.main()
