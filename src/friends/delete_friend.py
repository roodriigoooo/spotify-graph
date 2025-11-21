"""
Delete friend (unfriend) endpoint.
"""
import os
import sys
import boto3

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import get_item
from common.response_utils import (
    success_response,
    not_found_response,
    server_error_response
)
from common.logger import log_info, log_error
from botocore.exceptions import ClientError


FRIENDS_TABLE = os.environ.get('FRIENDS_TABLE')

# Use DynamoDB client for transactions
dynamodb_client = boto3.client('dynamodb')


def handler(event, context):
    """
    Delete a friendship (unfriend a user).
    Removes mutual friendship records using transaction.
    
    Path parameter:
        friendId: ID of the friend to remove
    
    Returns:
        Success message
    """
    try:
        # Extract user ID from authorizer context
        user_id = event['requestContext']['authorizer']['userId']
        
        # Extract friend ID from path parameters
        friend_id = event['pathParameters'].get('friendId')
        
        if not friend_id:
            return not_found_response('Friend ID is required')
        
        log_info('Delete friend request', user_id=user_id, friend_id=friend_id)
        
        # Check if friendship exists
        friendship = get_item(FRIENDS_TABLE, {'userId': user_id, 'friendId': friend_id})
        
        if not friendship:
            return not_found_response('Friendship not found')
        
        # Use transaction to delete both sides of the friendship
        try:
            dynamodb_client.transact_write_items(
                TransactItems=[
                    {
                        'Delete': {
                            'TableName': FRIENDS_TABLE,
                            'Key': {
                                'userId': {'S': user_id},
                                'friendId': {'S': friend_id}
                            },
                            'ConditionExpression': 'attribute_exists(userId) AND attribute_exists(friendId)'
                        }
                    },
                    {
                        'Delete': {
                            'TableName': FRIENDS_TABLE,
                            'Key': {
                                'userId': {'S': friend_id},
                                'friendId': {'S': user_id}
                            },
                            'ConditionExpression': 'attribute_exists(userId) AND attribute_exists(friendId)'
                        }
                    }
                ]
            )
            
            log_info('Friendship deleted successfully', user_id=user_id, friend_id=friend_id)
            
            return success_response(
                message='Friend removed successfully'
            )
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'TransactionCanceledException':
                return not_found_response('Friendship not found or already deleted')
            raise
        
    except KeyError as e:
        log_error('Missing required field', error=e)
        return server_error_response('Invalid request context')
    except Exception as e:
        log_error('Error deleting friend', error=e)
        return server_error_response('Failed to delete friend')



