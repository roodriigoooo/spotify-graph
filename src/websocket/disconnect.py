"""
WebSocket disconnect handler.
Handles WebSocket disconnections and cleans up connection records.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import delete_item
from common.response_utils import websocket_response
from common.logger import log_info, log_error


CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE')


def handler(event, context):
    """
    Handle WebSocket disconnection.
    
    Removes connection record from DynamoDB.
    
    Returns:
        WebSocket response with 200
    """
    try:
        connection_id = event['requestContext']['connectionId']
        
        log_info('WebSocket disconnect request', connection_id=connection_id)
        
        # Delete connection record
        delete_item(CONNECTIONS_TABLE, {'connectionId': connection_id})
        
        log_info('WebSocket connection removed', connection_id=connection_id)
        
        return websocket_response(200)
        
    except Exception as e:
        log_error('Error handling WebSocket disconnection', error=e)
        return websocket_response(200)  # Return 200 even on error



