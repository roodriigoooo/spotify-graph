"""
Internal Lambda (no API Gateway) — invoked asynchronously by UpdateMusicProfileFunction.
Fetches lyrics for recently played tracks in parallel, computes embeddings in one
batched call, averages them, and updates the user's music profile.

Expected payload: {userId: str, tracks: [{id, name, artistName}]}
"""
import os
import time
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

from common.dynamodb_utils import update_item
from common.lyrics_client import fetch_lyrics
from common.embedding_client import get_embeddings_batch, average_embeddings
from common.logger import log_info, log_error, log_warning

MUSIC_PROFILES_TABLE = os.environ.get('MUSIC_PROFILES_TABLE')
HUGGINGFACE_API_KEY = os.environ.get('HUGGINGFACE_API_KEY')
MAX_TRACKS = 20

def _fetch_lyrics_for_track(track):
    lyrics = fetch_lyrics(track.get('name', ''), track.get('artistName', ''))
    return lyrics

def handler(event, context):
    user_id = event.get('userId')
    tracks = event.get('tracks', [])[:MAX_TRACKS]

    if not user_id:
        log_error('compute_lyric_profile called without userId')
        return

    log_info('Starting lyric profile computation', user_id=user_id, track_count=len(tracks))

    update_item(
        MUSIC_PROFILES_TABLE,
        key={'userId': user_id},
        update_expression='SET lyricStatus = :s',
        expression_values={':s': 'pending'}
    )

    try:
        # Fetch lyrics in parallel
        lyrics_list = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_fetch_lyrics_for_track, t): t for t in tracks}
            for future in as_completed(futures):
                track = futures[future]
                lyrics = future.result()
                if lyrics:
                    lyrics_list.append(lyrics)
                else:
                    log_warning('No lyrics', track=track.get('name'), artist=track.get('artistName'))

        if not lyrics_list:
            log_error('No lyrics found for any track', user_id=user_id)
            update_item(
                MUSIC_PROFILES_TABLE,
                key={'userId': user_id},
                update_expression='SET lyricStatus = :s',
                expression_values={':s': 'failed'}
            )
            return

        log_info('Lyrics fetched, computing batch embeddings', user_id=user_id, count=len(lyrics_list))

        # Single batched embedding call
        vectors = get_embeddings_batch(lyrics_list, HUGGINGFACE_API_KEY)

        if not vectors:
            log_error('Batch embedding failed', user_id=user_id)
            update_item(
                MUSIC_PROFILES_TABLE,
                key={'userId': user_id},
                update_expression='SET lyricStatus = :s',
                expression_values={':s': 'failed'}
            )
            return

        lyric_vector = [Decimal(str(v)) for v in average_embeddings(vectors)]

        update_item(
            MUSIC_PROFILES_TABLE,
            key={'userId': user_id},
            update_expression='SET lyricVector = :v, lyricTracksAnalyzed = :c, lyricStatus = :s, lastLyricUpdate = :t',
            expression_values={
                ':v': lyric_vector,
                ':c': len(vectors),
                ':s': 'ready',
                ':t': int(time.time())
            }
        )
        log_info('Lyric profile ready', user_id=user_id, tracks_analyzed=len(vectors))

    except Exception as e:
        log_error('Error computing lyric profile', user_id=user_id, error=str(e))
        update_item(
            MUSIC_PROFILES_TABLE,
            key={'userId': user_id},
            update_expression='SET lyricStatus = :s',
            expression_values={':s': 'failed'}
        )
