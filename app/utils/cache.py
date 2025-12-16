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
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.similarity_threshold = 0.85  # 85% similarity = cache hit
        
        # Initialize LangChain embeddings if semantic cache is enabled
        if self.use_semantic_cache:
            try:
                # Use LangChain OpenAIEmbeddings with automatic retry and batching
                self._embeddings = OpenAIEmbeddings(
                    model="text-embedding-3-small",
                    api_key=os.environ.get("OPENAI_API_KEY"),
                    # LangChain handles retries automatically
                )
                logger.info("Semantic cache enabled (LangChain embedding-based similarity matching)")
            except Exception as e:
                logger.warning(f"Semantic cache initialization failed: {e}")
                self.use_semantic_cache = False
                self._embeddings = None
    
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
        Supports both exact match and semantic similarity matching via LangChain
        
        Flow:
        1. Try exact cache key match first (FREE - no API call)
        2. If miss AND semantic cache enabled → call LangChain embedding for similarity search
        
        Args:
            cache_key: Cache key to lookup
            query: Original query string (for semantic matching - only used if exact match fails)
            
        Returns:
            Cached response or None if not found/expired
        """
        if not self.enabled:
            return None
        
        # Step 1: Try exact cache key match first (fastest, FREE)
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if time.time() - cached_data['timestamp'] < self.ttl:
                logger.debug("Cache hit (exact match - saved API call)")
                return cached_data['response']
            else:
                # Expired, remove from cache
                del self.cache[cache_key]
        
        # Step 2: Only try semantic similarity if exact match failed
        # This costs 1 embedding API call (~$0.00002) via LangChain
        if self.use_semantic_cache and query and len(self.cache) > 0:
            query_embedding = self._get_embedding(query)
            if query_embedding:
                similar_key, similarity = self._find_similar_cached_query(query_embedding)
                if similar_key:
                    cached_data = self.cache[similar_key]
                    if time.time() - cached_data['timestamp'] < self.ttl:
                        logger.debug(f"Cache hit (semantic match {similarity:.1%} - saved LLM call)")
                        return cached_data['response']
                    else:
                        del self.cache[similar_key]
        
        return None
    
    def set(self, cache_key: str, response: str, query: Optional[str] = None):
        """
        Cache a response with optional query embedding for semantic matching
        Uses LangChain for embedding generation
        
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
            
            # Generate and store embedding if semantic cache is enabled (via LangChain)
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
            'enabled': self.enabled,
            'semantic_cache_enabled': self.use_semantic_cache
        }
