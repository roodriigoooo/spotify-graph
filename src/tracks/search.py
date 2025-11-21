"""
Search tracks endpoint.
Proxies request to Spotify Search API.
"""
import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.spotify_client import SpotifyClient, SpotifyAPIError
from common.response_utils import success_response, bad_request_response, server_error_response
from common.logger import log_info, log_error
from common.dynamodb_utils import get_item


USERS_TABLE = os.environ.get('USERS_TABLE')


def handler(event, context):
    """
    Search for tracks.
    
    Query parameters:
        q: Search query
        limit: Number of results (default 10)
        
    Returns:
        List of tracks
    """
    try:
        # Extract user ID from authorizer context
        user_id = event['requestContext']['authorizer']['userId']
        
        # Extract query parameters
        query_params = event.get('queryStringParameters') or {}
        query = query_params.get('q')
        limit = int(query_params.get('limit', 10))
        
        if not query:
            return bad_request_response('Search query (q) is required')
            
        log_info('Search tracks', user_id=user_id, query=query)
        
        # Get user tokens
        user = get_item(USERS_TABLE, {'userId': user_id})
        if not user:
            return server_error_response('User not found')
            
        access_token = user.get('spotifyAccessToken')
        
        # Search Spotify
        try:
            client = SpotifyClient(access_token)
            result = client.search(query, type='track', limit=limit)
            
            # Simplify response
            tracks = []
            for item in result.get('tracks', {}).get('items', []):
                # Safely extract artist name
                artists = item.get('artists', [])
                artist_name = artists[0].get('name') if artists else 'Unknown Artist'

                # Safely extract album image
                album = item.get('album', {})
                images = album.get('images', [])
                image_url = images[0].get('url') if images else None

                tracks.append({
                    'trackId': item.get('id'),
                    'trackName': item.get('name'),
                    'artistName': artist_name,
                    'albumName': album.get('name'),
                    'albumImageUrl': image_url,
                    'durationMs': item.get('duration_ms')
                })
                
            return success_response(tracks)
            
        except SpotifyAPIError as e:
            log_error('Spotify API error', error=e)
            return server_error_response(f'Spotify API error: {e.message}')
            
    except Exception as e:
        log_error('Error searching tracks', error=e)
        # Return the actual error message for debugging
        return server_error_response(f'Internal server error: {str(e)}')



