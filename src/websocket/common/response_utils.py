"""
Utility functions for creating standardized Lambda responses.
"""
import json
from decimal import Decimal
from typing import Dict, Any, Optional


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal types from DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert Decimal to int if it's a whole number, else float
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        return super(DecimalEncoder, self).default(obj)


def create_response(
    status_code: int,
    body: Any,
    headers: Optional[Dict[str, str]] = None
) -> Dict:
    """
    Create a standardized API Gateway response.
    
    Args:
        status_code: HTTP status code
        body: Response body (will be JSON encoded)
        headers: Optional additional headers
        
    Returns:
        API Gateway response dict
    """
    default_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
    }
    
    if headers:
        default_headers.update(headers)
    
    return {
        'statusCode': status_code,
        'headers': default_headers,
        'body': json.dumps(body, cls=DecimalEncoder) if not isinstance(body, str) else body
    }


def success_response(data: Any = None, message: str = 'Success') -> Dict:
    """Create a 200 OK response."""
    body = {'message': message}
    if data is not None:
        body['data'] = data
    return create_response(200, body)


def created_response(data: Any = None, message: str = 'Created') -> Dict:
    """Create a 201 Created response."""
    body = {'message': message}
    if data is not None:
        body['data'] = data
    return create_response(201, body)


def bad_request_response(message: str = 'Bad request', errors: Optional[Dict] = None) -> Dict:
    """Create a 400 Bad Request response."""
    body = {'error': message}
    if errors:
        body['errors'] = errors
    return create_response(400, body)


def unauthorized_response(message: str = 'Unauthorized') -> Dict:
    """Create a 401 Unauthorized response."""
    return create_response(401, {'error': message})


def forbidden_response(message: str = 'Forbidden') -> Dict:
    """Create a 403 Forbidden response."""
    return create_response(403, {'error': message})


def not_found_response(message: str = 'Not found') -> Dict:
    """Create a 404 Not Found response."""
    return create_response(404, {'error': message})


def conflict_response(message: str = 'Conflict') -> Dict:
    """Create a 409 Conflict response."""
    return create_response(409, {'error': message})


def server_error_response(message: str = 'Internal server error') -> Dict:
    """Create a 500 Internal Server Error response."""
    return create_response(500, {'error': message})


def websocket_response(status_code: int, body: Optional[Dict] = None) -> Dict:
    """
    Create a WebSocket API response.
    
    Args:
        status_code: HTTP status code
        body: Optional response body
        
    Returns:
        WebSocket API response dict
    """
    response = {'statusCode': status_code}
    if body:
        response['body'] = json.dumps(body, cls=DecimalEncoder)
    return response



