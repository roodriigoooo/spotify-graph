"""
GET /graph?mode=taste|lyric  (default: taste)

Returns nodes and edges for the similarity graph. Edges carry the v2 engine's full,
honest breakdown: a calibrated similarity plus the per-facet contributions and weights
that explain it (the comparative-imagery panel renders straight off this).

  mode=taste  -> edge.similarity is the calibrated, blended score over all facets
  mode=lyric  -> edge.similarity is the lyric-theme facet alone (pairs without lyric
                 data are dropped, matching the old behaviour)

Either way every edge also includes `facets`, `weights`, and the raw `blended` score, so
the UI never has to ask the server a second question to explain a match. The thinking lives
in `graph_core` (pure, I/O-free, unit-tested); this module is just the fetch-and-respond
shell.
"""
import os

from common.dynamodb_utils import query_items, batch_get_items
from common.response_utils import success_response, error_response
from common.logger import log_info, log_error
from boto3.dynamodb.conditions import Key

from graph_core import build_graph, load_params
from archetypes import archetype_profile_records, archetype_user_records

USERS_TABLE = os.environ.get('USERS_TABLE')
FRIENDS_TABLE = os.environ.get('FRIENDS_TABLE')
MUSIC_PROFILES_TABLE = os.environ.get('MUSIC_PROFILES_TABLE')

# Container-lifetime memo of score_pair results. WMD/Sinkhorn over per-track embeddings is
# the expensive part of a request (O(n²) pairs, each ~40×40 transport problem in pure
# Python); profiles change rarely, requests repeat often. Keys are profile-versioned
# (see graph_core._pair_key) so a refresh invalidates itself. ENGINE_PARAMS is env-fixed
# per container, so it can't go stale within one cache lifetime.
_SCORE_CACHE = {}
_SCORE_CACHE_MAX = 4096

def handler(event, context):
    user_id = event.get('requestContext', {}).get('authorizer', {}).get('userId')
    if not user_id:
        return error_response(401, 'Unauthorized')

    params = event.get('queryStringParameters') or {}
    mode = params.get('mode', 'taste')
    if mode not in ('taste', 'lyric'):
        return error_response(400, "mode must be 'taste' or 'lyric'")

    try:
        engine_params = load_params()

        # Friends -> the set of users in this graph
        friend_records = query_items(FRIENDS_TABLE, key_condition=Key('userId').eq(user_id))
        friend_ids = [r['friendId'] for r in friend_records]
        all_user_ids = [user_id] + friend_ids

        # Batch-fetch profiles + user records
        keys = [{'userId': uid} for uid in all_user_ids]
        raw_profiles = batch_get_items(MUSIC_PROFILES_TABLE, keys) if keys else []
        raw_users = batch_get_items(USERS_TABLE, keys) if keys else []

        records_by_id = {p['userId']: p for p in raw_profiles}
        users_by_id = {u['userId']: u for u in raw_users}

        # Archetype landmarks: persistent, genre-defined personas added to the graph so it is
        # meaningful even with zero friends (you get plotted against them). Additive only — they
        # are never persisted, so the friend mechanism never sees them. Opt out with ?archetypes=0.
        # Only in taste mode: archetypes have no lyric-theme data yet, so in lyric mode they'd be
        # edgeless floaters — omit them until phase 2 gives them real theme embeddings.
        if mode == 'taste' and params.get('archetypes', '1') != '0':
            for aid, rec in archetype_profile_records().items():
                records_by_id[aid] = rec
                all_user_ids.append(aid)
            for aid, urec in archetype_user_records().items():
                users_by_id[aid] = urec

        if len(_SCORE_CACHE) > _SCORE_CACHE_MAX:
            _SCORE_CACHE.clear()
        graph = build_graph(user_id, all_user_ids, records_by_id, users_by_id,
                            mode=mode, engine_params=engine_params,
                            score_cache=_SCORE_CACHE)

        log_info('Graph computed', user_id=user_id, mode=mode,
                 nodes=len(graph['nodes']), edges=len(graph['edges']))
        return success_response(graph)

    except Exception as e:
        log_error('Error computing graph', user_id=user_id, error=e)
        return error_response(500, 'Internal server error')
