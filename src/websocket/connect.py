"""
WebSocket connect handler.
Handles new WebSocket connections and stores connection info.
"""
import os
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import put_item
from common.jwt_utils import decode_token
from common.response_utils import websocket_response
from common.logger import log_info, log_error


CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE')


def handler(event, context):
    """
    Handle WebSocket connection.
    
    Expects JWT token in query string parameter 'token'.
    Stores connection ID and user ID in DynamoDB.
    
    Returns:
        WebSocket response with 200 or 401
    """
    try:
        connection_id = event['requestContext']['connectionId']
        
        log_info('WebSocket connect request', connection_id=connection_id)
        
        # Extract token from query string
        query_params = event.get('queryStringParameters') or {}
        token = query_params.get('token')
        
        if not token:
            log_error('No token provided in connection request', connection_id=connection_id)
            return websocket_response(401, {'message': 'Unauthorized'})
        
        # Validate token
        payload = decode_token(token)
        
        if not payload:
            log_error('Invalid or expired token', connection_id=connection_id)
            return websocket_response(401, {'message': 'Unauthorized'})
        
        user_id = payload.get('userId')
        
        if not user_id:
            log_error('No userId in token', connection_id=connection_id)
            return websocket_response(401, {'message': 'Unauthorized'})
        
        # Store connection
        timestamp = int(time.time())
        ttl = timestamp + (8 * 60 * 60)  # 8 hours TTL
        
        connection_item = {
            'connectionId': connection_id,
            'userId': user_id,
            'connectedAt': timestamp,
            'ttl': ttl
        }
        
        put_item(CONNECTIONS_TABLE, connection_item)
        
        log_info('WebSocket connection established',
                connection_id=connection_id,
                user_id=user_id)
        
        return websocket_response(200)
        
    except Exception as e:
        log_error('Error handling WebSocket connection', error=e)
        return websocket_response(500, {'message': 'Internal server error'})



