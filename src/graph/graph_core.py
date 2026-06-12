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


def _top_genres(profile, k=8):
    """Top-k of the normalized genre distribution — the node's compact taste summary.

    Shipped on every node so the UI can render comparative imagery (you-vs-friend genre
    histograms) without a second request. [[genre, weight], ...], weights sum ≤ 1.
    """
    items = sorted(profile.genre_dist.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
    return [[g, round(float(w), 4)] for g, w in items]


def _top_artist_names(record, k=5):
    """Top-k artist display names from the profile snapshot (best-effort; may be [])."""
    top = (record or {}).get('topArtists') or {}
    if not isinstance(top, dict):
        return []
    for rng in ('medium_term', 'long_term', 'short_term'):
        names = [a.get('name') for a in (top.get(rng) or []) if isinstance(a, dict) and a.get('name')]
        if names:
            return [str(n) for n in names[:k]]
    return []


def _pair_key(uid_a, uid_b, rec_a, rec_b):
    """Order-independent cache key for a scored pair, versioned by profile timestamps.

    A profile refresh bumps `lastUpdated` / `lastLyricUpdate`, which rotates the key — so a
    warm Lambda container can memoize WMD-heavy `score_pair` results across requests without
    ever serving a stale score. Archetype records carry no timestamps and never change.
    """
    va = (uid_a, str(rec_a.get('lastUpdated', '')), str(rec_a.get('lastLyricUpdate', '')))
    vb = (uid_b, str(rec_b.get('lastUpdated', '')), str(rec_b.get('lastLyricUpdate', '')))
    return tuple(sorted((va, vb)))


def build_graph(user_id, all_user_ids, records_by_id, users_by_id, mode='taste',
                engine_params=None, score_cache=None):
    """
    Pure graph builder — no I/O.

    Args:
        user_id: the requesting user (flagged isCurrentUser).
        all_user_ids: every node id (self + friends), in node order.
        records_by_id: userId -> MusicProfiles record (raw dict).
        users_by_id: userId -> Users record (for display name / spotify id).
        mode: 'taste' (calibrated blend) or 'lyric' (lyric facet alone).
        engine_params: fitted EngineParams (defaults applied if None).
        score_cache: optional dict for memoizing score_pair results across calls (the
            handler passes a container-lifetime dict; keys are profile-versioned).

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
        # Archetype landmarks are id-prefixed `archetype:`; the UI renders them distinctly and
        # never offers friend actions on them. Everything else is a real person.
        is_arch = isinstance(uid, str) and uid.startswith('archetype:')
        nodes.append({
            'userId': uid,
            'displayName': user_rec.get('displayName', ''),
            'spotifyId': user_rec.get('spotifyId', ''),
            'isCurrentUser': uid == user_id,
            'hasProfile': record is not None,
            'lyricStatus': record.get('lyricStatus') if record else None,
            'kind': 'archetype' if is_arch else 'user',
            'description': user_rec.get('description', '') if is_arch else '',
            # compact taste summary for the comparative-imagery panels (V2/V3)
            'topGenres': _top_genres(taste_by_id[uid]) if uid in taste_by_id else [],
            'topArtists': _top_artist_names(record),
        })

    edges = []
    for i, uid_a in enumerate(all_user_ids):
        for uid_b in all_user_ids[i + 1:]:
            pa = taste_by_id.get(uid_a)
            pb = taste_by_id.get(uid_b)
            if pa is None or pb is None:
                continue

            result = None
            key = None
            if score_cache is not None:
                key = _pair_key(uid_a, uid_b, records_by_id[uid_a], records_by_id[uid_b])
                result = score_cache.get(key)
            if result is None:
                result = score_pair(pa, pb, engine_params)
                if score_cache is not None:
                    score_cache[key] = result
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

    # Tell the UI whether `similarity` is already an absolute, calibrated percentile. When false
    # (no calibrator fitted yet) the ego-graph spreads scores relative to the field instead of
    # claiming absolute %s. Shipping a fitted calibrator flips this to true with no UI change.
    calibrated = bool(engine_params.calibrator and not engine_params.calibrator.is_empty)

    return {'mode': mode, 'nodes': nodes, 'edges': edges, 'calibrated': calibrated}
