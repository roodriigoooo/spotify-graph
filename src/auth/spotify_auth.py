"""
Spotify OAuth authentication handler.
Handles authorization URL generation and callback processing.
"""
import os
import sys
import json
import uuid
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.spotify_client import SpotifyClient, SpotifyAPIError
from common.jwt_utils import generate_token
from common.dynamodb_utils import put_item, query_items, update_item
from common.response_utils import (
    success_response,
    bad_request_response,
    server_error_response
)
from common.logger import log_info, log_error
from boto3.dynamodb.conditions import Key


USERS_TABLE = os.environ.get('USERS_TABLE')
FRONTEND_CALLBACK_URL = os.environ.get('FRONTEND_CALLBACK_URL')


def handler(event, context):
    """
    Handle Spotify OAuth flow.
    
    Routes:
        GET /auth/spotify - Returns authorization URL
        GET /auth/callback - Handles OAuth callback
    """
    try:
        log_info('Spotify auth handler invoked', path=event.get('path'))
        
        path = event.get('path', '')
        
        if path.endswith('/auth/spotify'):
            return handle_auth_url(event, context)
        elif path.endswith('/auth/callback'):
            return handle_callback(event, context)
        else:
            return bad_request_response('Invalid path')
            
    except Exception as e:
        log_error('Spotify auth handler error', error=e)
        return server_error_response(str(e))


def handle_auth_url(event, context):
    """
    Generate and return Spotify authorization URL.
    
    Returns:
        Authorization URL for client to redirect to
    """
    try:
        # Generate state for CSRF protection
        state = str(uuid.uuid4())
        
        # Get redirect URI from query params or use default
        query_params = event.get('queryStringParameters') or {}
        redirect_uri = query_params.get('redirect_uri', FRONTEND_CALLBACK_URL)
        
        # Create Spotify client and get auth URL
        spotify_client = SpotifyClient()
        
        # Build the callback URL that Spotify will redirect to
        api_callback_url = f"https://{event['requestContext']['domainName']}/{event['requestContext']['stage']}/auth/callback"
        
        auth_url = spotify_client.get_authorization_url(
            redirect_uri=api_callback_url,
            state=state
        )
        
        log_info('Generated auth URL', state=state)
        
        return success_response({
            'authUrl': auth_url,
            'state': state
        })
        
    except Exception as e:
        log_error('Error generating auth URL', error=e)
        return server_error_response('Failed to generate authorization URL')


def handle_callback(event, context):
    """
    Handle OAuth callback from Spotify.
    Exchange code for tokens, get user info, create/update user.
    
    Returns:
        Redirect to frontend with JWT token
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        
        code = query_params.get('code')
        state = query_params.get('state')
        error = query_params.get('error')
        
        if error:
            log_error('OAuth error from Spotify', error=error)
            return redirect_to_frontend(error=error)
        
        if not code or not state:
            log_error('Missing code or state in callback')
            return redirect_to_frontend(error='missing_parameters')
        
        # Build callback URL
        api_callback_url = f"https://{event['requestContext']['domainName']}/{event['requestContext']['stage']}/auth/callback"
        
        # Exchange code for tokens
        spotify_client = SpotifyClient()
        token_data = spotify_client.exchange_code_for_token(code, api_callback_url)
        
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        
        # Get user profile from Spotify
        spotify_client.access_token = access_token
        user_profile = spotify_client.get_current_user()
        
        spotify_id = user_profile.get('id')
        email = user_profile.get('email')
        display_name = user_profile.get('display_name')
        
        log_info('Retrieved Spotify user profile', spotify_id=spotify_id)
        
        # Check if user already exists
        existing_users = query_items(
            USERS_TABLE,
            Key('spotifyId').eq(spotify_id),
            index_name='SpotifyIdIndex'
        )
        
        if existing_users:
            # Update existing user
            user = existing_users[0]
            user_id = user['userId']
            
            update_item(
                USERS_TABLE,
                key={'userId': user_id},
                update_expression='SET spotifyAccessToken = :access, spotifyRefreshToken = :refresh, tokenExpiresAt = :expires, displayName = :name, lastLogin = :login',
                expression_values={
                    ':access': access_token,
                    ':refresh': refresh_token,
                    ':expires': int(time.time()) + expires_in,
                    ':name': display_name,
                    ':login': int(time.time())
                }
            )
            
            log_info('Updated existing user', user_id=user_id)
        else:
            # Create new user
            user_id = str(uuid.uuid4())
            
            user_item = {
                'userId': user_id,
                'spotifyId': spotify_id,
                'email': email,
                'displayName': display_name,
                'spotifyAccessToken': access_token,
                'spotifyRefreshToken': refresh_token,
                'tokenExpiresAt': int(time.time()) + expires_in,
                'visibility': 'friends',  # Default visibility
                'createdAt': int(time.time()),
                'lastLogin': int(time.time())
            }
            
            put_item(USERS_TABLE, user_item)
            
            log_info('Created new user', user_id=user_id)
        
        # Generate JWT token
        jwt_token = generate_token(user_id, spotify_id)
        
        # Redirect to frontend with token
        return redirect_to_frontend(token=jwt_token)
        
    except SpotifyAPIError as e:
        log_error('Spotify API error in callback', error=e)
        return redirect_to_frontend(error='spotify_api_error')
    except Exception as e:
        log_error('Error in callback handler', error=e)
        return redirect_to_frontend(error='internal_error')


def redirect_to_frontend(token: str = None, error: str = None):
    """
    Create redirect response to frontend.
    
    Args:
        token: JWT token if successful
        error: Error message if failed
        
    Returns:
        HTTP redirect response
    """
    if token:
        url = f"{FRONTEND_CALLBACK_URL}?token={token}"
    else:
        url = f"{FRONTEND_CALLBACK_URL}?error={error}"
    
    return {
        'statusCode': 302,
        'headers': {
            'Location': url
        },
        'body': ''
    }



