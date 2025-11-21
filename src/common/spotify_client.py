"""
Spotify API client for making authenticated requests.
"""
import os
import requests
from typing import Dict, Optional
from requests.exceptions import RequestException


SPOTIFY_API_BASE_URL = 'https://api.spotify.com/v1'
SPOTIFY_ACCOUNTS_BASE_URL = 'https://accounts.spotify.com'


class SpotifyAPIError(Exception):
    """Custom exception for Spotify API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class SpotifyClient:
    """Client for interacting with Spotify API."""
    
    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize Spotify client.
        
        Args:
            access_token: User's Spotify access token
        """
        self.access_token = access_token
        self.client_id = os.environ.get('SPOTIFY_CLIENT_ID')
        self.client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    
    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """
        Get Spotify authorization URL for OAuth flow.
        
        Args:
            redirect_uri: Callback URL
            state: Random state for CSRF protection
            
        Returns:
            Authorization URL
        """
        scopes = [
            'user-read-currently-playing',
            'user-read-playback-state',
            'user-read-recently-played',
            'user-read-email',
            'user-read-private'
        ]
        
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'state': state,
            'scope': ' '.join(scopes),
            'show_dialog': 'false'
        }
        
        query_string = '&'.join([f'{k}={v}' for k, v in params.items()])
        return f'{SPOTIFY_ACCOUNTS_BASE_URL}/authorize?{query_string}'
    
    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from callback
            redirect_uri: Redirect URI used in authorization
            
        Returns:
            Token response with access_token, refresh_token, expires_in
            
        Raises:
            SpotifyAPIError: If token exchange fails
        """
        try:
            response = requests.post(
                f'{SPOTIFY_ACCOUNTS_BASE_URL}/api/token',
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': redirect_uri,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret
                },
                timeout=10
            )
            
            if response.status_code != 200:
                raise SpotifyAPIError(
                    f'Failed to exchange code for token: {response.text}',
                    response.status_code
                )
            
            return response.json()
        except RequestException as e:
            raise SpotifyAPIError(f'Request failed: {str(e)}')
    
    def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh an expired access token.
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            New token response
            
        Raises:
            SpotifyAPIError: If refresh fails
        """
        try:
            response = requests.post(
                f'{SPOTIFY_ACCOUNTS_BASE_URL}/api/token',
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret
                },
                timeout=10
            )
            
            if response.status_code != 200:
                raise SpotifyAPIError(
                    f'Failed to refresh token: {response.text}',
                    response.status_code
                )
            
            return response.json()
        except RequestException as e:
            raise SpotifyAPIError(f'Request failed: {str(e)}')
    
    def get_current_user(self) -> Dict:
        """
        Get current user's profile.
        
        Returns:
            User profile data
            
        Raises:
            SpotifyAPIError: If request fails
        """
        return self._make_request('GET', '/me')
    
    def get_currently_playing(self) -> Optional[Dict]:
        """
        Get user's currently playing track.
        
        Returns:
            Currently playing data or None if nothing playing
            
        Raises:
            SpotifyAPIError: If request fails (except 204)
        """
        try:
            return self._make_request('GET', '/me/player/currently-playing')
        except SpotifyAPIError as e:
            # 204 means nothing is playing
            if e.status_code == 204:
                return None
            raise
    
    def get_recently_played(self, limit: int = 1) -> Dict:
        """
        Get user's recently played tracks.
        
        Args:
            limit: Number of tracks to return
            
        Returns:
            Recently played data
            
        Raises:
            SpotifyAPIError: If request fails
        """
        return self._make_request('GET', f'/me/player/recently-played?limit={limit}')

    def search(self, query: str, type: str = 'track', limit: int = 10) -> Dict:
        """
        Search for items on Spotify.
        
        Args:
            query: Search query
            type: Item type (track, artist, album, playlist)
            limit: Number of results
            
        Returns:
            Search results
        """
        # URL encode query
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        return self._make_request('GET', f'/search?q={encoded_query}&type={type}&limit={limit}')

    def get_top_tracks(self, time_range: str = 'medium_term', limit: int = 20) -> Dict:
        """
        Get user's top tracks.
        
        Args:
            time_range: Over what time frame (short_term, medium_term, long_term)
            limit: Number of results
            
        Returns:
            Top tracks
        """
        return self._make_request('GET', f'/me/top/tracks?time_range={time_range}&limit={limit}')
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """
        Make an authenticated request to Spotify API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Optional request body
            
        Returns:
            Response JSON
            
        Raises:
            SpotifyAPIError: If request fails
        """
        if not self.access_token:
            raise SpotifyAPIError('No access token provided')
        
        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }
        
        url = f'{SPOTIFY_API_BASE_URL}{endpoint}'
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                timeout=10
            )
            
            # Rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After', '60')
                raise SpotifyAPIError(
                    f'Rate limited. Retry after {retry_after} seconds',
                    429
                )
            
            if response.status_code == 401:
                raise SpotifyAPIError('Unauthorized. Token may be expired', 401)
            
            if response.status_code == 204:
                # No content response
                raise SpotifyAPIError('No content', 204)
            
            if response.status_code not in [200, 201]:
                raise SpotifyAPIError(
                    f'Request failed: {response.text}',
                    response.status_code
                )
            
            return response.json()
        except RequestException as e:
            raise SpotifyAPIError(f'Request failed: {str(e)}')



