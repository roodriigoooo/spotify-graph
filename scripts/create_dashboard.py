import boto3
import json
import os

REGION = os.environ.get('AWS_REGION', 'us-east-1')
STACK_NAME = os.environ.get('STACK_NAME', 'spotify-queue-platform')

def create_dashboard():
    cw = boto3.client('cloudwatch', region_name=REGION)
    
    # Define dashboard body
    dashboard_body = {
        "widgets": [
            {
                "type": "metric",
                "x": 0,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [ "AWS/ApiGateway", "Count", "ApiName", "SpotifyQueue-RestApi" ],
                        [ "AWS/ApiGateway", "4XXError", "ApiName", "SpotifyQueue-RestApi" ],
                        [ "AWS/ApiGateway", "5XXError", "ApiName", "SpotifyQueue-RestApi" ]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": REGION,
                    "period": 300,
                    "stat": "Sum",
                    "title": "API Gateway Traffic & Errors"
                }
            },
            {
                "type": "metric",
                "x": 12,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [ "AWS/Lambda", "Invocations", "FunctionName", "SpotifyQueue-Authorizer" ],
                        [ ".", "Errors", ".", "." ],
                        [ ".", "Invocations", "FunctionName", "SpotifyQueue-SpotifyAuth" ],
                        [ ".", "Errors", ".", "." ]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": REGION,
                    "title": "Auth Functions Health"
                }
            },
            {
                "type": "metric",
                "x": 0,
                "y": 6,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [ "AWS/Lambda", "Invocations", "FunctionName", "SpotifyQueue-DiscoverActiveUsers" ],
                        [ ".", "Errors", ".", "." ],
                        [ ".", "Invocations", "FunctionName", "SpotifyQueue-FetchPresence" ],
                        [ ".", "Errors", ".", "." ]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": REGION,
                    "title": "Presence Polling Health"
                }
            },
            {
                "type": "metric",
                "x": 12,
                "y": 6,
                "width": 12,
                "height": 6,
                "properties": {
                     "metrics": [
                        [ "AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", "SpotifyQueue-Users" ],
                        [ ".", "ConsumedWriteCapacityUnits", ".", "." ]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": REGION,
                    "title": "DynamoDB Capacity (Users)"
                }
            }
        ]
    }
    
    dashboard_name = f"{STACK_NAME}-Dashboard"
    print(f"Creating dashboard: {dashboard_name}")
    
    cw.put_dashboard(
        DashboardName=dashboard_name,
        DashboardBody=json.dumps(dashboard_body)
    )
    print("Dashboard created successfully")

if __name__ == "__main__":
    create_dashboard()





