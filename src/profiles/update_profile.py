"""
POST /me/profile/refresh
Refreshes the current user's music profile by fetching Spotify data, saving
taste data, and asynchronously invoking ComputeLyricProfileFunction.
"""
import os
import json
import time

import boto3
from decimal import Decimal
from common.spotify_client import SpotifyClient, SpotifyAPIError
from common.dynamodb_utils import get_item, put_item, update_item, batch_write_items
from common.similarity import compute_genre_vector
from common.play_events import to_play_events
from common.response_utils import success_response, error_response
from common.logger import log_info, log_error

USERS_TABLE = os.environ.get('USERS_TABLE')
MUSIC_PROFILES_TABLE = os.environ.get('MUSIC_PROFILES_TABLE')
PLAY_EVENTS_TABLE = os.environ.get('PLAY_EVENTS_TABLE')
COMPUTE_LYRIC_FUNCTION_ARN = os.environ.get('COMPUTE_LYRIC_FUNCTION_ARN')

def _get_valid_token(user: dict) -> str:
    """Return a valid access token, refreshing if within 5 minutes of expiry."""
    access_token = user.get('spotifyAccessToken')
    refresh_token = user.get('spotifyRefreshToken')
    token_expires_at = int(user.get('tokenExpiresAt', 0))

    if int(time.time()) >= token_expires_at - 300:
        spotify = SpotifyClient()
        token_data = spotify.refresh_access_token(refresh_token)
        access_token = token_data['access_token']
        expires_in = token_data.get('expires_in', 3600)
        update_item(
            USERS_TABLE,
            key={'userId': user['userId']},
            update_expression='SET spotifyAccessToken = :token, tokenExpiresAt = :exp',
            expression_values={
                ':token': access_token,
                ':exp': int(time.time()) + expires_in
            }
        )

    return access_token

def handler(event, context):
    user_id = event.get('requestContext', {}).get('authorizer', {}).get('userId')
    if not user_id:
        return error_response(401, 'Unauthorized')

    try:
        user = get_item(USERS_TABLE, {'userId': user_id})
        if not user:
            return error_response(404, 'User not found')

        access_token = _get_valid_token(user)
        spotify = SpotifyClient(access_token=access_token)

        # Fetch taste data (8 Spotify API calls)
        ranges = ['long_term', 'medium_term', 'short_term']

        top_artists = {}
        top_tracks = {}
        for r in ranges:
            top_artists[r] = spotify.get_top_artists(time_range=r).get('items', [])
            top_tracks[r] = spotify.get_top_tracks(time_range=r).get('items', [])

        followed_artists = spotify.get_followed_artists()
        recently_played = spotify.get_recently_played(limit=50).get('items', [])

        genre_vector = {k: Decimal(str(v)) for k, v in compute_genre_vector(top_artists).items()}

        # Collect recently played tracks for lyric analysis
        lyric_tracks = []
        seen_ids = set()
        for item in recently_played:
            track = item.get('track', {})
            track_id = track.get('id')
            if track_id and track_id not in seen_ids:
                seen_ids.add(track_id)
                artist_name = (track.get('artists') or [{}])[0].get('name', '')
                lyric_tracks.append({
                    'id': track_id,
                    'name': track.get('name', ''),
                    'artistName': artist_name
                })

        now = int(time.time())
        profile_item = {
            'userId': user_id,
            'topArtists': {
                r: [{'id': a['id'], 'name': a['name'], 'genres': a.get('genres', [])} for a in artists]
                for r, artists in top_artists.items()
            },
            'topTracks': {
                r: [{'id': t['id'], 'name': t['name']} for t in tracks]
                for r, tracks in top_tracks.items()
            },
            'followedArtists': [{'id': a['id'], 'name': a['name']} for a in followed_artists],
            'genreVector': genre_vector,
            'lyricStatus': 'pending',
            'lastUpdated': now
        }

        put_item(MUSIC_PROFILES_TABLE, profile_item)
        log_info('Music profile saved', user_id=user_id)

        # Append to the continuous footprint — only if the user opted in (see
        # set_history_consent). Without consent we store no play history at all.
        if user.get('historyConsent') and PLAY_EVENTS_TABLE:
            written = batch_write_items(
                PLAY_EVENTS_TABLE, to_play_events(recently_played, user_id, now_ts=now))
            log_info('PlayEvents appended', user_id=user_id, rows=written)

        # Invoke lyric computation asynchronously
        lyric_tracks = lyric_tracks[:20]

        if COMPUTE_LYRIC_FUNCTION_ARN and lyric_tracks:
            lambda_client = boto3.client('lambda')
            lambda_client.invoke(
                FunctionName=COMPUTE_LYRIC_FUNCTION_ARN,
                InvocationType='Event',
                Payload=json.dumps({'userId': user_id, 'tracks': lyric_tracks})
            )
            log_info('Lyric compute invoked async', user_id=user_id, track_count=len(lyric_tracks))

        artist_count = sum(len(v) for v in top_artists.values())
        return success_response({
            'message': 'Profile refresh started',
            'lyricStatus': 'pending',
            'lastUpdated': now,
            'artistCount': artist_count,
            'followedArtistCount': len(followed_artists)
        })

    except SpotifyAPIError as e:
        log_error('Spotify API error during profile refresh', user_id=user_id, error=str(e))
        return error_response(502, f'Spotify API error: {e.message}')
    except Exception as e:
        log_error('Error refreshing profile', user_id=user_id, error=str(e))
        return error_response(500, 'Internal server error')
