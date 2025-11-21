"""
Get current user profile endpoint.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import get_item
from common.response_utils import (
    success_response,
    not_found_response,
    server_error_response
)
from common.logger import log_info, log_error


USERS_TABLE = os.environ.get('USERS_TABLE')


def handler(event, context):
    """
    Get current user's profile.
    
    Returns:
        User profile data (excluding sensitive fields)
    """
    try:
        # Extract user ID from authorizer context
        user_id = event['requestContext']['authorizer']['userId']
        
        log_info('Get user profile', user_id=user_id)
        
        # Get user from database
        user = get_item(USERS_TABLE, {'userId': user_id})
        
        if not user:
            log_error('User not found', user_id=user_id)
            return not_found_response('User not found')
        
        # Remove sensitive fields
        safe_user = {
            'userId': user['userId'],
            'spotifyId': user['spotifyId'],
            'email': user.get('email'),
            'displayName': user.get('displayName'),
            'visibility': user.get('visibility', 'friends'),
            'createdAt': user.get('createdAt'),
            'lastLogin': user.get('lastLogin')
        }
        
        log_info('User profile retrieved successfully', user_id=user_id)
        
        return success_response(safe_user)
        
    except KeyError as e:
        log_error('Missing required field', error=e)
        return server_error_response('Invalid request context')
    except Exception as e:
        log_error('Error retrieving user profile', error=e)
        return server_error_response('Failed to retrieve user profile')




