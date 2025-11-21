"""
Leave queue endpoint.
"""
import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from boto3.dynamodb.conditions import Key

from common.dynamodb_utils import delete_item, get_item, query_items
from common.response_utils import (
    success_response,
    bad_request_response,
    not_found_response,
    server_error_response
)
from common.logger import log_info, log_error


SHARED_QUEUES_TABLE = os.environ.get('SHARED_QUEUES_TABLE')
QUEUE_MEMBERS_TABLE = os.environ.get('QUEUE_MEMBERS_TABLE')


def handler(event, context):
    """
    Leave a shared queue.
    
    Path parameter:
        queueId: ID of the queue
        
    Returns:
        Success message
    """
    try:
        # Extract user ID from authorizer context
        user_id = event['requestContext']['authorizer']['userId']
        
        # Extract queue ID from path parameters
        queue_id = event['pathParameters'].get('queueId')
        
        if not queue_id:
            return bad_request_response('Queue ID is required')
            
        log_info('Leave queue request', queue_id=queue_id, user_id=user_id)
        
        # Check if queue exists
        queue = get_item(SHARED_QUEUES_TABLE, {'queueId': queue_id})
        if not queue:
            return not_found_response('Queue not found')
            
        # If user is owner, they can't leave (for now, or delete queue)
        if queue.get('ownerId') == user_id:
            # Optional: Allow deleting queue?
            return bad_request_response('Owner cannot leave the queue. Delete it instead.')
            
        # Delete membership
        delete_item(
            QUEUE_MEMBERS_TABLE,
            {'queueId': queue_id, 'userId': user_id}
        )
        
        # Check if any members remain. If not, delete the queue automatically.
        remaining_members = query_items(
            QUEUE_MEMBERS_TABLE,
            Key('queueId').eq(queue_id)
        )

        if not remaining_members:
            delete_item(SHARED_QUEUES_TABLE, {'queueId': queue_id})
            log_info('Queue automatically deleted because it became empty', queue_id=queue_id)
            message = 'Successfully left the queue. It has been closed because no members remain.'
        else:
            log_info('User left queue', queue_id=queue_id, user_id=user_id)
            message = 'Successfully left the queue'
        
        return success_response({'message': message})
        
    except Exception as e:
        log_error('Error leaving queue', error=e)
        return server_error_response('Failed to leave queue')
