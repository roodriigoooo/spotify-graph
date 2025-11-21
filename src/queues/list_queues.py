"""
List queues for the current user.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from boto3.dynamodb.conditions import Key

from common.dynamodb_utils import query_items, batch_get_items
from common.response_utils import success_response, server_error_response
from common.logger import log_info, log_error


SHARED_QUEUES_TABLE = os.environ.get('SHARED_QUEUES_TABLE')
QUEUE_MEMBERS_TABLE = os.environ.get('QUEUE_MEMBERS_TABLE')


def handler(event, context):
    """
    Return the queues the current user is participating in.
    """
    try:
        user_id = event['requestContext']['authorizer']['userId']

        log_info('List queues request', user_id=user_id)

        memberships = query_items(
            QUEUE_MEMBERS_TABLE,
            Key('userId').eq(user_id),
            index_name='UserQueuesIndex'
        )

        if not memberships:
            return success_response({'queues': []})

        queue_ids = [m['queueId'] for m in memberships]
        queue_keys = [{'queueId': queue_id} for queue_id in queue_ids]
        queues = batch_get_items(SHARED_QUEUES_TABLE, queue_keys)
        queue_map = {queue['queueId']: queue for queue in queues}

        enriched = []
        for membership in memberships:
            queue_id = membership['queueId']
            queue = queue_map.get(queue_id)
            if not queue:
                continue

            # Count members to show liveliness (only a handful per queue)
            members = query_items(
                QUEUE_MEMBERS_TABLE,
                Key('queueId').eq(queue_id)
            )

            enriched.append({
                'queueId': queue_id,
                'name': queue.get('name'),
                'description': queue.get('description', ''),
                'ownerId': queue.get('ownerId'),
                'isPublic': queue.get('isPublic', False),
                'memberRole': membership.get('role', 'member'),
                'joinedAt': membership.get('joinedAt'),
                'updatedAt': queue.get('updatedAt'),
                'memberCount': len(members),
                'members': [
                    {
                        'userId': m['userId'],
                        'role': m.get('role', 'member')
                    } for m in members
                ]
            })

        enriched.sort(key=lambda q: q.get('updatedAt', 0), reverse=True)

        return success_response({'queues': enriched})

    except KeyError as error:
        log_error('Invalid request context for list queues', error=error)
        return server_error_response('Invalid request context')
    except Exception as error:
        log_error('Error listing queues', error=error)
        return server_error_response('Failed to load queues')


