"""
WebSocket broadcast handler.
Triggered by DynamoDB Streams on Presence table updates.
Broadcasts presence updates to friends' active WebSocket connections.
"""
import os
import sys
import json
import boto3

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import query_items, get_item
from common.logger import log_info, log_error, log_warning
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


FRIENDS_TABLE = os.environ.get('FRIENDS_TABLE')
CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE')
USERS_TABLE = os.environ.get('USERS_TABLE')
WEBSOCKET_API_ENDPOINT = os.environ.get('WEBSOCKET_API_ENDPOINT')

# API Gateway Management API client for posting to connections
apigateway_management = None


def get_apigateway_client():
    """Get or create API Gateway Management API client."""
    global apigateway_management
    if not apigateway_management:
        apigateway_management = boto3.client(
            'apigatewaymanagementapi',
            endpoint_url=WEBSOCKET_API_ENDPOINT
        )
    return apigateway_management


def handler(event, context):
    """
    Handle DynamoDB Stream events from Presence table.
    
    For each presence update:
    1. Get user's friends list
    2. Check each friend's visibility settings
    3. Find active WebSocket connections for visible friends
    4. Broadcast presence update to those connections
    
    Also broadcasts to the user's own connections for UI sync.
    
    Returns:
        Processing summary
    """
    try:
        log_info('Broadcast handler triggered', record_count=len(event['Records']))
        
        processed_count = 0
        error_count = 0
        
        for record in event['Records']:
            try:
                # Only process INSERT and MODIFY events
                if record['eventName'] not in ['INSERT', 'MODIFY']:
                    continue
                
                # Extract presence data from new image
                new_image = record['dynamodb'].get('NewImage', {})
                
                user_id = new_image.get('userId', {}).get('S')
                
                if not user_id:
                    log_warning('No userId in DynamoDB record')
                    continue
                
                # Get user info
                user = get_item(USERS_TABLE, {'userId': user_id})
                
                if not user:
                    log_warning('User not found', user_id=user_id)
                    continue
                
                visibility = user.get('visibility', 'friends')
                
                # If user is private, don't broadcast
                if visibility == 'private':
                    log_info('User is private, skipping broadcast', user_id=user_id)
                    continue
                
                # Parse presence data
                presence_data = parse_presence_from_dynamodb(new_image)
                
                # Get list of users to notify
                recipients = get_broadcast_recipients(user_id, visibility)
                
                # Add the user themselves for UI sync
                recipients.add(user_id)
                
                log_info('Broadcasting presence update',
                        user_id=user_id,
                        recipient_count=len(recipients),
                        is_playing=presence_data.get('isPlaying'))
                
                # Broadcast to all recipients
                broadcast_count = broadcast_to_users(recipients, user, presence_data)
                
                log_info('Presence broadcast completed',
                        user_id=user_id,
                        broadcast_count=broadcast_count)
                
                processed_count += 1
                
            except Exception as e:
                log_error('Error processing record', error=e)
                error_count += 1
        
        log_info('Broadcast handler completed',
                processed=processed_count,
                errors=error_count)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'processed': processed_count,
                'errors': error_count
            })
        }
        
    except Exception as e:
        log_error('Fatal error in broadcast handler', error=e)
        raise


def parse_presence_from_dynamodb(dynamodb_item: dict) -> dict:
    """
    Parse presence data from DynamoDB stream format.
    
    Args:
        dynamodb_item: DynamoDB item in stream format
        
    Returns:
        Parsed presence data
    """
    presence = {
        'userId': dynamodb_item.get('userId', {}).get('S'),
        'spotifyId': dynamodb_item.get('spotifyId', {}).get('S'),
        'isPlaying': dynamodb_item.get('isPlaying', {}).get('BOOL', False),
        'updatedAt': int(dynamodb_item.get('updatedAt', {}).get('N', 0))
    }
    
    # Add track info if playing
    if presence['isPlaying']:
        presence['trackId'] = dynamodb_item.get('trackId', {}).get('S')
        presence['trackName'] = dynamodb_item.get('trackName', {}).get('S')
        presence['artistName'] = dynamodb_item.get('artistName', {}).get('S')
        presence['albumName'] = dynamodb_item.get('albumName', {}).get('S')
        presence['albumImageUrl'] = dynamodb_item.get('albumImageUrl', {}).get('S')
        presence['progressMs'] = int(dynamodb_item.get('progressMs', {}).get('N', 0))
        presence['durationMs'] = int(dynamodb_item.get('durationMs', {}).get('N', 0))
    
    return presence


def build_graph_node(user: dict, presence_data: dict) -> dict:
    """
    Build a graph node payload for clients.
    """
    return {
        'userId': presence_data['userId'],
        'displayName': user.get('displayName') or user.get('spotifyId') or 'Friend',
        'spotifyId': user.get('spotifyId'),
        'visibility': user.get('visibility'),
        'lastLogin': user.get('lastLogin'),
        'presence': presence_data
    }


def get_broadcast_recipients(user_id: str, visibility: str) -> set:
    """
    Get list of users who should receive this presence update.
    
    Args:
        user_id: User whose presence changed
        visibility: User's visibility setting
        
    Returns:
        Set of user IDs to notify
    """
    recipients = set()
    
    if visibility == 'friends':
        # Get user's friends
        friendships = query_items(
            FRIENDS_TABLE,
            Key('userId').eq(user_id)
        )
        
        for friendship in friendships:
            recipients.add(friendship['friendId'])
    
    elif visibility == 'public':
        # For public, we could broadcast to all users
        # For now, still limit to friends to avoid spam
        # In production, consider implementing a "public feed" feature
        friendships = query_items(
            FRIENDS_TABLE,
            Key('userId').eq(user_id)
        )
        
        for friendship in friendships:
            recipients.add(friendship['friendId'])
    
    return recipients


def broadcast_to_users(user_ids: set, user: dict, presence_data: dict) -> int:
    """
    Broadcast presence update to list of users.
    
    Args:
        user_ids: Set of user IDs to notify
        user: User object with display name
        presence_data: Presence data to broadcast
        
    Returns:
        Number of successful broadcasts
    """
    if not user_ids:
        return 0
    
    # Prepare message payload
    message = {
        'type': 'presence_update',
        'userId': presence_data['userId'],
        'displayName': user.get('displayName'),
        'spotifyId': user.get('spotifyId'),
        'data': presence_data,
        'graphNode': build_graph_node(user, presence_data)
    }
    
    message_json = json.dumps(message)
    
    broadcast_count = 0
    
    # For each user, find their active connections and send message
    for recipient_id in user_ids:
        try:
            # Get user's connections
            connections = query_items(
                CONNECTIONS_TABLE,
                Key('userId').eq(recipient_id),
                index_name='UserIdIndex'
            )
            
            # Send to each connection
            for connection in connections:
                connection_id = connection['connectionId']
                
                try:
                    client = get_apigateway_client()
                    client.post_to_connection(
                        ConnectionId=connection_id,
                        Data=message_json.encode('utf-8')
                    )
                    broadcast_count += 1
                    
                except ClientError as e:
                    if e.response['Error']['Code'] == 'GoneException':
                        # Connection is stale, remove it
                        log_info('Removing stale connection', connection_id=connection_id)
                        from common.dynamodb_utils import delete_item
                        delete_item(CONNECTIONS_TABLE, {'connectionId': connection_id})
                    else:
                        log_error('Error posting to connection',
                                connection_id=connection_id,
                                error=e)
                
        except Exception as e:
            log_error('Error broadcasting to user', user_id=recipient_id, error=e)
    
    return broadcast_count



