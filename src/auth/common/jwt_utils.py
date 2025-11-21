"""
JWT utility functions for token generation and validation.
"""
import os
import jwt
import time
from typing import Dict, Optional


JWT_SECRET = os.environ.get('JWT_SECRET')
JWT_ALGORITHM = 'HS256'
TOKEN_EXPIRY_HOURS = 24 * 7  # 7 days


def generate_token(user_id: str, spotify_id: str) -> str:
    """
    Generate a JWT token for a user.
    
    Args:
        user_id: Internal user ID
        spotify_id: Spotify user ID
        
    Returns:
        JWT token string
    """
    now = int(time.time())
    payload = {
        'userId': user_id,
        'spotifyId': spotify_id,
        'iat': now,
        'exp': now + (TOKEN_EXPIRY_HOURS * 3600)
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload if valid, None otherwise
    """
    try:
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def extract_user_from_token(token: str) -> Optional[str]:
    """
    Extract user ID from JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        User ID if valid, None otherwise
    """
    payload = decode_token(token)
    if payload:
        return payload.get('userId')
    return None



