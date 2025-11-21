"""
Return presence graph data for the current user and their friends.
"""
import os
import sys
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from boto3.dynamodb.conditions import Key

from common.dynamodb_utils import query_items, batch_get_items
from common.response_utils import success_response, server_error_response
from common.logger import log_info, log_error


USERS_TABLE = os.environ.get('USERS_TABLE')
FRIENDS_TABLE = os.environ.get('FRIENDS_TABLE')
PRESENCE_TABLE = os.environ.get('PRESENCE_TABLE')


def _to_int(value):
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return value


def handler(event, context):
    """
    Build a lightweight presence network for the requesting user.
    """
    try:
        user_id = event['requestContext']['authorizer']['userId']

        log_info('Presence network request', user_id=user_id)

        friendships = query_items(
            FRIENDS_TABLE,
            Key('userId').eq(user_id)
        )
        friend_ids = [f['friendId'] for f in friendships if f.get('friendId')]

        network_ids = [user_id] + [fid for fid in friend_ids if fid != user_id]

        if not network_ids:
            return success_response({'nodes': []})

        user_profiles = batch_get_items(
            USERS_TABLE,
            [{'userId': uid} for uid in network_ids]
        )
        presence_items = batch_get_items(
            PRESENCE_TABLE,
            [{'userId': uid} for uid in network_ids]
        )

        profile_map = {profile['userId']: profile for profile in user_profiles}
        presence_map = {presence['userId']: presence for presence in presence_items}

        nodes = []
        for uid in network_ids:
            profile = profile_map.get(uid, {})
            presence = presence_map.get(uid, {})

            nodes.append({
                'userId': uid,
                'displayName': profile.get('displayName') or profile.get('spotifyId') or 'Friend',
                'spotifyId': profile.get('spotifyId'),
                'visibility': profile.get('visibility', 'friends'),
                'presence': {
                    'isPlaying': bool(presence.get('isPlaying', False)),
                    'trackName': presence.get('trackName'),
                    'artistName': presence.get('artistName'),
                    'albumName': presence.get('albumName'),
                    'albumImageUrl': presence.get('albumImageUrl'),
                    'updatedAt': _to_int(presence.get('updatedAt', 0))
                }
            })

        return success_response({'nodes': nodes})

    except KeyError as error:
        log_error('Invalid request context for presence network', error=error)
        return server_error_response('Invalid request context')
    except Exception as error:
        log_error('Error building presence network', error=error)
        return server_error_response('Failed to load presence network')


