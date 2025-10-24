"""
Redis-based proxy token storage
Shared between Flask app and Celery workers
"""
import redis
import json
import hashlib
import os
from datetime import datetime, timedelta
from config import config
import logging

logger = logging.getLogger(__name__)

# Connect to Redis
redis_client = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)

def create_proxy_url(private_url, url_type="image", expiration_minutes=30):
    """
    Create a temporary public URL for a private image
    Stores token in Redis so both Flask and Celery can access it
    """
    try:
        # Generate unique token
        token_data = f"{private_url}{datetime.now()}{os.urandom(16)}"
        token = hashlib.sha256(token_data.encode()).hexdigest()[:32]
        
        # Prepare token data
        token_info = {
            'url': private_url,
            'type': url_type,
            'created': datetime.now().isoformat()
        }
        
        # Store in Redis with automatic expiration
        redis_key = f"proxy_token:{token}"
        redis_client.setex(
            redis_key,
            timedelta(minutes=expiration_minutes),
            json.dumps(token_info)
        )
        
        logger.info(f"🔑 Created proxy token {token[:8]}... (expires in {expiration_minutes}m)")
        
        # Get base URL from config
        proxy_base = config.PROXY_BASE_URL
        return f"{proxy_base}/proxy/image/{token}"
        
    except Exception as e:
        logger.error(f"❌ Error creating proxy token: {e}")
        raise

def get_proxy_token_data(token):
    """
    Get data for a proxy token from Redis
    Returns dict with 'url', 'type', 'created', 'expires'
    """
    try:
        redis_key = f"proxy_token:{token}"
        data = redis_client.get(redis_key)
        
        if not data:
            logger.warning(f"⚠️ Token {token[:8]}... not found in Redis")
            return None
        
        # Parse the stored JSON
        token_info = json.loads(data)
        
        # Get TTL to calculate expiration
        ttl = redis_client.ttl(redis_key)
        if ttl > 0:
            token_info['expires'] = datetime.now() + timedelta(seconds=ttl)
        else:
            # Token exists but has no expiration (shouldn't happen) or is expired
            token_info['expires'] = datetime.now()
        
        logger.debug(f"✅ Token {token[:8]}... found, expires in {ttl}s")
        return token_info
        
    except Exception as e:
        logger.error(f"❌ Error getting token data: {e}")
        return None

def delete_proxy_token(token):
    """
    Manually delete a token (optional - Redis auto-expires them)
    """
    try:
        redis_key = f"proxy_token:{token}"
        deleted = redis_client.delete(redis_key)
        if deleted:
            logger.info(f"🗑️ Deleted token {token[:8]}...")
        return deleted > 0
    except Exception as e:
        logger.error(f"❌ Error deleting token: {e}")
        return False

def get_proxy_stats():
    """
    Get statistics about proxy tokens
    """
    try:
        # Find all proxy tokens
        keys = redis_client.keys("proxy_token:*")
        
        if not keys:
            return {
                "total_tokens": 0,
                "active_tokens": 0,
                "expired_tokens": 0
            }
        
        # Count active vs expired
        active = 0
        expired = 0
        
        for key in keys:
            ttl = redis_client.ttl(key)
            if ttl > 0:
                active += 1
            else:
                expired += 1
        
        return {
            "total_tokens": len(keys),
            "active_tokens": active,
            "expired_tokens": expired
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting proxy stats: {e}")
        return {
            "total_tokens": 0,
            "active_tokens": 0,
            "error": str(e)
        }

def cleanup_expired_tokens():
    """
    Manual cleanup of expired tokens (Redis does this automatically, but this can be called explicitly)
    """
    try:
        keys = redis_client.keys("proxy_token:*")
        cleaned = 0
        
        for key in keys:
            ttl = redis_client.ttl(key)
            if ttl <= 0:  # Expired or no expiration set
                redis_client.delete(key)
                cleaned += 1
        
        if cleaned > 0:
            logger.info(f"🧹 Cleaned up {cleaned} expired tokens")
        
        return cleaned
        
    except Exception as e:
        logger.error(f"❌ Error during cleanup: {e}")
        return 0