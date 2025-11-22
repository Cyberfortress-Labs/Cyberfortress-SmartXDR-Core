"""
Response Caching System for API Optimization
"""
import time
import hashlib
from typing import Optional, Dict, Any


class ResponseCache:
    """Cache API responses to reduce duplicate calls"""
    
    def __init__(self, ttl: int = 3600, enabled: bool = True):
        """
        Initialize response cache
        
        Args:
            ttl: Time-to-live in seconds (default: 3600 = 1 hour)
            enabled: Enable/disable caching (default: True)
        """
        self.ttl = ttl
        self.enabled = enabled
        self.cache: Dict[str, Dict[str, Any]] = {}
    
    def get_cache_key(self, query: str, context_hash: str) -> str:
        """
        Generate cache key from query and context
        
        Args:
            query: User's query string
            context_hash: Hash of the context used
            
        Returns:
            MD5 hash as cache key
        """
        combined = f"{query}:{context_hash}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def get(self, cache_key: str) -> Optional[str]:
        """
        Get cached response if available and not expired
        
        Args:
            cache_key: Cache key to lookup
            
        Returns:
            Cached response or None if not found/expired
        """
        if not self.enabled:
            return None
        
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if time.time() - cached_data['timestamp'] < self.ttl:
                print(f"\nCache hit! Using cached response (saved API call)")
                return cached_data['response']
            else:
                # Expired, remove from cache
                del self.cache[cache_key]
        return None
    
    def set(self, cache_key: str, response: str):
        """
        Cache a response
        
        Args:
            cache_key: Cache key
            response: Response to cache
        """
        if self.enabled:
            self.cache[cache_key] = {
                'response': response,
                'timestamp': time.time()
            }
    
    def clear(self):
        """Clear all cached responses"""
        self.cache.clear()
    
    def clear_expired(self):
        """Remove expired cache entries"""
        now = time.time()
        expired_keys = [
            key for key, data in self.cache.items()
            if now - data['timestamp'] >= self.ttl
        ]
        for key in expired_keys:
            del self.cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            'cache_size': len(self.cache),
            'ttl': self.ttl,
            'enabled': self.enabled
        }
