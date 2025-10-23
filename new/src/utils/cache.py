"""Simple in-memory cache for deep research files and prompts."""

from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from .logger import get_logger

logger = get_logger(__name__)


class Cache:
    """Simple in-memory cache with TTL support."""
    
    def __init__(self, default_ttl_seconds: int = 3600):
        """
        Initialize cache.
        
        Args:
            default_ttl_seconds: Default time-to-live in seconds
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl_seconds = default_ttl_seconds
    
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """
        Set a cache value.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Optional custom TTL
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        self._cache[key] = {
            "value": value,
            "expires_at": expires_at,
        }
        
        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get a cache value.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        
        # Check if expired
        if datetime.utcnow() > entry["expires_at"]:
            logger.debug(f"Cache expired: {key}")
            del self._cache[key]
            return None
        
        logger.debug(f"Cache hit: {key}")
        return entry["value"]
    
    def delete(self, key: str):
        """Delete a cache entry."""
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Cache deleted: {key}")
    
    def clear(self):
        """Clear all cache entries."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache cleared: {count} entries removed")
    
    def cleanup_expired(self):
        """Remove all expired entries."""
        now = datetime.utcnow()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now > entry["expires_at"]
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            logger.info(f"Cache cleanup: {len(expired_keys)} expired entries removed")


# Global cache instance
_cache = Cache()


def get_cache() -> Cache:
    """Get the global cache instance."""
    return _cache