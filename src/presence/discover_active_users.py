"""
Discover active users Lambda.
Triggered by EventBridge scheduler to find users that need presence polling.
Sends user IDs to SQS queue for parallel processing.
"""
import os
import sys
import json
import time
import boto3
from boto3.dynamodb.conditions import Key

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.dynamodb_utils import scan_items, query_items, batch_get_items
from common.logger import log_info, log_error


USERS_TABLE = os.environ.get('USERS_TABLE')
PRESENCE_POLL_QUEUE_URL = os.environ.get('PRESENCE_POLL_QUEUE_URL')
QUEUE_MEMBERS_TABLE = os.environ.get('QUEUE_MEMBERS_TABLE')
SHARED_QUEUES_TABLE = os.environ.get('SHARED_QUEUES_TABLE')
FRIENDS_TABLE = os.environ.get('FRIENDS_TABLE')
RECENT_ACTIVITY_INDEX = 'RecentActivityIndex'
SHAREABLE_VISIBILITIES = ['public', 'friends']

sqs = boto3.client('sqs')


def handler(event, context):
    """
    Discover users who need presence polling and queue them for processing.
    
    Strategy:
    - Find users who have connected recently (within last 30 minutes)
    - Find users who have visibility set to 'friends' or 'public'
    - Send each user ID to SQS for parallel processing by fetch-presence Lambda
    
    Returns:
        Summary of queued users
    """
    try:
        log_info('Discover active users triggered')
        
        # Calculate cutoff time (7 days ago)
        cutoff_time = int(time.time()) - (7 * 24 * 60 * 60)
        
        recent_users = []
        for visibility in SHAREABLE_VISIBILITIES:
            key_condition = Key('visibility').eq(visibility) & Key('lastLogin').gt(cutoff_time)
            recent_users.extend(
                query_items(
                    USERS_TABLE,
                    key_condition=key_condition,
                    index_name=RECENT_ACTIVITY_INDEX
                )
            )

        user_map = {user['userId']: user for user in recent_users}
        
        def user_shareable(user):
            return user and user.get('visibility', 'friends') != 'private'
        
        active_user_ids = {user['userId'] for user in recent_users}
        
        # Include queue owners and members (anyone collaborating in a session)
        queues = scan_items(SHARED_QUEUES_TABLE)
        for queue in queues:
            owner_id = queue.get('ownerId')
            if owner_id:
                active_user_ids.add(owner_id)
        
        queue_members = scan_items(QUEUE_MEMBERS_TABLE)
        for member in queue_members:
            uid = member.get('userId')
            if uid:
                active_user_ids.add(uid)
        
        # Include friends of active people so their playback shows up together
        friends = scan_items(FRIENDS_TABLE)
        for relation in friends:
            if relation.get('userId'):
                active_user_ids.add(relation['userId'])
            if relation.get('friendId'):
                active_user_ids.add(relation['friendId'])
        
        missing_user_ids = [uid for uid in active_user_ids if uid not in user_map]
        if missing_user_ids:
            batch_size = 100
            for i in range(0, len(missing_user_ids), batch_size):
                chunk = missing_user_ids[i:i + batch_size]
                keys = [{'userId': uid} for uid in chunk]
                for user in batch_get_items(USERS_TABLE, keys):
                    user_map[user['userId']] = user

        # Filter users that are shareable (non-private and known)
        active_users = []
        for uid in list(active_user_ids):
            user = user_map.get(uid)
            if user_shareable(user):
                active_users.append(user)
            else:
                active_user_ids.discard(uid)
        
        log_info(f'Found {len(active_users)} active users to poll')
        
        # Send messages to SQS queue (one message per user)
        queued_count = 0
        failed_count = 0
        
        for user in active_users:
            try:
                # SECURITY: Only send identifiers, not tokens
                message_body = {
                    'userId': user['userId'],
                    'spotifyId': user['spotifyId']
                }
                
                sqs.send_message(
                    QueueUrl=PRESENCE_POLL_QUEUE_URL,
                    MessageBody=json.dumps(message_body),
                    MessageAttributes={
                        'userId': {
                            'StringValue': user['userId'],
                            'DataType': 'String'
                        }
                    }
                )
                
                queued_count += 1
                
            except Exception as e:
                log_error(f'Failed to queue user {user["userId"]}', error=e)
                failed_count += 1
        
        log_info('Discover active users completed',
                recent_shareable=len(recent_users),
                active_users=len(active_users),
                queued=queued_count,
                failed=failed_count)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'recentShareableUsers': len(recent_users),
                'activeUsers': len(active_users),
                'queued': queued_count,
                'failed': failed_count
            })
        }
        
    except Exception as e:
        log_error('Error in discover active users', error=e)
        raise



