import os
import sys
import json
import uuid
import time
import requests
import boto3
import unittest
from botocore.exceptions import ClientError

# Configuration
STACK_NAME = os.environ.get('STACK_NAME', 'spotify-queue-platform')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

def get_stack_output(output_key):
    client = boto3.client('cloudformation', region_name=AWS_REGION)
    try:
        response = client.describe_stacks(StackName=STACK_NAME)
        outputs = response['Stacks'][0]['Outputs']
        for output in outputs:
            if output['OutputKey'] == output_key:
                return output['OutputValue']
    except ClientError:
        return None
    return None

API_URL = get_stack_output('RestApiUrl')
# Ensure trailing slash
if API_URL and not API_URL.endswith('/'):
    API_URL += '/'

class SpotifyQueueIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print(f"Testing against API: {API_URL}")
        if not API_URL:
            raise Exception("Could not find RestApiUrl in stack outputs")

        # Get JWT Token from env or fail
        cls.jwt_token = os.environ.get('JWT_TOKEN')
        if not cls.jwt_token:
             print("WARNING: JWT_TOKEN not set. Some tests will be skipped or fail.")
             # Try to get it from .env if not in env
             try:
                 with open('.env', 'r') as f:
                     for line in f:
                         if line.startswith('JWT_TOKEN='):
                             cls.jwt_token = line.strip().split('=', 1)[1]
                             break
             except:
                 pass
        
        if not cls.jwt_token:
             raise Exception("JWT_TOKEN is required. Please log in via the demo app and export JWT_TOKEN='...'")

        cls.headers = {
            'Authorization': f'Bearer {cls.jwt_token}',
            'Content-Type': 'application/json'
        }
        
        # Setup AWS Clients for verification/setup
        cls.dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        
        # Find table names
        cf = boto3.client('cloudformation', region_name=AWS_REGION)
        resources = cf.describe_stack_resources(StackName=STACK_NAME)
        
        cls.users_table_name = next(r['PhysicalResourceId'] for r in resources['StackResources'] if r['LogicalResourceId'] == 'UsersTable')
        cls.friends_table_name = next(r['PhysicalResourceId'] for r in resources['StackResources'] if r['LogicalResourceId'] == 'FriendsTable')
        cls.queues_table_name = next(r['PhysicalResourceId'] for r in resources['StackResources'] if r['LogicalResourceId'] == 'SharedQueuesTable')
        cls.queue_members_table_name = next(r['PhysicalResourceId'] for r in resources['StackResources'] if r['LogicalResourceId'] == 'QueueMembersTable')

        cls.users_table = cls.dynamodb.Table(cls.users_table_name)
        cls.friends_table = cls.dynamodb.Table(cls.friends_table_name)

        # Ensure the ADMIN user (from JWT) exists in DB
        cls.admin_user_id = 'test-admin-user'
        print(f"Creating/Updating admin user: {cls.admin_user_id}")
        cls.users_table.put_item(Item={
            'userId': cls.admin_user_id,
            'spotifyId': 'spotify-admin',
            'displayName': 'Test Admin',
            'email': 'admin@example.com',
            'visibility': 'friends',
            'createdAt': int(time.time())
        })
        
        # Create a fake second user for testing interactions
        cls.fake_user_id = f"test-user-{str(uuid.uuid4())[:8]}"
        cls.fake_spotify_id = f"spotify-test-{str(uuid.uuid4())[:8]}"
        
        print(f"Creating fake user: {cls.fake_user_id} ({cls.fake_spotify_id})")
        cls.users_table.put_item(Item={
            'userId': cls.fake_user_id,
            'spotifyId': cls.fake_spotify_id,
            'displayName': 'Test User B',
            'email': 'test@example.com',
            'visibility': 'friends',
            'createdAt': int(time.time())
        })
        
    @classmethod
    def tearDownClass(cls):
        # Cleanup fake user
        if hasattr(cls, 'fake_user_id'):
            print(f"Cleaning up fake user: {cls.fake_user_id}")
            cls.users_table.delete_item(Key={'userId': cls.fake_user_id})
            
            # Cleanup friendships
            # (In a real scenario we'd query and delete, but we know what we created)

    def test_01_get_profile(self):
        """Test getting own profile"""
        response = requests.get(f"{API_URL}me", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertIn('spotifyId', data)
        self.my_user_id = data['userId']
        print(f"  My User ID: {self.my_user_id}")

    def test_02_change_visibility(self):
        """Test changing visibility"""
        # Change to private
        response = requests.put(
            f"{API_URL}me/visibility", 
            headers=self.headers,
            json={'visibility': 'private'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['visibility'], 'private')
        
        # Verify in DB
        response = requests.get(f"{API_URL}me", headers=self.headers)
        self.assertEqual(response.json()['data']['visibility'], 'private')
        
        # Change back to friends
        requests.put(
            f"{API_URL}me/visibility", 
            headers=self.headers,
            json={'visibility': 'friends'}
        )

    def test_03_create_queue_validation(self):
        """Test queue creation validation"""
        # Missing name
        response = requests.post(
            f"{API_URL}queues", 
            headers=self.headers,
            json={'description': 'No name'}
        )
        self.assertEqual(response.status_code, 400)

    def test_04_create_queue_success(self):
        """Test successful queue creation"""
        queue_name = f"Test Queue {uuid.uuid4()}"
        response = requests.post(
            f"{API_URL}queues", 
            headers=self.headers,
            json={
                'name': queue_name,
                'description': 'Integration test queue',
                'isPublic': True
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()['data']
        self.assertEqual(data['name'], queue_name)
        self.queue_id = data['queueId']
        
        # Verify owner member created
        # We can verify via API or DB. Let's verify via API get queue
        r2 = requests.get(f"{API_URL}queues/{self.queue_id}", headers=self.headers)
        self.assertEqual(r2.status_code, 200)
        # Note: GetQueue might not return members list depending on implementation
        
    def test_05_add_fake_friend_to_queue(self):
        """Test adding a user to a queue (requires friend logic if we enforce it)"""
        # Current implementation of create_queue doesn't enforce friendship for adding members
        # But let's try to add the fake user to a NEW queue
        
        queue_name = f"Shared Queue {uuid.uuid4()}"
        response = requests.post(
            f"{API_URL}queues", 
            headers=self.headers,
            json={
                'name': queue_name,
                'memberIds': [self.fake_user_id]
            }
        )
        self.assertEqual(response.status_code, 201)
        queue_id = response.json()['data']['queueId']
        
        # Verify in QueueMembersTable directly (since we don't have an API to list members yet?)
        # Or check memberCount in response
        self.assertEqual(response.json()['data']['memberCount'], 2) # Owner + 1

    def test_06_add_nonexistent_user_fails(self):
        """Test adding a non-existent user to a queue fails"""
        response = requests.post(
            f"{API_URL}queues", 
            headers=self.headers,
            json={
                'name': "Bad Queue",
                'memberIds': ["non-existent-user-id-999"]
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Users not found", response.json()['error'])

if __name__ == '__main__':
    unittest.main()

