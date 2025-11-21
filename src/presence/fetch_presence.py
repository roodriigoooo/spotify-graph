"""
Fetch presence Lambda.
Triggered by SQS queue to fetch individual user's Spotify presence.
Implements proper error handling for rate limiting (HTTP 429).
"""
import os
import sys
import json
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.spotify_client import SpotifyClient, SpotifyAPIError
from common.dynamodb_utils import put_item, update_item, get_item
from common.logger import log_info, log_error, log_warning


PRESENCE_TABLE = os.environ.get('PRESENCE_TABLE')
USERS_TABLE = os.environ.get('USERS_TABLE')


def handler(event, context):
    """
    Fetch Spotify presence for a user.
    
    SQS Event contains:
        - userId: Internal user ID
        - spotifyId: Spotify user ID
        
    Error Handling:
        - HTTP 429: Raises exception to trigger SQS retry with backoff
        - HTTP 401: Attempts token refresh, then retries
        - Other errors: Logged but message deleted (no retry)
    
    Returns:
        Success or raises exception for retry
    """
    try:
        # Process each SQS message
        for record in event['Records']:
            try:
                message_body = json.loads(record['body'])
                
                user_id = message_body['userId']
                spotify_id = message_body['spotifyId']
                
                log_info('Processing presence for user', user_id=user_id)
                
                # Fetch user tokens from DynamoDB
                user = get_item(USERS_TABLE, {'userId': user_id})
                if not user:
                    log_error('User not found during presence fetch', user_id=user_id)
                    continue
                    
                access_token = user.get('spotifyAccessToken')
                refresh_token = user.get('spotifyRefreshToken')
                token_expires_at = user.get('tokenExpiresAt', 0)
                
                if not access_token or not refresh_token:
                    log_warning('User has no tokens', user_id=user_id)
                    continue
                
                # Check if token needs refresh
                current_time = int(time.time())
                if current_time >= token_expires_at - 300:  # Refresh 5 minutes before expiry
                    log_info('Token expired or expiring soon, refreshing', user_id=user_id)
                    access_token = refresh_user_token(user_id, refresh_token)
                
                # Fetch presence from Spotify
                presence_data = fetch_spotify_presence(user_id, access_token, refresh_token)
                
                if presence_data:
                    # Save presence to DynamoDB
                    save_presence(user_id, spotify_id, presence_data)
                    log_info('Presence updated successfully', user_id=user_id)
                else:
                    # No currently playing track
                    log_info('No active playback for user', user_id=user_id)
                    # Optionally save "not playing" status
                    save_presence(user_id, spotify_id, None)
                
            except SpotifyAPIError as e:
                # Handle rate limiting - raise exception to trigger SQS retry
                if e.status_code == 429:
                    log_warning('Rate limited by Spotify API', user_id=user_id)
                    # Raise exception to make Lambda fail
                    # SQS will automatically retry after visibility timeout
                    raise Exception(f'Rate limited. Retry needed: {str(e)}')
                
                # Handle unauthorized - try token refresh
                elif e.status_code == 401:
                    log_warning('Unauthorized, attempting token refresh', user_id=user_id)
                    try:
                        new_token = refresh_user_token(user_id, refresh_token)
                        # Retry with new token
                        presence_data = fetch_spotify_presence(user_id, new_token, refresh_token)
                        if presence_data:
                            save_presence(user_id, spotify_id, presence_data)
                    except Exception as refresh_error:
                        log_error('Token refresh failed', user_id=user_id, error=refresh_error)
                        # Don't retry - likely needs user to re-authenticate
                
                else:
                    # Other API errors - log but don't retry
                    log_error('Spotify API error', user_id=user_id, error=e)
            
            except Exception as e:
                log_error('Error processing message', error=e, message_id=record.get('messageId'))
                # Don't raise - let this message be deleted
        
        return {'statusCode': 200}
        
    except Exception as e:
        log_error('Fatal error in fetch presence handler', error=e)
        # Raise to trigger SQS retry
        raise


def fetch_spotify_presence(user_id: str, access_token: str, refresh_token: str) -> dict:
    """
    Fetch user's current Spotify playback.
    
    Args:
        user_id: User ID
        access_token: Spotify access token
        refresh_token: Spotify refresh token
        
    Returns:
        Presence data or None if nothing playing
        
    Raises:
        SpotifyAPIError: For API errors (especially 429)
    """
    spotify_client = SpotifyClient(access_token=access_token)
    
    try:
        # Get currently playing track
        currently_playing = spotify_client.get_currently_playing()
        
        if currently_playing and currently_playing.get('is_playing'):
            item = currently_playing.get('item', {})
            
            return {
                'isPlaying': True,
                'trackId': item.get('id'),
                'trackName': item.get('name'),
                'artistName': item.get('artists', [{}])[0].get('name'),
                'albumName': item.get('album', {}).get('name'),
                'albumImageUrl': item.get('album', {}).get('images', [{}])[0].get('url') if item.get('album', {}).get('images') else None,
                'progressMs': currently_playing.get('progress_ms'),
                'durationMs': item.get('duration_ms'),
                'timestamp': int(time.time())
            }
        else:
            return None
            
    except SpotifyAPIError:
        # Re-raise Spotify errors for proper handling
        raise


def refresh_user_token(user_id: str, refresh_token: str) -> str:
    """
    Refresh user's Spotify access token.
    
    Args:
        user_id: User ID
        refresh_token: Spotify refresh token
        
    Returns:
        New access token
        
    Raises:
        SpotifyAPIError: If refresh fails
    """
    spotify_client = SpotifyClient()
    token_data = spotify_client.refresh_access_token(refresh_token)
    
    new_access_token = token_data['access_token']
    expires_in = token_data.get('expires_in', 3600)
    
    # Update user's token in database
    update_item(
        USERS_TABLE,
        key={'userId': user_id},
        update_expression='SET spotifyAccessToken = :token, tokenExpiresAt = :expires',
        expression_values={
            ':token': new_access_token,
            ':expires': int(time.time()) + expires_in
        }
    )
    
    log_info('Token refreshed successfully', user_id=user_id)
    
    return new_access_token


def save_presence(user_id: str, spotify_id: str, presence_data: dict):
    """
    Save user presence to DynamoDB.
    
    Args:
        user_id: User ID
        spotify_id: Spotify user ID
        presence_data: Presence data or None
    """
    timestamp = int(time.time())
    ttl = timestamp + (24 * 60 * 60)  # 24 hours TTL
    
    presence_item = {
        'userId': user_id,
        'spotifyId': spotify_id,
        'updatedAt': timestamp,
        'ttl': ttl
    }
    
    if presence_data:
        presence_item.update(presence_data)
        presence_item['isPlaying'] = True
    else:
        presence_item['isPlaying'] = False
    
    put_item(PRESENCE_TABLE, presence_item)



