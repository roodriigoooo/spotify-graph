"""
List user's friends endpoint.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import query_items, batch_get_items
from common.response_utils import success_response, server_error_response
from common.logger import log_info, log_error
from boto3.dynamodb.conditions import Key


FRIENDS_TABLE = os.environ.get('FRIENDS_TABLE')
USERS_TABLE = os.environ.get('USERS_TABLE')


def handler(event, context):
    """
    List all friends for the current user.
    
    Returns:
        List of friends with their basic profile info
    """
    try:
        # Extract user ID from authorizer context
        user_id = event['requestContext']['authorizer']['userId']
        
        log_info('List friends request', user_id=user_id)
        
        # Query all friendships for this user
        friendships = query_items(
            FRIENDS_TABLE,
            Key('userId').eq(user_id)
        )
        
        if not friendships:
            return success_response([])
        
        # Get friend IDs
        friend_ids = [f['friendId'] for f in friendships]
        
        # Batch get friend user profiles
        friend_keys = [{'userId': friend_id} for friend_id in friend_ids]
        friends = batch_get_items(USERS_TABLE, friend_keys)
        
        # Format response (exclude sensitive data)
        friends_data = []
        for friend in friends:
            friends_data.append({
                'userId': friend['userId'],
                'spotifyId': friend['spotifyId'],
                'displayName': friend.get('displayName'),
                'visibility': friend.get('visibility', 'friends')
            })
        
        log_info('Friends list retrieved', user_id=user_id, count=len(friends_data))
        
        return success_response(friends_data)
        
    except KeyError as e:
        log_error('Missing required field', error=e)
        return server_error_response('Invalid request context')
    except Exception as e:
        log_error('Error listing friends', error=e)
        return server_error_response('Failed to retrieve friends list')



