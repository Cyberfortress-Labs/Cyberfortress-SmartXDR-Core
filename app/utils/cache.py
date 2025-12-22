"""
Response Caching System for API Optimization
Using LangChain's OpenAIEmbeddings for semantic similarity matching
"""
import time
import hashlib
import re
import os
import logging
import numpy as np
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv
from app.config import *

# Setup logger
logger = logging.getLogger('smartxdr.cache')

# Load environment variables
load_dotenv()

# Try to import LangChain for embedding similarity matching
try:
    from langchain_openai import OpenAIEmbeddings
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False


class ResponseCache:
    """Cache API responses with semantic similarity matching using LangChain"""
    
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
        self.use_semantic_cache = use_semantic_cache and LANGCHAIN_AVAILABLE
        # Default local cache (L1)
        self._local_cache: Dict[str, Dict[str, Any]] = {} 
        # Redis cache (L2)
        self._redis = None
        self._redis_available = False
        self._init_redis()
        
        self.similarity_threshold = 0.85  # 85% similarity = cache hit
        
        # Initialize LangChain embeddings if semantic cache is enabled
        if self.use_semantic_cache:
            try:
                # Use LangChain OpenAIEmbeddings with automatic retry and batching
                self._embeddings = OpenAIEmbeddings(
                    model=EMBEDDING_MODEL,
                    api_key=os.environ.get("OPENAI_API_KEY"),
                    # LangChain handles retries automatically
                )
                logger.info("Semantic cache enabled (LangChain embedding-based similarity matching)")
            except Exception as e:
                logger.warning(f"Semantic cache initialization failed: {e}")
                self.use_semantic_cache = False
                self._embeddings = None

    def _init_redis(self):
        """Initialize Redis using shared client"""
        try:
            from app.utils.redis_client import get_redis_client
            redis_wrapper = get_redis_client()
            self._redis = redis_wrapper.client
            self._redis_available = redis_wrapper.available
            if self._redis_available:
                logger.info("ResponseCache connected to Redis")
        except Exception as e:
            logger.warning(f"ResponseCache failed to connect to Redis: {e}")

    def _normalize_query(self, query: str) -> str:
        """
        Lightweight query normalization for cache key generation.
        
        Strategy: Do minimal text cleanup and let embedding similarity 
        handle semantic matching. This is more robust than rule-based patterns.
        
        Args:
            query: Original query string
            
        Returns:
            Normalized query string for cache key
        """
        if not query:
            return ""
        
        # Basic cleanup only - embeddings handle semantic similarity
        normalized = query.lower().strip()
        
        # Remove trailing punctuation (?, !, ., ...)
        normalized = re.sub(r'[?!.…]+$', '', normalized)
        
        # Normalize whitespace (multiple spaces/tabs/newlines -> single space)
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Extract and preserve key entities (IPs, versions, IDs)
        # These are exact-match important for cache keys
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        mitre_pattern = r'\b[tT]\d{4}(?:\.\d{3})?\b'  # T1234 or T1234.001
        cve_pattern = r'\bCVE-\d{4}-\d+\b'
        
        # Find all entities
        entities = []
        entities.extend(re.findall(ip_pattern, normalized))
        entities.extend(re.findall(mitre_pattern, normalized, re.IGNORECASE))
        entities.extend(re.findall(cve_pattern, normalized, re.IGNORECASE))
        
        # If entities found, prepend them (sorted) for consistent cache keys
        if entities:
            entity_prefix = ' '.join(sorted(set(e.upper() for e in entities)))
            # Remove entities from normalized text to avoid duplication
            for entity in entities:
                normalized = re.sub(re.escape(entity), '', normalized, flags=re.IGNORECASE)
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            return f"{entity_prefix} {normalized}".strip()
        
        return normalized.strip()
    
    def _get_embedding(self, text: str) -> Optional[list]:
        """
        Get embedding for text using LangChain OpenAIEmbeddings
        
        Benefits of LangChain:
        - Automatic retry logic with exponential backoff
        - Better error handling
        - Optimized for single query embedding
        """
        if not self.use_semantic_cache or not self._embeddings:
            return None
        
        try:
            # Use embed_query for single text (optimized for queries)
            return self._embeddings.embed_query(text)
        except Exception as e:
            logger.warning(f"Failed to get embedding: {e}")
            return None
    
    def _cosine_similarity(self, vec1: list, vec2: list) -> float:
        """Calculate cosine similarity between two vectors"""
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    
    def _find_similar_cached_query(self, query_embedding: list) -> Tuple[Optional[str], float]:
        """Find cached query with highest similarity to current query"""
        # Linear scan (OK for small cache, but need vector DB for scale)
        # TODO: Use persistent vector store for scalable semantic cache
        
        # Use local cache for scan if available, otherwise skip (Redis scan is too slow)
        best_match_key = None
        best_similarity = 0.0
        
        # For now, only scan in-memory keys for semantic match to avoid perf hit
        for cache_key, cache_data in self._local_cache.items():
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
        Supports L1 (Memory) and L2 (Redis) cache
        """
        if not self.enabled:
            return None
        
        # Step 1: Check L1 Local Cache (Fastest)
        if cache_key in self._local_cache:
            cached_data = self._local_cache[cache_key]
            if time.time() - cached_data['timestamp'] < self.ttl:
                logger.debug("Cache hit (L1 In-Memory)")
                return cached_data['response']
            else:
                del self._local_cache[cache_key]
        
        # Step 2: Check L2 Redis Cache
        if self._redis_available:
            try:
                redis_data = self._redis.get(f"rag_cache:{cache_key}")
                if redis_data:
                    import json
                    cached_data = json.loads(redis_data)
                    
                    # Promote to L1
                    self._local_cache[cache_key] = cached_data
                    
                    logger.debug("Cache hit (L2 Redis)")
                    return cached_data['response']
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")
        
        # Step 3: Semantic Search (Only if exact match failed)
        if self.use_semantic_cache and query:
            query_embedding = self._get_embedding(query)
            if query_embedding:
                similar_key, similarity = self._find_similar_cached_query(query_embedding)
                if similar_key:
                    # Retrieve from L1 (since we only scan L1 for now)
                    cached_data = self._local_cache[similar_key]
                    if time.time() - cached_data['timestamp'] < self.ttl:
                        # SAFETY CHECK: Reject if entities or action verbs conflict
                        cached_query = cached_data.get('original_query', '')
                        if self._has_entity_or_action_conflict(query, cached_query):
                            logger.warning(f"Semantic cache REJECTED: conflict detected between '{query[:DEBUG_TEXT_LENGTH]}' and '{cached_query[:DEBUG_TEXT_LENGTH]}'")
                        else:
                            logger.debug(f"Cache hit (semantic match {similarity:.1%})")
                            return cached_data['response']
        
        return None
    
    # ==================== Conflict Detection (Generalized) ====================
    
    # Pairs of opposite action verbs (Vietnamese + English)
    _OPPOSITE_ACTIONS = [
        # Vietnamese
        ('bật', 'tắt'), ('mở', 'đóng'), ('kích hoạt', 'vô hiệu hóa'),
        ('thêm', 'xóa'), ('tạo', 'xóa'), ('cài', 'gỡ'),
        ('bắt đầu', 'dừng'), ('khởi động', 'dừng'), ('chạy', 'dừng'),
        # English
        ('enable', 'disable'), ('start', 'stop'), ('on', 'off'),
        ('open', 'close'), ('add', 'remove'), ('create', 'delete'),
        ('install', 'uninstall'), ('activate', 'deactivate'),
        ('allow', 'block'), ('permit', 'deny'), ('grant', 'revoke'),
    ]
    
    # Regex patterns for critical entities
    _ENTITY_PATTERNS = {
        'ip': r'\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b',  # IPv4 with optional CIDR
        'ipv6': r'\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b',  # IPv6
        'domain': r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b',  # domain.tld
        'hash_md5': r'\b[a-fA-F0-9]{32}\b',  # MD5
        'hash_sha1': r'\b[a-fA-F0-9]{40}\b',  # SHA1
        'hash_sha256': r'\b[a-fA-F0-9]{64}\b',  # SHA256
        'cve': r'\bCVE-\d{4}-\d+\b',  # CVE-2024-12345
        'mitre': r'\b[tT][aA]?\d{4}(?:\.\d{3})?\b',  # T1234, TA0001, T1234.001
        'port': r'\bport\s*[:\s]?\s*(\d{1,5})\b',  # port 443, port:80
        'email': r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
    }
    
    def _extract_entities(self, text: str) -> set:
        """Extract all critical entities from text"""
        if not text:
            return set()
        
        entities = set()
        text_lower = text.lower()
        
        for entity_type, pattern in self._ENTITY_PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Normalize: lowercase for case-insensitive comparison
                entities.add(f"{entity_type}:{match.lower()}")
        
        return entities
    
    def _has_entity_or_action_conflict(self, query1: str, query2: str) -> bool:
        """
        Check if two queries have conflicting entities or action verbs.
        Returns True if:
        1. They have opposite action verbs (bật/tắt, enable/disable)
        2. They reference DIFFERENT critical entities (different IPs, hashes, etc.)
        """
        if not query1 or not query2:
            return False
        
        q1_lower = query1.lower()
        q2_lower = query2.lower()
        
        # Check 1: Action verb conflict
        for action_a, action_b in self._OPPOSITE_ACTIONS:
            q1_has_a = action_a in q1_lower
            q1_has_b = action_b in q1_lower
            q2_has_a = action_a in q2_lower
            q2_has_b = action_b in q2_lower
            
            if (q1_has_a and q2_has_b) or (q1_has_b and q2_has_a):
                return True
        
        # Check 2: Entity mismatch
        entities1 = self._extract_entities(query1)
        entities2 = self._extract_entities(query2)
        
        # If either query has entities, they MUST match
        if entities1 or entities2:
            # Group by entity type
            types1 = {e.split(':')[0] for e in entities1}
            types2 = {e.split(':')[0] for e in entities2}
            
            # Check each common entity type
            common_types = types1 & types2
            for etype in common_types:
                vals1 = {e for e in entities1 if e.startswith(f"{etype}:")}
                vals2 = {e for e in entities2 if e.startswith(f"{etype}:")}
                
                # If same type but different values → conflict
                if vals1 != vals2:
                    return True
        
        return False
    
    def set(self, cache_key: str, response: str, query: Optional[str] = None):
        """
        Cache a response to L1 and L2
        """
        if self.enabled:
            cache_entry = {
                'response': response,
                'timestamp': time.time(),
                'original_query': query or ''  # Store for action conflict detection
            }
            
            # Add embedding for semantic cache (L1 only for now due to complexity)
            if self.use_semantic_cache and query:
                query_embedding = self._get_embedding(query)
                if query_embedding:
                    cache_entry['query_embedding'] = query_embedding
            
            # Store L1
            self._local_cache[cache_key] = cache_entry
            
            # Store L2 Redis (without embedding to save space/complexity)
            if self._redis_available:
                try:
                    import json
                    # Create copy without embedding (not serializable/needed in Redis for simple key lookup)
                    redis_entry = cache_entry.copy()
                    if 'query_embedding' in redis_entry:
                        del redis_entry['query_embedding']
                        
                    self._redis.setex(
                        f"rag_cache:{cache_key}",
                        self.ttl,
                        json.dumps(redis_entry)
                    )
                except Exception as e:
                    logger.warning(f"Failed to set Redis cache: {e}")
    
    def clear(self):
        """Clear all cached responses"""
        self._local_cache.clear()
        if self._redis_available:
            try:
                keys = self._redis.keys("rag_cache:*")
                if keys:
                    self._redis.delete(*keys)
            except Exception as e:
                logger.warning(f"Failed to clear Redis cache: {e}")
    
    def clear_expired(self):
        """Remove expired cache entries (Redis handles this automatically via TTL)"""
        now = time.time()
        expired_keys = [
            key for key, data in self._local_cache.items()
            if now - data['timestamp'] >= self.ttl
        ]
        for key in expired_keys:
            del self._local_cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            'l1_cache_size': len(self._local_cache),
            'redis_available': self._redis_available,
            'ttl': self.ttl,
            'enabled': self.enabled,
            'semantic_cache_enabled': self.use_semantic_cache
        }
