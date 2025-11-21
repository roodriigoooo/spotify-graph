"""
Join queue endpoint.
"""
import os
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from boto3.dynamodb.conditions import Key

from common.dynamodb_utils import get_item, put_item, query_items
from common.response_utils import (
    success_response,
    bad_request_response,
    not_found_response,
    forbidden_response,
    server_error_response
)
from common.logger import log_info, log_error


SHARED_QUEUES_TABLE = os.environ.get('SHARED_QUEUES_TABLE')
QUEUE_MEMBERS_TABLE = os.environ.get('QUEUE_MEMBERS_TABLE')
FRIENDS_TABLE = os.environ.get('FRIENDS_TABLE')


def handler(event, context):
    """
    Allow a user to join an existing queue (one queue per user).
    """
    try:
        user_id = event['requestContext']['authorizer']['userId']
        queue_id = event['pathParameters'].get('queueId') if event.get('pathParameters') else None

        if not queue_id:
            return bad_request_response('Queue ID is required')

        log_info('Join queue request', queue_id=queue_id, user_id=user_id)

        queue = get_item(SHARED_QUEUES_TABLE, {'queueId': queue_id})
        if not queue:
            return not_found_response('Queue not found')

        owner_id = queue.get('ownerId')

        if owner_id == user_id:
            return success_response(
                {
                    'queueId': queue_id,
                    'role': 'owner',
                    'name': queue.get('name')
                },
                'You already own this queue.'
            )

        # Prevent joining multiple queues
        existing_memberships = query_items(
            QUEUE_MEMBERS_TABLE,
            Key('userId').eq(user_id),
            index_name='UserQueuesIndex',
            limit=1
        )
        if existing_memberships:
            return bad_request_response('You are already participating in another queue. Leave it before joining a new one.')

        membership = get_item(QUEUE_MEMBERS_TABLE, {'queueId': queue_id, 'userId': user_id})
        if membership:
            return success_response({'queueId': queue_id, 'role': membership.get('role', 'member')}, 'You are already in this queue.')

        if not queue.get('isPublic', False) and not _are_friends(owner_id, user_id):
            return forbidden_response('Only friends of the owner can join this private queue.')

        timestamp = int(time.time())
        put_item(
            QUEUE_MEMBERS_TABLE,
            {
                'queueId': queue_id,
                'userId': user_id,
                'role': 'member',
                'joinedAt': timestamp
            }
        )

        log_info('User joined queue', queue_id=queue_id, user_id=user_id)

        return success_response(
            {
                'queueId': queue_id,
                'role': 'member',
                'joinedAt': timestamp,
                'name': queue.get('name'),
                'description': queue.get('description', ''),
                'ownerId': owner_id
            },
            'Joined queue successfully'
        )

    except KeyError as error:
        log_error('Missing required field when joining queue', error=error)
        return server_error_response('Invalid request context')
    except Exception as error:
        log_error('Error joining queue', error=error)
        return server_error_response('Failed to join queue')


def _are_friends(user_a: str, user_b: str) -> bool:
    """
    Check if two users are friends in either direction.
    """
    if not user_a or not user_b:
        return False

    friendship = get_item(FRIENDS_TABLE, {'userId': user_a, 'friendId': user_b})
    if friendship:
        return True

    friendship = get_item(FRIENDS_TABLE, {'userId': user_b, 'friendId': user_a})
    return friendship is not None



