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

USERS_TABLE = os.environ.get('USERS_TABLE')
FRIENDS_TABLE = os.environ.get('FRIENDS_TABLE')
MUSIC_PROFILES_TABLE = os.environ.get('MUSIC_PROFILES_TABLE')

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

        graph = build_graph(user_id, all_user_ids, records_by_id, users_by_id,
                            mode=mode, engine_params=engine_params)

        log_info('Graph computed', user_id=user_id, mode=mode,
                 nodes=len(graph['nodes']), edges=len(graph['edges']))
        return success_response(graph)

    except Exception as e:
        log_error('Error computing graph', user_id=user_id, error=e)
        return error_response(500, 'Internal server error')
