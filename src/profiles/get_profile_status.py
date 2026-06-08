"""
GET /me/profile
Returns the current user's music profile metadata (no raw vectors).
"""
import os

from common.dynamodb_utils import get_item
from common.response_utils import success_response, error_response
from common.logger import log_error

MUSIC_PROFILES_TABLE = os.environ.get('MUSIC_PROFILES_TABLE')

def handler(event, context):
    user_id = event.get('requestContext', {}).get('authorizer', {}).get('userId')
    if not user_id:
        return error_response(401, 'Unauthorized')

    try:
        profile = get_item(MUSIC_PROFILES_TABLE, {'userId': user_id})
        if not profile:
            return success_response({'hasProfile': False})

        # Top genres: sort genreVector by weight descending, take top 10
        genre_vector = profile.get('genreVector', {})
        top_genres = sorted(genre_vector.items(), key=lambda x: float(x[1]), reverse=True)[:10]

        # Top 5 artists from medium_term
        top_artists_medium = profile.get('topArtists', {}).get('medium_term', [])
        top_artists_preview = [
            {'id': a['id'], 'name': a['name']}
            for a in top_artists_medium[:5]
        ]

        return success_response({
            'hasProfile': True,
            'lastUpdated': profile.get('lastUpdated'),
            'lyricStatus': profile.get('lyricStatus'),
            'lyricTracksAnalyzed': profile.get('lyricTracksAnalyzed'),
            'lastLyricUpdate': profile.get('lastLyricUpdate'),
            'topGenres': [g for g, _ in top_genres],
            'topArtistsPreview': top_artists_preview
        })

    except Exception as e:
        log_error('Error fetching profile status', user_id=user_id, error=str(e))
        return error_response(500, 'Internal server error')
