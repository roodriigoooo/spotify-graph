import os
import json

from common.response_utils import success_response

def handler(event, context):
    """
    Simple health check endpoint.
    Returns 200 OK if the Lambda is reachable.
    """
    return success_response({'status': 'healthy', 'service': 'spotify-queue-platform'})

