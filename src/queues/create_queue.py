"""
Create shared queue endpoint.
"""
import os
import sys
import json
import uuid
import time
import boto3
from boto3.dynamodb.conditions import Key

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import put_item, batch_get_items, query_items
from common.response_utils import (
    created_response,
    bad_request_response,
    server_error_response
)
from common.logger import log_info, log_error


SHARED_QUEUES_TABLE = os.environ.get('SHARED_QUEUES_TABLE')
QUEUE_MEMBERS_TABLE = os.environ.get('QUEUE_MEMBERS_TABLE')
USERS_TABLE = os.environ.get('USERS_TABLE')

dynamodb_client = boto3.client('dynamodb')


def handler(event, context):
    """
    Create a new shared queue.
    
    Request body:
        {
            "name": "Queue name",
            "description": "Optional description",
            "isPublic": false,
            "memberIds": ["userId1", "userId2"]  // Optional initial members
        }
    
    Returns:
        Created queue with ID
    """
    try:
        # Extract user ID from authorizer context
        owner_id = event['requestContext']['authorizer']['userId']
        
        log_info('Create queue request', owner_id=owner_id)
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return bad_request_response('Invalid JSON in request body')
        
        name = body.get('name')
        description = body.get('description', '')
        is_public = body.get('isPublic', False)
        member_ids = body.get('memberIds', [])
        
        # Validate required fields
        if not name:
            return bad_request_response('Queue name is required')
        
        if len(name) > 100:
            return bad_request_response('Queue name must be 100 characters or less')
            
        # Validate members exist
        if member_ids:
            # Deduplicate
            member_ids = list(set(member_ids))
            # Remove owner if present (will be added as owner role)
            if owner_id in member_ids:
                member_ids.remove(owner_id)
                
            if member_ids:
                keys = [{'userId': mid} for mid in member_ids]
                found_users = batch_get_items(USERS_TABLE, keys)
                
                if len(found_users) != len(member_ids):
                    # Find which ones are missing
                    found_ids = [u['userId'] for u in found_users]
                    missing_ids = [mid for mid in member_ids if mid not in found_ids]
                    return bad_request_response(f"Users not found: {', '.join(missing_ids)}")
            else:
                found_users = []
        else:
            found_users = []

        # Ensure none of the participants are already in an active queue
        def user_has_active_queue(user_id: str) -> bool:
            memberships = query_items(
                QUEUE_MEMBERS_TABLE,
                Key('userId').eq(user_id),
                index_name='UserQueuesIndex',
                limit=1
            )
            return len(memberships) > 0

        conflict_users = []
        users_to_check = [owner_id] + member_ids
        for uid in users_to_check:
            if user_has_active_queue(uid):
                conflict_users.append(uid)

        if conflict_users:
            if owner_id in conflict_users:
                return bad_request_response('You already have an active queue. Leave or delete it before creating another.')
            else:
                return bad_request_response('One or more invited members are already participating in another queue. Ask them to leave before adding them here.')
        
        # Create queue
        queue_id = str(uuid.uuid4())
        timestamp = int(time.time())
        
        queue_item = {
            'queueId': queue_id,
            'ownerId': owner_id,
            'name': name,
            'description': description,
            'isPublic': is_public,
            'tracks': [],  # List of track objects
            'createdAt': timestamp,
            'updatedAt': timestamp
        }
        
        # Prepare transaction items
        transaction_items = [
            {
                'Put': {
                    'TableName': SHARED_QUEUES_TABLE,
                    'Item': {
                        'queueId': {'S': queue_id},
                        'ownerId': {'S': owner_id},
                        'name': {'S': name},
                        'description': {'S': description},
                        'isPublic': {'BOOL': is_public},
                        'tracks': {'L': []},
                        'createdAt': {'N': str(timestamp)},
                        'updatedAt': {'N': str(timestamp)}
                    }
                }
            },
            # Add owner as a member
            {
                'Put': {
                    'TableName': QUEUE_MEMBERS_TABLE,
                    'Item': {
                        'queueId': {'S': queue_id},
                        'userId': {'S': owner_id},
                        'role': {'S': 'owner'},
                        'joinedAt': {'N': str(timestamp)}
                    }
                }
            }
        ]
        
        # Add initial members
        for member_id in member_ids:
            if member_id != owner_id:  # Don't duplicate owner
                transaction_items.append({
                    'Put': {
                        'TableName': QUEUE_MEMBERS_TABLE,
                        'Item': {
                            'queueId': {'S': queue_id},
                            'userId': {'S': member_id},
                            'role': {'S': 'member'},
                            'joinedAt': {'N': str(timestamp)}
                        }
                    }
                })
        
        # Execute transaction
        dynamodb_client.transact_write_items(TransactItems=transaction_items)
        
        log_info('Queue created successfully',
                queue_id=queue_id,
                owner_id=owner_id,
                member_count=len(member_ids) + 1)
        
        return created_response(
            {
                'queueId': queue_id,
                'ownerId': owner_id,
                'name': name,
                'description': description,
                'isPublic': is_public,
                'tracks': [],
                'memberCount': len(member_ids) + 1,
                'createdAt': timestamp,
                'updatedAt': timestamp
            },
            'Queue created successfully'
        )
        
    except KeyError as e:
        log_error('Missing required field', error=e)
        return server_error_response('Invalid request context')
    except Exception as e:
        log_error('Error creating queue', error=e)
        return server_error_response('Failed to create queue')



