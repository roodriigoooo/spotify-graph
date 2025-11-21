"""
Get shared queue endpoint.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import get_item, query_items
from common.response_utils import (
    success_response,
    not_found_response,
    forbidden_response,
    server_error_response
)
from common.logger import log_info, log_error
from boto3.dynamodb.conditions import Key


SHARED_QUEUES_TABLE = os.environ.get('SHARED_QUEUES_TABLE')
QUEUE_MEMBERS_TABLE = os.environ.get('QUEUE_MEMBERS_TABLE')


def handler(event, context):
    """
    Get a shared queue by ID.
    
    Path parameter:
        queueId: ID of the queue
    
    Returns:
        Queue data with tracks and members
    """
    try:
        # Extract user ID from authorizer context
        user_id = event['requestContext']['authorizer']['userId']
        
        # Extract queue ID from path parameters
        queue_id = event['pathParameters'].get('queueId')
        
        if not queue_id:
            return not_found_response('Queue ID is required')
        
        log_info('Get queue request', queue_id=queue_id, user_id=user_id)
        
        # Get queue
        queue = get_item(SHARED_QUEUES_TABLE, {'queueId': queue_id})
        
        if not queue:
            return not_found_response('Queue not found')
        
        # Check if user has access to this queue
        if not queue.get('isPublic', False):
            # For private queues, check if user is a member
            membership = get_item(
                QUEUE_MEMBERS_TABLE,
                {'queueId': queue_id, 'userId': user_id}
            )
            
            if not membership:
                return forbidden_response('You do not have access to this queue')
        
        # Get queue members
        members = query_items(
            QUEUE_MEMBERS_TABLE,
            Key('queueId').eq(queue_id)
        )
        
        # Format response
        queue_data = {
            'queueId': queue['queueId'],
            'ownerId': queue['ownerId'],
            'name': queue['name'],
            'description': queue.get('description', ''),
            'isPublic': queue.get('isPublic', False),
            'tracks': queue.get('tracks', []),
            'members': [
                {
                    'userId': m['userId'],
                    'role': m.get('role', 'member'),
                    'joinedAt': m.get('joinedAt')
                }
                for m in members
            ],
            'createdAt': queue.get('createdAt'),
            'updatedAt': queue.get('updatedAt')
        }
        
        log_info('Queue retrieved successfully', queue_id=queue_id)
        
        return success_response(queue_data)
        
    except KeyError as e:
        log_error('Missing required field', error=e)
        return server_error_response('Invalid request context')
    except Exception as e:
        log_error('Error retrieving queue', error=e)
        return server_error_response('Failed to retrieve queue')



