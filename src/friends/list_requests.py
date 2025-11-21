"""
List pending friend requests endpoint.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import query_items, batch_get_items
from common.response_utils import success_response, server_error_response
from common.logger import log_info, log_error
from boto3.dynamodb.conditions import Key, Attr


FRIEND_REQUESTS_TABLE = os.environ.get('FRIEND_REQUESTS_TABLE')
USERS_TABLE = os.environ.get('USERS_TABLE')


def handler(event, context):
    """
    List pending friend requests received by the current user.
    
    Returns:
        List of pending requests with sender details
    """
    try:
        # Extract user ID from authorizer context
        user_id = event['requestContext']['authorizer']['userId']
        
        log_info('List friend requests', user_id=user_id)
        
        # Query incoming requests for this user
        incoming = query_items(
            FRIEND_REQUESTS_TABLE,
            Key('toUserId').eq(user_id),
            index_name='ToUserIndex',
            filter_expression=Attr('status').eq('pending')
        )

        # Query outgoing requests created by this user
        outgoing = query_items(
            FRIEND_REQUESTS_TABLE,
            Key('fromUserId').eq(user_id),
            index_name='FromUserIndex',
            filter_expression=Attr('status').eq('pending')
        )

        if not incoming and not outgoing:
            return success_response({'incoming': [], 'outgoing': []})

        # Collect user IDs we need to hydrate
        related_user_ids = set()
        related_user_ids.update(r['fromUserId'] for r in incoming)
        related_user_ids.update(r['toUserId'] for r in outgoing)

        user_map = {}
        if related_user_ids:
            user_keys = [{'userId': uid} for uid in related_user_ids]
            users = batch_get_items(USERS_TABLE, user_keys)
            user_map = {u['userId']: u for u in users}

        incoming_data = []
        for req in incoming:
            sender = user_map.get(req['fromUserId'], {})
            incoming_data.append({
                'requestId': req['requestId'],
                'fromUserId': req['fromUserId'],
                'fromSpotifyId': sender.get('spotifyId'),
                'fromDisplayName': sender.get('displayName'),
                'createdAt': req.get('createdAt')
            })

        outgoing_data = []
        for req in outgoing:
            recipient = user_map.get(req['toUserId'], {})
            outgoing_data.append({
                'requestId': req['requestId'],
                'toUserId': req['toUserId'],
                'toSpotifyId': recipient.get('spotifyId'),
                'toDisplayName': recipient.get('displayName'),
                'createdAt': req.get('createdAt')
            })

        return success_response({
            'incoming': incoming_data,
            'outgoing': outgoing_data
        })
        
    except KeyError as e:
        log_error('Missing required field', error=e)
        return server_error_response('Invalid request context')
    except Exception as e:
        log_error('Error listing friend requests', error=e)
        return server_error_response('Failed to retrieve friend requests')




