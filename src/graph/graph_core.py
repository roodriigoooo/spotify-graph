"""
graph_core — the pure, I/O-free heart of GET /graph.

Kept separate from `get_graph.py` so it imports nothing heavy (no boto3, no DynamoDB) and is
directly unit-testable: feed it plain records, get back nodes + edges. The handler does the
fetching; this does the thinking.
"""
import json
import os

from common.logger import log_error
from common.taste import build_profile, score_pair, EngineParams


def load_params() -> EngineParams:
    """
    Load the offline-fitted engine params (whitening / calibration / facet weights).

    Serialized by `taste.fit`; injected via the ENGINE_PARAMS env var (a JSON blob). Absent
    that, sensible defaults apply: identity whitening, uniform facet weights, no calibration
    (raw scores pass through). This is the one knob that turns the engine from "works" to
    "calibrated".
    """
    blob = os.environ.get('ENGINE_PARAMS')
    if blob:
        try:
            return EngineParams.from_dict(json.loads(blob))
        except (ValueError, TypeError) as e:
            log_error('Bad ENGINE_PARAMS, using defaults', error=e)
    return EngineParams()


def build_graph(user_id, all_user_ids, records_by_id, users_by_id, mode='taste',
                engine_params=None):
    """
    Pure graph builder — no I/O.

    Args:
        user_id: the requesting user (flagged isCurrentUser).
        all_user_ids: every node id (self + friends), in node order.
        records_by_id: userId -> MusicProfiles record (raw dict).
        users_by_id: userId -> Users record (for display name / spotify id).
        mode: 'taste' (calibrated blend) or 'lyric' (lyric facet alone).
        engine_params: fitted EngineParams (defaults applied if None).

    Returns:
        {'mode', 'nodes', 'edges'} — every edge carries similarity + the per-facet
        breakdown and weights that explain it.
    """
    engine_params = engine_params or EngineParams()

    taste_by_id = {
        uid: build_profile(rec, params=engine_params)
        for uid, rec in records_by_id.items()
    }

    nodes = []
    for uid in all_user_ids:
        user_rec = users_by_id.get(uid, {})
        record = records_by_id.get(uid)
        nodes.append({
            'userId': uid,
            'displayName': user_rec.get('displayName', ''),
            'spotifyId': user_rec.get('spotifyId', ''),
            'isCurrentUser': uid == user_id,
            'hasProfile': record is not None,
            'lyricStatus': record.get('lyricStatus') if record else None,
        })

    edges = []
    for i, uid_a in enumerate(all_user_ids):
        for uid_b in all_user_ids[i + 1:]:
            pa = taste_by_id.get(uid_a)
            pb = taste_by_id.get(uid_b)
            if pa is None or pb is None:
                continue

            result = score_pair(pa, pb, engine_params)
            facets = result['facets']

            if mode == 'lyric':
                if 'lyric' not in facets:
                    continue
                similarity = facets['lyric']
            else:
                similarity = result['similarity']

            edges.append({
                'source': uid_a,
                'target': uid_b,
                'similarity': round(similarity, 4),
                'blended': round(result['blended'], 4),
                'facets': {k: round(v, 4) for k, v in facets.items()},
                'weights': {k: round(v, 4) for k, v in result['weights'].items()},
            })

    return {'mode': mode, 'nodes': nodes, 'edges': edges}
