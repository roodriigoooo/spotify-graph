"""
WebSocket default route handler.
Handles incoming WebSocket messages from clients.
"""
import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import get_item
from common.response_utils import websocket_response
from common.logger import log_info, log_error


CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE')


def handler(event, context):
    """
    Handle incoming WebSocket messages.
    
    Supported actions:
        - ping: Simple health check
        - subscribe: Subscribe to presence updates (automatic on connect)
        - unsubscribe: Unsubscribe from updates
    
    Returns:
        WebSocket response
    """
    try:
        connection_id = event['requestContext']['connectionId']
        
        # Parse message body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            log_error('Invalid JSON in WebSocket message', connection_id=connection_id)
            return websocket_response(400, {'error': 'Invalid JSON'})
        
        action = body.get('action', 'unknown')
        
        log_info('WebSocket message received', connection_id=connection_id, action=action)
        
        # Get connection info to verify user
        connection = get_item(CONNECTIONS_TABLE, {'connectionId': connection_id})
        
        if not connection:
            log_error('Connection not found', connection_id=connection_id)
            return websocket_response(404, {'error': 'Connection not found'})
        
        user_id = connection['userId']
        
        # Handle different actions
        if action == 'ping':
            return handle_ping(connection_id, user_id)
        elif action == 'subscribe':
            return handle_subscribe(connection_id, user_id, body)
        elif action == 'unsubscribe':
            return handle_unsubscribe(connection_id, user_id, body)
        else:
            log_error('Unknown action', connection_id=connection_id, action=action)
            return websocket_response(400, {'error': f'Unknown action: {action}'})
        
    except Exception as e:
        log_error('Error handling WebSocket message', error=e)
        return websocket_response(500, {'error': 'Internal server error'})


def handle_ping(connection_id: str, user_id: str):
    """Handle ping action."""
    log_info('Ping received', connection_id=connection_id, user_id=user_id)
    return websocket_response(200, {
        'action': 'pong',
        'timestamp': int(time.time())
    })


def handle_subscribe(connection_id: str, user_id: str, body: dict):
    """
    Handle subscribe action.
    Note: Subscription is automatic on connect based on friendships.
    This is for explicit subscription requests if needed.
    """
    log_info('Subscribe request', connection_id=connection_id, user_id=user_id)
    return websocket_response(200, {
        'action': 'subscribed',
        'message': 'You are now subscribed to presence updates'
    })


def handle_unsubscribe(connection_id: str, user_id: str, body: dict):
    """Handle unsubscribe action."""
    log_info('Unsubscribe request', connection_id=connection_id, user_id=user_id)
    return websocket_response(200, {
        'action': 'unsubscribed',
        'message': 'You are now unsubscribed from presence updates'
    })


# Import time at module level
import time



