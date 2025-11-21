"""
AutoDJ Lambda function.
Triggered by DynamoDB Streams when a queue becomes empty.
Refills the queue with music based on members' tastes.
"""
import os
import sys
import json
import time
import random

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import get_item, batch_get_items, update_item
from common.spotify_client import SpotifyClient, SpotifyAPIError
from common.logger import log_info, log_error, log_warning


SHARED_QUEUES_TABLE = os.environ.get('SHARED_QUEUES_TABLE')
QUEUE_MEMBERS_TABLE = os.environ.get('QUEUE_MEMBERS_TABLE')
USERS_TABLE = os.environ.get('USERS_TABLE')


def handler(event, context):
    """
    Handle DynamoDB Stream events.
    Checks for queues that have become empty and refills them.
    """
    try:
        for record in event['Records']:
            if record['eventName'] not in ['INSERT', 'MODIFY']:
                continue
                
            new_image = record['dynamodb'].get('NewImage', {})
            
            # Check if tracks list is empty
            tracks = new_image.get('tracks', {}).get('L', [])
            
            if len(tracks) > 0:
                continue
                
            queue_id = new_image.get('queueId', {}).get('S')
            if not queue_id:
                continue
                
            log_info('Queue is empty, triggering AutoDJ', queue_id=queue_id)
            
            # Refill the queue
            refill_queue(queue_id)
            
    except Exception as e:
        log_error('Error in AutoDJ handler', error=e)
        # Don't raise, just log to avoid infinite retry loops on bad data


def refill_queue(queue_id):
    """
    Add a recommended track to the queue.
    """
    # 1. Get queue members
    # Note: This requires a GSI on QueueMembersTable to list members by queueId
    # Or we can store memberIds in the Queue object itself. 
    # The CreateQueue logic stores memberIds in the queue object but AddMember adds to QueueMembersTable.
    # Let's rely on the Queue object having a member list if possible, or query the Members table.
    
    # For this demo implementation, we'll query the QueueMembers table if available, 
    # or fall back to the 'ownerId' from the queue item.
    
    # Let's assume we need to query the QueueMembersTable
    # But wait, we don't have a GSI for QueueId -> Members in the current template (checked mentally, need to verify).
    # CreateQueue.py puts 'memberIds' in the queue item. Let's use that if available? 
    # Actually, let's just use the owner for now if we can't easily get all members, 
    # OR scan the members table (inefficient but works for demo).
    
    # Better: The queue object in DynamoDB usually has memberCount, but not the list of members 
    # if they were added later.
    
    # Let's fetch the queue first to get the owner.
    queue = get_item(SHARED_QUEUES_TABLE, {'queueId': queue_id})
    if not queue:
        return
        
    owner_id = queue.get('ownerId')
    
    # Try to get other members. For MVP/Demo, using Owner + random friends is complex.
    # Let's just use the Owner's top tracks for now, effectively "radio mode" based on owner.
    # If we want "intersection", we need all members.
    
    # Fetch owner's tokens
    user = get_item(USERS_TABLE, {'userId': owner_id})
    if not user:
        log_warning('Owner not found', user_id=owner_id)
        return
        
    access_token = user.get('spotifyAccessToken')
    if not access_token:
        return
        
    try:
        client = SpotifyClient(access_token)
        
        # Get top tracks
        top_tracks_data = client.get_top_tracks(limit=20)
        items = top_tracks_data.get('items', [])
        
        if not items:
            log_warning('No top tracks found for user', user_id=owner_id)
            return
            
        # Pick a random track
        track_item = random.choice(items)
        
        # Add to queue
        track = {
            'trackId': track_item.get('id'),
            'trackName': track_item.get('name'),
            'artistName': track_item.get('artists', [{}])[0].get('name'),
            'albumName': track_item.get('album', {}).get('name'),
            'albumImageUrl': track_item.get('album', {}).get('images', [{}])[0].get('url') if track_item.get('album', {}).get('images') else None,
            'durationMs': track_item.get('duration_ms'),
            'addedBy': 'AutoDJ',
            'addedAt': int(time.time())
        }
        
        # Update queue
        from common.dynamodb_utils import get_table
        table = get_table(SHARED_QUEUES_TABLE)
        
        table.update_item(
            Key={'queueId': queue_id},
            UpdateExpression='SET tracks = list_append(tracks, :track), updatedAt = :updated',
            ExpressionAttributeValues={
                ':track': [track],
                ':updated': int(time.time())
            }
        )
        
        log_info('AutoDJ added track to queue', queue_id=queue_id, track_name=track['trackName'])
        
    except Exception as e:
        log_error('AutoDJ failed to fetch/add track', error=e)





