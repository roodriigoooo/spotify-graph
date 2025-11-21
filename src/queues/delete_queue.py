"""
Delete queue endpoint.
"""
import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import delete_item, get_item, query_items
from common.response_utils import (
    success_response,
    bad_request_response,
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
    Delete a shared queue.
    
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
            
        log_info('Delete queue request', queue_id=queue_id, user_id=user_id)
        
        # Check if queue exists
        queue = get_item(SHARED_QUEUES_TABLE, {'queueId': queue_id})
        if not queue:
            return not_found_response('Queue not found')
            
        # Only owner can delete
        if queue.get('ownerId') != user_id:
            return forbidden_response('Only the owner can delete this queue')
            
        # 1. Delete queue item
        delete_item(SHARED_QUEUES_TABLE, {'queueId': queue_id})
        
        # 2. Delete all members (Query QueueMembersTable by queueId)
        # Note: This requires GSI on QueueMembersTable if primary key is queueId+userId?
        # In template:
        # KeySchema: queueId (HASH), userId (RANGE)
        # So we can query by queueId partition key directly!
        
        members = query_items(
            QUEUE_MEMBERS_TABLE,
            Key('queueId').eq(queue_id)
        )
        
        # Batch delete members would be better, but loop delete is okay for small queues
        for member in members:
            delete_item(
                QUEUE_MEMBERS_TABLE,
                {'queueId': queue_id, 'userId': member['userId']}
            )
        
        log_info('Queue deleted successfully', queue_id=queue_id, user_id=user_id)
        
        return success_response({'message': 'Queue deleted successfully'})
        
    except Exception as e:
        log_error('Error deleting queue', error=e)
        return server_error_response('Failed to delete queue')
