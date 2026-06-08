"""
PUT /me/history-consent  —  opt in/out of continuous listening-history storage.

Privacy: overlapping echoes only ever stores your play history (the PlayEvents footprint
that powers the recency-weighted taste profile) if you explicitly opt in here. Default is
off. Turning it off stops new ingestion immediately; existing rows also lapse on their own
via the table's TTL.
"""
import os
import json

from common.dynamodb_utils import update_item, get_item
from common.response_utils import (
    success_response,
    bad_request_response,
    not_found_response,
    server_error_response,
)
from common.logger import log_info, log_error

USERS_TABLE = os.environ.get('USERS_TABLE')


def handler(event, context):
    try:
        user_id = event['requestContext']['authorizer']['userId']

        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return bad_request_response('Invalid JSON in request body')

        consent = body.get('historyConsent')
        if not isinstance(consent, bool):
            return bad_request_response('historyConsent (boolean) is required')

        if not get_item(USERS_TABLE, {'userId': user_id}):
            return not_found_response('User not found')

        update_item(
            USERS_TABLE,
            key={'userId': user_id},
            update_expression='SET historyConsent = :c',
            expression_values={':c': consent},
        )
        log_info('History consent updated', user_id=user_id, consent=consent)
        return success_response({'historyConsent': consent})

    except Exception as e:
        log_error('Error updating history consent', error=e)
        return server_error_response('Internal server error')
