"""
Update user visibility settings endpoint.
"""
import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import update_item, get_item
from common.response_utils import (
    success_response,
    bad_request_response,
    not_found_response,
    server_error_response
)
from common.logger import log_info, log_error


USERS_TABLE = os.environ.get('USERS_TABLE')
VALID_VISIBILITY_VALUES = ['private', 'friends', 'public']


def handler(event, context):
    """
    Update user's visibility setting.
    
    Request body:
        {
            "visibility": "private" | "friends" | "public"
        }
    
    Returns:
        Updated visibility setting
    """
    try:
        # Extract user ID from authorizer context
        user_id = event['requestContext']['authorizer']['userId']
        
        log_info('Update visibility request', user_id=user_id)
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return bad_request_response('Invalid JSON in request body')
        
        visibility = body.get('visibility')
        
        # Validate visibility value
        if not visibility:
            return bad_request_response('Visibility field is required')
        
        if visibility not in VALID_VISIBILITY_VALUES:
            return bad_request_response(
                f'Invalid visibility value. Must be one of: {", ".join(VALID_VISIBILITY_VALUES)}'
            )
        
        # Check if user exists
        user = get_item(USERS_TABLE, {'userId': user_id})
        if not user:
            log_error('User not found', user_id=user_id)
            return not_found_response('User not found')
        
        # Update user visibility
        success = update_item(
            USERS_TABLE,
            key={'userId': user_id},
            update_expression='SET visibility = :visibility',
            expression_values={':visibility': visibility},
            condition_expression='attribute_exists(userId)'
        )
        
        if not success:
            log_error('Failed to update visibility', user_id=user_id)
            return server_error_response('Failed to update visibility')
        
        log_info('Visibility updated successfully', user_id=user_id, visibility=visibility)
        
        return success_response(
            {'visibility': visibility},
            'Visibility updated successfully'
        )
        
    except KeyError as e:
        log_error('Missing required field', error=e)
        return server_error_response('Invalid request context')
    except Exception as e:
        log_error('Error updating visibility', error=e)
        return server_error_response('Failed to update visibility')



