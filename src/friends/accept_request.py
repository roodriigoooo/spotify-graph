"""
Accept friend request endpoint.
"""
import os
import sys
import json
import time
import boto3

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import get_item, update_item
from common.response_utils import (
    success_response,
    bad_request_response,
    not_found_response,
    forbidden_response,
    server_error_response
)
from common.logger import log_info, log_error
from botocore.exceptions import ClientError


FRIENDS_TABLE = os.environ.get('FRIENDS_TABLE')
FRIEND_REQUESTS_TABLE = os.environ.get('FRIEND_REQUESTS_TABLE')

# Use DynamoDB client for transactions
dynamodb_client = boto3.client('dynamodb')


def handler(event, context):
    """
    Accept a friend request.
    Creates mutual friendship records using transaction.
    
    Request body:
        {
            "requestId": "uuid-of-request"
        }
    
    Returns:
        Success message with friendship data
    """
    try:
        # Extract user ID from authorizer context
        user_id = event['requestContext']['authorizer']['userId']
        
        log_info('Accept friend request', user_id=user_id)
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return bad_request_response('Invalid JSON in request body')
        
        request_id = body.get('requestId')
        
        if not request_id:
            return bad_request_response('requestId is required')
        
        # Get the friend request
        friend_request = get_item(FRIEND_REQUESTS_TABLE, {'requestId': request_id})
        
        if not friend_request:
            return not_found_response('Friend request not found')
        
        # Verify the request is for this user
        if friend_request['toUserId'] != user_id:
            return forbidden_response('This friend request is not for you')
        
        # Verify request is still pending
        if friend_request.get('status') != 'pending':
            return bad_request_response('Friend request is not pending')
        
        from_user_id = friend_request['fromUserId']
        to_user_id = friend_request['toUserId']
        timestamp = int(time.time())
        
        # Use DynamoDB transaction to:
        # 1. Create friendship record for user A -> user B
        # 2. Create friendship record for user B -> user A
        # 3. Update friend request status to accepted
        # This ensures atomic operation for mutual friendship
        
        try:
            dynamodb_client.transact_write_items(
                TransactItems=[
                    {
                        'Put': {
                            'TableName': FRIENDS_TABLE,
                            'Item': {
                                'userId': {'S': from_user_id},
                                'friendId': {'S': to_user_id},
                                'createdAt': {'N': str(timestamp)}
                            },
                            'ConditionExpression': 'attribute_not_exists(userId) AND attribute_not_exists(friendId)'
                        }
                    },
                    {
                        'Put': {
                            'TableName': FRIENDS_TABLE,
                            'Item': {
                                'userId': {'S': to_user_id},
                                'friendId': {'S': from_user_id},
                                'createdAt': {'N': str(timestamp)}
                            },
                            'ConditionExpression': 'attribute_not_exists(userId) AND attribute_not_exists(friendId)'
                        }
                    },
                    {
                        'Update': {
                            'TableName': FRIEND_REQUESTS_TABLE,
                            'Key': {
                                'requestId': {'S': request_id}
                            },
                            'UpdateExpression': 'SET #status = :status, acceptedAt = :acceptedAt',
                            'ExpressionAttributeNames': {
                                '#status': 'status'
                            },
                            'ExpressionAttributeValues': {
                                ':status': {'S': 'accepted'},
                                ':acceptedAt': {'N': str(timestamp)},
                                ':pending': {'S': 'pending'}
                            },
                            'ConditionExpression': '#status = :pending'
                        }
                    }
                ]
            )
            
            log_info('Friend request accepted successfully',
                    request_id=request_id,
                    from_user_id=from_user_id,
                    to_user_id=to_user_id)
            
            return success_response(
                {
                    'requestId': request_id,
                    'fromUserId': from_user_id,
                    'toUserId': to_user_id,
                    'status': 'accepted',
                    'acceptedAt': timestamp
                },
                'Friend request accepted successfully'
            )
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'TransactionCanceledException':
                reasons = e.response['Error'].get('CancellationReasons', [])
                log_error('Transaction failed', reasons=str(reasons))
                return bad_request_response('Unable to accept friend request. It may have already been accepted.')
            raise
        
    except KeyError as e:
        log_error('Missing required field', error=e)
        return server_error_response('Invalid request context')
    except Exception as e:
        log_error('Error accepting friend request', error=e)
        return server_error_response('Failed to accept friend request')



