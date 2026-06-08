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


def _record(uid, genre, emb=None):
    rec = {
        "userId": uid,
        "topArtists": {"long_term": [{"id": "a_" + uid, "genres": [genre]}]},
        "genreVector": {genre: Decimal("1.0")},
        "lyricStatus": "ready" if emb else "pending",
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
