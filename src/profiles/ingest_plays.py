"""
IngestPlays — append each user's recent listening to PlayEvents (taste-engine v2 footprint).

Two entry points share one body:
  - EventBridge schedule (no userId in the event): walk every consenting user.
  - Direct/async invoke with {"userId": ...}: just that user.

Consent is mandatory: a user's plays are only ever stored if they set `historyConsent`
(see set_history_consent). No consent -> we skip them entirely. Rows self-expire via TTL.
"""
import os
import time
from typing import Optional

from boto3.dynamodb.conditions import Attr

from common.dynamodb_utils import get_item, update_item, scan_items, batch_write_items
from common.spotify_client import SpotifyClient, SpotifyAPIError
from common.play_events import to_play_events
from common.logger import log_info, log_error
from common.response_utils import success_response, error_response

USERS_TABLE = os.environ.get('USERS_TABLE')
PLAY_EVENTS_TABLE = os.environ.get('PLAY_EVENTS_TABLE')

# Cap the scheduled sweep so one run can't blow the timeout / Spotify rate limits.
MAX_USERS_PER_RUN = 100


def _valid_access_token(user: dict) -> str:
    """Return a usable access token, refreshing + persisting it if near expiry."""
    access_token = user.get('spotifyAccessToken')
    refresh_token = user.get('spotifyRefreshToken')
    expires_at = int(user.get('tokenExpiresAt', 0))
    if int(time.time()) >= expires_at - 300:
        token_data = SpotifyClient().refresh_access_token(refresh_token)
        access_token = token_data['access_token']
        update_item(
            USERS_TABLE,
            key={'userId': user['userId']},
            update_expression='SET spotifyAccessToken = :t, tokenExpiresAt = :e',
            expression_values={':t': access_token,
                               ':e': int(time.time()) + token_data.get('expires_in', 3600)},
        )
    return access_token


def ingest_user(user: dict, now_ts: Optional[float] = None) -> int:
    """
    Pull a user's recently-played and append them to PlayEvents. Returns rows written.
    Returns 0 (and writes nothing) if the user hasn't consented to history storage.
    """
    if not user or not user.get('historyConsent'):
        return 0
    access_token = _valid_access_token(user)
    spotify = SpotifyClient(access_token=access_token)
    items = spotify.get_recently_played(limit=50).get('items', [])
    rows = to_play_events(items, user['userId'], now_ts=now_ts)
    return batch_write_items(PLAY_EVENTS_TABLE, rows)


def handler(event, context):
    event = event or {}
    user_id = event.get('userId') or \
        event.get('requestContext', {}).get('authorizer', {}).get('userId')

    try:
        if user_id:
            user = get_item(USERS_TABLE, {'userId': user_id})
            written = ingest_user(user)
            log_info('Ingested plays', user_id=user_id, rows=written)
            return success_response({'userId': user_id, 'eventsWritten': written})

        # Scheduled sweep: every consenting user.
        users = scan_items(
            USERS_TABLE,
            filter_expression=Attr('historyConsent').eq(True),
            limit=MAX_USERS_PER_RUN,
        )
        total = 0
        for user in users:
            try:
                total += ingest_user(user)
            except SpotifyAPIError as e:
                log_error('Ingest skipped (Spotify)', user_id=user.get('userId'), error=e)
        log_info('Scheduled ingest complete', users=len(users), rows=total)
        return success_response({'users': len(users), 'eventsWritten': total})

    except SpotifyAPIError as e:
        log_error('Ingest failed (Spotify)', user_id=user_id, error=e)
        return error_response(502, f'Spotify API error: {e.message}')
    except Exception as e:
        log_error('Ingest failed', user_id=user_id, error=e)
        return error_response(500, 'Internal server error')
