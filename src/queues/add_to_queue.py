"""
Add track to shared queue endpoint.
"""
import os
import sys
import json
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import get_item, update_item
from common.response_utils import (
    success_response,
    bad_request_response,
    not_found_response,
    forbidden_response,
    server_error_response
)
from common.logger import log_info, log_error


SHARED_QUEUES_TABLE = os.environ.get('SHARED_QUEUES_TABLE')
QUEUE_MEMBERS_TABLE = os.environ.get('QUEUE_MEMBERS_TABLE')


def handler(event, context):
    """
    Add a track to a shared queue.
    
    Path parameter:
        queueId: ID of the queue
    
    Request body:
        {
            "trackId": "spotify_track_id",
            "trackName": "Track Name",
            "artistName": "Artist Name",
            "albumName": "Album Name",
            "albumImageUrl": "https://...",
            "durationMs": 180000
        }
    
    Returns:
        Updated queue
    """
    try:
        # Extract user ID from authorizer context
        user_id = event['requestContext']['authorizer']['userId']
        
        # Extract queue ID from path parameters
        queue_id = event['pathParameters'].get('queueId')
        
        if not queue_id:
            return not_found_response('Queue ID is required')
        
        log_info('Add to queue request', queue_id=queue_id, user_id=user_id)
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return bad_request_response('Invalid JSON in request body')
        
        track_id = body.get('trackId')
        track_name = body.get('trackName')
        artist_name = body.get('artistName')
        album_name = body.get('albumName')
        album_image_url = body.get('albumImageUrl')
        duration_ms = body.get('durationMs')
        
        # Validate required fields
        if not track_id or not track_name:
            return bad_request_response('trackId and trackName are required')
        
        # Get queue
        queue = get_item(SHARED_QUEUES_TABLE, {'queueId': queue_id})
        
        if not queue:
            return not_found_response('Queue not found')
        
        # Check if user is a member of the queue
        membership = get_item(
            QUEUE_MEMBERS_TABLE,
            {'queueId': queue_id, 'userId': user_id}
        )
        
        if not membership and not queue.get('isPublic', False):
            return forbidden_response('You are not a member of this queue')
        
        # Create track object
        timestamp = int(time.time())
        track = {
            'trackId': track_id,
            'trackName': track_name,
            'artistName': artist_name or 'Unknown Artist',
            'albumName': album_name or '',
            'albumImageUrl': album_image_url or '',
            'durationMs': duration_ms or 0,
            'addedBy': user_id,
            'addedAt': timestamp
        }
        
        # Get current tracks
        current_tracks = queue.get('tracks', [])
        
        # Add new track
        current_tracks.append(track)
        
        # Update queue with new track
        # Using DynamoDB's list_append to add to tracks array
        from common.dynamodb_utils import get_table
        table = get_table(SHARED_QUEUES_TABLE)
        
        response = table.update_item(
            Key={'queueId': queue_id},
            UpdateExpression='SET tracks = :tracks, updatedAt = :updated',
            ExpressionAttributeValues={
                ':tracks': current_tracks,
                ':updated': timestamp
            },
            ReturnValues='ALL_NEW'
        )
        
        updated_queue = response.get('Attributes', {})
        
        log_info('Track added to queue successfully',
                queue_id=queue_id,
                track_id=track_id,
                user_id=user_id)
        
        return success_response(
            {
                'queueId': queue_id,
                'tracks': updated_queue.get('tracks', []),
                'updatedAt': updated_queue.get('updatedAt')
            },
            'Track added to queue successfully'
        )
        
    except KeyError as e:
        log_error('Missing required field', error=e)
        return server_error_response('Invalid request context')
    except Exception as e:
        log_error('Error adding track to queue', error=e)
        return server_error_response('Failed to add track to queue')



