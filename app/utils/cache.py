"""
Response Caching System for API Optimization
"""
import time
import hashlib
import re
import os
import numpy as np
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try to import OpenAI for embedding similarity matching
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class ResponseCache:
    """Cache API responses with semantic similarity matching"""
    
    def __init__(self, ttl: int = 3600, enabled: bool = True, use_semantic_cache: bool = False):
        """
        Initialize response cache
        
        Args:
            ttl: Time-to-live in seconds (default: 3600 = 1 hour)
            enabled: Enable/disable caching (default: True)
            use_semantic_cache: Use embedding similarity for cache lookup (default: False)
        """
        self.ttl = ttl
        self.enabled = enabled
        self.use_semantic_cache = use_semantic_cache and OPENAI_AVAILABLE
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.similarity_threshold = 0.85  # 85% similarity = cache hit
        
        # Initialize OpenAI client if semantic cache is enabled
        if self.use_semantic_cache:
            try:
                self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                self.embedding_model = "text-embedding-3-small"
                print("✓ Semantic cache enabled (embedding-based similarity matching)")
            except Exception as e:
                print(f"⚠ Semantic cache initialization failed: {e}")
                self.use_semantic_cache = False
    
    def _normalize_query(self, query: str) -> str:
        """
        Normalize query for better cache hit rate.
        Removes variations in phrasing that don't change semantic meaning.
        
        Args:
            query: Original query string
            
        Returns:
            Normalized query string
        """
        # Convert to lowercase
        normalized = query.lower().strip()
        
        # Remove punctuation at the end (?, !, .)
        normalized = re.sub(r'[?!.]+$', '', normalized)
        
        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Extract key entities first (IP addresses)
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ips = re.findall(ip_pattern, normalized)
        
        # Normalize question patterns (Vietnamese) - same meaning, different phrasing
        patterns = [
            (r'là của máy nào', 'máy_nào'),
            (r'thuộc máy nào', 'máy_nào'),
            (r'là của thiết bị nào', 'thiết_bị_nào'),
            (r'thuộc thiết bị nào', 'thiết_bị_nào'),
            (r'là máy nào', 'máy_nào'),
            (r'là thiết bị nào', 'thiết_bị_nào'),
            (r'là của gì', 'máy_nào'),
            (r'tên máy', 'máy_nào'),
            (r'của máy gì', 'máy_nào'),
            (r'thuộc về máy', 'máy_nào'),
            (r'belongs to which', 'máy_nào'),
            (r'is assigned to', 'máy_nào'),
            (r'what device has', 'máy_nào'),
            (r'what machine has', 'máy_nào'),
            (r'which device has', 'máy_nào'),
            (r'which machine has', 'máy_nào'),
        ]
        
        for pattern, replacement in patterns:
            normalized = re.sub(pattern, replacement, normalized)
        
        # Remove common filler words that don't change meaning
        filler_words = [
            # Vietnamese
            'là', 'của', 'thuộc', 'về', 'cho', 'nào', 'gì', 'vậy', 'thế', 'nhỉ', 'nhé', 'ạ',
            'có', 'cái', 'chiếc', 'tên', 'được', 'sẽ', 'đã', 'đang', 'hãy', 'hành', 'em', 'anh',
            # English  
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'which', 'whose', 'am', 'be',
            'please', 'tell', 'me', 'can', 'you', 'ip', 'máy', 'address', 'device', 'machine',
            'has', 'have', 'does', 'do', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
        ]
        
        words = normalized.split()
        # Keep words that are: IP addresses, normalized patterns, or not filler words
        important_words = []
        for word in words:
            is_ip = re.match(ip_pattern, word)
            is_normalized_pattern = '_' in word  # Our normalized patterns have underscore
            is_important = word not in filler_words and len(word) > 0
            if is_ip or is_normalized_pattern or is_important:
                important_words.append(word)
        
        # Remove redundant máy_nào and thiết_bị_nào patterns if IP is present
        # (they're implied by the question context and vary too much)
        if ips:
            important_words = [w for w in important_words if w not in ('máy_nào', 'thiết_bị_nào')]
        
        # Rebuild with IPs first for consistency
        result_parts = []
        for ip in sorted(set(ips)):
            result_parts.append(ip)
        for word in important_words:
            if not re.match(ip_pattern, word):
                result_parts.append(word)
        
        return ' '.join(result_parts).strip()
    
    def _get_embedding(self, text: str) -> Optional[list]:
        """Get embedding for text using OpenAI API"""
        if not self.use_semantic_cache:
            return None
        
        try:
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"⚠ Failed to get embedding: {e}")
            return None
    
    def _cosine_similarity(self, vec1: list, vec2: list) -> float:
        """Calculate cosine similarity between two vectors"""
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    
    def _find_similar_cached_query(self, query_embedding: list) -> Tuple[Optional[str], float]:
        """Find cached query with highest similarity to current query"""
        best_match_key = None
        best_similarity = 0.0
        
        for cache_key, cache_data in self.cache.items():
            if 'query_embedding' in cache_data:
                similarity = self._cosine_similarity(query_embedding, cache_data['query_embedding'])
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_key = cache_key
        
        if best_similarity >= self.similarity_threshold:
            return best_match_key, best_similarity
        return None, 0.0
    
    def get_cache_key(self, query: str, context_hash: str) -> str:
        """
        Generate cache key from normalized query and context
        
        Args:
            query: User's query string
            context_hash: Hash of the context used
            
        Returns:
            SHA256 hash as cache key
        """
        normalized_query = self._normalize_query(query)
        combined = f"{normalized_query}:{context_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def get(self, cache_key: str, query: Optional[str] = None) -> Optional[str]:
        """
        Get cached response if available and not expired
        Supports both exact match and semantic similarity matching
        
        Args:
            cache_key: Cache key to lookup
            query: Original query string (for semantic matching)
            
        Returns:
            Cached response or None if not found/expired
        """
        if not self.enabled:
            return None
        
        # Try exact cache key match first (fastest)
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if time.time() - cached_data['timestamp'] < self.ttl:
                print(f"\n✓ Cache hit! (exact match - saved API call)")
                return cached_data['response']
            else:
                # Expired, remove from cache
                del self.cache[cache_key]
        
        # Try semantic similarity matching if enabled and query provided
        if self.use_semantic_cache and query:
            query_embedding = self._get_embedding(query)
            if query_embedding:
                similar_key, similarity = self._find_similar_cached_query(query_embedding)
                if similar_key:
                    cached_data = self.cache[similar_key]
                    if time.time() - cached_data['timestamp'] < self.ttl:
                        print(f"\n✓ Cache hit! (semantic match {similarity:.1%} - saved API call)")
                        return cached_data['response']
                    else:
                        del self.cache[similar_key]
        
        return None
    
    def set(self, cache_key: str, response: str, query: Optional[str] = None):
        """
        Cache a response with optional query embedding for semantic matching
        
        Args:
            cache_key: Cache key
            response: Response to cache
            query: Original query string (used to generate embedding for semantic matching)
        """
        if self.enabled:
            cache_entry = {
                'response': response,
                'timestamp': time.time()
            }
            
            # Generate and store embedding if semantic cache is enabled
            if self.use_semantic_cache and query:
                query_embedding = self._get_embedding(query)
                if query_embedding:
                    cache_entry['query_embedding'] = query_embedding
            
            self.cache[cache_key] = cache_entry
    
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
