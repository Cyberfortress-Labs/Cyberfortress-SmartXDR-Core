"""
Redis Client Utility

Provides a singleton Redis client for the application.
Centralizes connection logic and configuration.
"""
import os
import redis
from app.utils.logger import redis_logger as logger
from typing import Optional

class RedisClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._client: Optional[redis.Redis] = None
        self._available = False
        self._init_client()
        self._initialized = True
        
    def _init_client(self):
        """Initialize Redis connection"""
        redis_host = os.getenv("REDIS_HOST")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        
        if redis_host:
            try:
                self._client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=0,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                # Test connection
                self._client.ping()
                self._available = True
                logger.info(f"Redis connected at {redis_host}:{redis_port}")
            except Exception as e:
                logger.warning(f"Redis not available ({e})")
                self._client = None
                self._available = False
        else:
            logger.info("Redis not configured (REDIS_HOST not set)")
            
    @property
    def client(self) -> Optional[redis.Redis]:
        """Get the underlying redis client"""
        return self._client
        
    @property
    def available(self) -> bool:
        """Check if Redis is available"""
        return self._available

# Global instance
_redis_client = RedisClient()

def get_redis_client() -> RedisClient:
    """Get the global Redis client wrapper implementation"""
    return _redis_client

def get_redis_connection() -> Optional[redis.Redis]:
    """Get the raw Redis connection (shorthand)"""
    return _redis_client.client
