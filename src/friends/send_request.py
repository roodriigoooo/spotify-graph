"""
Send friend request endpoint.
"""
import os
import sys
import json
import uuid
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import put_item, get_item, query_items
from common.response_utils import (
    created_response,
    bad_request_response,
    not_found_response,
    conflict_response,
    server_error_response
)
from common.logger import log_info, log_error
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError


USERS_TABLE = os.environ.get('USERS_TABLE')
FRIENDS_TABLE = os.environ.get('FRIENDS_TABLE')
FRIEND_REQUESTS_TABLE = os.environ.get('FRIEND_REQUESTS_TABLE')


def handler(event, context):
    """
    Send a friend request to another user.
    
    Request body:
        {
            "toUserId": "uuid-of-recipient"
        }
    
    Returns:
        Created friend request
    """
    try:
        # Extract sender user ID from authorizer context
        from_user_id = event['requestContext']['authorizer']['userId']
        
        log_info('Send friend request', from_user_id=from_user_id)
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return bad_request_response('Invalid JSON in request body')
        
        to_user_id = body.get('toUserId')
        to_spotify_id = body.get('toSpotifyId')
        
        # Lookup user by Spotify ID if User ID not provided
        if not to_user_id and to_spotify_id:
            log_info('Looking up user by Spotify ID', spotify_id=to_spotify_id)
            users = query_items(
                USERS_TABLE,
                Key('spotifyId').eq(to_spotify_id),
                index_name='SpotifyIdIndex'
            )
            if users:
                to_user_id = users[0]['userId']
            else:
                return not_found_response(f'User with Spotify ID {to_spotify_id} not found')
        
        if not to_user_id:
            return bad_request_response('toUserId or toSpotifyId is required')
        
        # Can't send request to yourself
        if from_user_id == to_user_id:
            return bad_request_response('Cannot send friend request to yourself')
        
        # Check if recipient user exists
        to_user = get_item(USERS_TABLE, {'userId': to_user_id})
        if not to_user:
            return not_found_response('User not found')
        
        # Check if already friends
        existing_friendship = get_item(
            FRIENDS_TABLE,
            {'userId': from_user_id, 'friendId': to_user_id}
        )
        if existing_friendship:
            return conflict_response('Already friends with this user')
        
        # Check if there's already a pending request (from either direction)
        existing_requests = query_items(
            FRIEND_REQUESTS_TABLE,
            Key('toUserId').eq(to_user_id),
            index_name='ToUserIndex',
            filter_expression=Attr('fromUserId').eq(from_user_id) & Attr('status').eq('pending')
        )
        
        if existing_requests:
            return conflict_response('Friend request already pending')
        
        # Check if there's a reverse pending request
        reverse_requests = query_items(
            FRIEND_REQUESTS_TABLE,
            Key('toUserId').eq(from_user_id),
            index_name='ToUserIndex',
            filter_expression=Attr('fromUserId').eq(to_user_id) & Attr('status').eq('pending')
        )
        
        if reverse_requests:
            return conflict_response('This user has already sent you a friend request. Please accept it instead.')
        
        # Create friend request
        request_id = str(uuid.uuid4())
        request_item = {
            'requestId': request_id,
            'fromUserId': from_user_id,
            'toUserId': to_user_id,
            'status': 'pending',
            'createdAt': int(time.time())
        }
        
        # Use condition expression to ensure idempotency
        try:
            put_item(
                FRIEND_REQUESTS_TABLE,
                request_item,
                condition_expression='attribute_not_exists(requestId)'
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return conflict_response('Friend request already exists')
            raise
        
        log_info('Friend request sent successfully',
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                request_id=request_id)
        
        return created_response(
            {
                'requestId': request_id,
                'fromUserId': from_user_id,
                'toUserId': to_user_id,
                'status': 'pending',
                'createdAt': request_item['createdAt']
            },
            'Friend request sent successfully'
        )
        
    except KeyError as e:
        log_error('Missing required field', error=e)
        return server_error_response('Invalid request context')
    except Exception as e:
        log_error('Error sending friend request', error=e)
        return server_error_response('Failed to send friend request')



