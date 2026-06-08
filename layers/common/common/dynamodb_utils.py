"""
DynamoDB utility functions for common database operations.
"""
import os
import boto3
from typing import Dict, List, Optional, Any
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError


dynamodb = boto3.resource('dynamodb')


def get_table(table_name: str):
    """Get a DynamoDB table resource."""
    return dynamodb.Table(table_name)


def put_item(table_name: str, item: Dict, condition_expression: Optional[str] = None) -> bool:
    """
    Put an item into a DynamoDB table.
    
    Args:
        table_name: Name of the table
        item: Item to put
        condition_expression: Optional condition expression
        
    Returns:
        True if successful, False otherwise
    """
    try:
        table = get_table(table_name)
        params = {'Item': item}
        
        if condition_expression:
            params['ConditionExpression'] = condition_expression
        
        table.put_item(**params)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return False
        raise


def get_item(table_name: str, key: Dict) -> Optional[Dict]:
    """
    Get an item from a DynamoDB table.
    
    Args:
        table_name: Name of the table
        key: Primary key of the item
        
    Returns:
        Item if found, None otherwise
    """
    try:
        table = get_table(table_name)
        response = table.get_item(Key=key)
        return response.get('Item')
    except ClientError:
        return None


def update_item(
    table_name: str,
    key: Dict,
    update_expression: str,
    expression_values: Dict,
    expression_names: Optional[Dict] = None,
    condition_expression: Optional[str] = None
) -> bool:
    """
    Update an item in a DynamoDB table.
    
    Args:
        table_name: Name of the table
        key: Primary key of the item
        update_expression: Update expression
        expression_values: Expression attribute values
        expression_names: Optional expression attribute names
        condition_expression: Optional condition expression
        
    Returns:
        True if successful, False otherwise
    """
    try:
        table = get_table(table_name)
        params = {
            'Key': key,
            'UpdateExpression': update_expression,
            'ExpressionAttributeValues': expression_values,
        }
        
        if expression_names:
            params['ExpressionAttributeNames'] = expression_names
        
        if condition_expression:
            params['ConditionExpression'] = condition_expression
        
        table.update_item(**params)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return False
        raise


def delete_item(table_name: str, key: Dict, condition_expression: Optional[str] = None) -> bool:
    """
    Delete an item from a DynamoDB table.
    
    Args:
        table_name: Name of the table
        key: Primary key of the item
        condition_expression: Optional condition expression
        
    Returns:
        True if successful, False otherwise
    """
    try:
        table = get_table(table_name)
        params = {'Key': key}
        
        if condition_expression:
            params['ConditionExpression'] = condition_expression
        
        table.delete_item(**params)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return False
        raise


def query_items(
    table_name: str,
    key_condition: Any,
    index_name: Optional[str] = None,
    filter_expression: Optional[Any] = None,
    limit: Optional[int] = None
) -> List[Dict]:
    """
    Query items from a DynamoDB table.
    
    Args:
        table_name: Name of the table
        key_condition: Key condition expression
        index_name: Optional GSI name
        filter_expression: Optional filter expression
        limit: Optional result limit
        
    Returns:
        List of items
    """
    try:
        table = get_table(table_name)
        params = {'KeyConditionExpression': key_condition}
        
        if index_name:
            params['IndexName'] = index_name
        
        if filter_expression:
            params['FilterExpression'] = filter_expression
        
        if limit:
            params['Limit'] = limit
        
        response = table.query(**params)
        return response.get('Items', [])
    except ClientError:
        return []


def scan_items(
    table_name: str,
    filter_expression: Optional[Any] = None,
    limit: Optional[int] = None
) -> List[Dict]:
    """
    Scan items from a DynamoDB table.
    
    Args:
        table_name: Name of the table
        filter_expression: Optional filter expression
        limit: Optional result limit
        
    Returns:
        List of items
    """
    try:
        table = get_table(table_name)
        params = {}
        
        if filter_expression:
            params['FilterExpression'] = filter_expression
        
        if limit:
            params['Limit'] = limit
        
        response = table.scan(**params)
        items = response.get('Items', [])
        
        # Handle pagination if no limit specified
        while 'LastEvaluatedKey' in response and not limit:
            params['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = table.scan(**params)
            items.extend(response.get('Items', []))
        
        return items
    except ClientError:
        return []


def batch_get_items(table_name: str, keys: List[Dict]) -> List[Dict]:
    """
    Batch get items from a DynamoDB table.
    
    Args:
        table_name: Name of the table
        keys: List of primary keys
        
    Returns:
        List of items
    """
    if not keys:
        return []
    
    try:
        response = dynamodb.batch_get_item(
            RequestItems={
                table_name: {
                    'Keys': keys
                }
            }
        )
        return response.get('Responses', {}).get(table_name, [])
    except ClientError:
        return []


def transact_write_items(items: List[Dict]) -> bool:
    """
    Execute a transaction with multiple write operations.
    
    Args:
        items: List of transaction items
        
    Returns:
        True if successful, False otherwise
    """
    try:
        dynamodb_client = boto3.client('dynamodb')
        dynamodb_client.transact_write_items(TransactItems=items)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'TransactionCanceledException':
            return False
        raise



