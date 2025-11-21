"""
JWT Authorizer Lambda for API Gateway.
Validates JWT tokens and returns IAM policy.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.jwt_utils import decode_token
from common.logger import log_info, log_error


def handler(event, context):
    """
    Lambda authorizer for API Gateway.
    
    Args:
        event: API Gateway authorizer event
        context: Lambda context
        
    Returns:
        IAM policy document
    """
    try:
        log_info('Authorizer invoked', request_id=context.aws_request_id if hasattr(context, 'aws_request_id') else 'unknown')
        
        # Allow OPTIONS requests for CORS preflight (no auth required)
        method_arn = event.get('methodArn', '')
        if '/OPTIONS/' in method_arn or event.get('httpMethod') == 'OPTIONS':
            log_info('OPTIONS request detected, allowing without auth')
            # Return allow policy for OPTIONS requests
            policy = generate_policy('cors-preflight', 'Allow', event['methodArn'])
            return policy
        
        # Extract token from Authorization header
        # API Gateway might send headers in lower case or mixed case
        headers = event.get('headers', {})
        token = (
            headers.get('Authorization') or
            headers.get('authorization') or
            headers.get('X-Auth-Token') or
            headers.get('x-auth-token')
        )
        
        if not token:
            log_error('No authorization token provided')
            raise Exception('Unauthorized')
        
        # Handle "Bearer <token>" format
        if token.lower().startswith('bearer '):
            token = token[7:]
        
        # Decode and validate token
        payload = decode_token(token)
        
        if not payload:
            log_error('Invalid or expired token')
            raise Exception('Unauthorized')
        
        user_id = payload.get('userId')
        
        if not user_id:
            log_error('No userId in token payload')
            raise Exception('Unauthorized')
        
        log_info('Token validated successfully', user_id=user_id)
        
        # Generate IAM policy
        policy = generate_policy(user_id, 'Allow', event['methodArn'])
        
        # Add user context to pass to downstream Lambdas
        policy['context'] = {
            'userId': user_id,
            'spotifyId': payload.get('spotifyId', '')
        }
        
        return policy
        
    except Exception as e:
        log_error('Authorization failed', error=e)
        # Return deny policy
        raise Exception('Unauthorized')


def generate_policy(principal_id: str, effect: str, resource: str) -> dict:
    """
    Generate IAM policy document.
    
    Args:
        principal_id: User identifier
        effect: Allow or Deny
        resource: Resource ARN (will be converted to wildcard for all methods)
        
    Returns:
        IAM policy document
    """
    # Convert specific resource ARN to wildcard to allow all HTTP methods
    # Example: arn:aws:execute-api:region:account:api-id/stage/GET/path
    # Becomes: arn:aws:execute-api:region:account:api-id/stage/*/*
    resource_parts = resource.split('/')
    if len(resource_parts) >= 3:
        # Keep everything up to and including the stage, then add wildcards
        wildcard_resource = '/'.join(resource_parts[:2]) + '/*/*'
    else:
        wildcard_resource = resource
    
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': wildcard_resource
                }
            ]
        }
    }
    
    return policy



