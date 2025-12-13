"""
Conversation Memory Service - Hybrid Redis + ChromaDB storage

Production-ready implementation with:
- Redis: Fast session storage with TTL, shared across workers
- ChromaDB: Semantic search for relevant past context
- Fallback: In-memory dict when Redis unavailable (development mode)
"""
import os
import uuid
import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from app.config import *
logger = logging.getLogger('smartxdr.conversation')


@dataclass
class Message:
    """Single message in a conversation"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {})
        )


class ConversationMemory:
    """
    Hybrid conversation memory with Redis + ChromaDB storage
    
    Redis: Fast session storage with TTL (production)
    In-Memory: Fallback for development when Redis unavailable
    ChromaDB: Semantic search for relevant past context
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Redis client (None if not available)
        self._redis = None
        self._redis_available = False
        
        # Fallback: In-Memory storage for development
        self._sessions: Dict[str, List[Message]] = {}
        
        # ChromaDB collection (lazy initialization)
        self._collection = None
        self._chroma_client = None
        
        # Configuration
        self.max_messages_per_session = 20  # Max messages to keep
        self.default_history_limit = 6  # Default: last 3 pairs (user + assistant)
        self.session_ttl = 3600  # 1 hour TTL for sessions
        self.redis_key_prefix = "conv:"  # Redis key prefix
        
        # Summarization config (for token optimization)
        self.summarize_threshold = 4  # Summarize when > 4 messages
        self.summarize_max_tokens = 100  # Target summary length
        self.summary_cache_prefix = "summary:"  # Redis key prefix for summaries
        
        # Initialize Redis connection
        self._init_redis()
        
        self._initialized = True
        storage_type = "Redis" if self._redis_available else "In-Memory"
        logger.info(f"✓ ConversationMemory initialized (storage: {storage_type})")
    
    def _init_redis(self):
        """Initialize Redis connection if available"""
        redis_host = os.getenv("REDIS_HOST")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        
        if redis_host:
            try:
                import redis
                self._redis = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=0,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                # Test connection
                self._redis.ping()
                self._redis_available = True
                logger.info(f"✓ Redis connected at {redis_host}:{redis_port}")
            except Exception as e:
                logger.warning(f"Redis not available ({e}), using in-memory fallback")
                self._redis = None
                self._redis_available = False
        else:
            logger.info("Redis not configured (REDIS_HOST not set), using in-memory storage")
    
    def _get_redis_key(self, session_id: str) -> str:
        """Get Redis key for a session"""
        return f"{self.redis_key_prefix}{session_id}"
    
    def _get_collection(self):
        """Lazy load ChromaDB collection for conversation history.
        
        Uses SEPARATE ChromaDB instance from RAG (CHROMA_CONV_HOST) for isolation.
        Falls back to local PersistentClient for development.
        """
        if self._collection is None:
            try:
                import chromadb
                from chromadb.config import Settings
                from app.config import CONVERSATION_COLLECTION_NAME, DB_PATH
                from app.core.embeddings import OpenAIEmbeddingFunction
                
                # Get conversation-specific ChromaDB config
                conv_host = os.getenv("CHROMA_CONV_HOST")
                conv_port = int(os.getenv("CHROMA_CONV_PORT", "8000"))
                
                if conv_host:
                    # Docker: Use separate ChromaDB instance for conversations
                    try:
                        self._chroma_client = chromadb.HttpClient(
                            host=conv_host,
                            port=conv_port,
                            settings=Settings(anonymized_telemetry=False)
                        )
                        self._chroma_client.heartbeat()
                        logger.info(f"✓ Connected to conversation ChromaDB at {conv_host}:{conv_port}")
                    except Exception as e:
                        logger.warning(f"ChromaDB conv service not available ({e}), using local fallback")
                        from app.config import CONV_DB_PATH
                        self._chroma_client = chromadb.PersistentClient(
                            path=CONV_DB_PATH,
                            settings=Settings(anonymized_telemetry=False)
                        )
                else:
                    # Local development: Use separate local directory
                    from app.config import CONV_DB_PATH
                    os.makedirs(CONV_DB_PATH, exist_ok=True)
                    self._chroma_client = chromadb.PersistentClient(
                        path=CONV_DB_PATH,
                        settings=Settings(anonymized_telemetry=False)
                    )
                    logger.info(f"Using local conversation ChromaDB at {CONV_DB_PATH}")
                
                # Create embedding function
                embedding_function = OpenAIEmbeddingFunction()
                
                # Get or create collection
                self._collection = self._chroma_client.get_or_create_collection(
                    name=CONVERSATION_COLLECTION_NAME,
                    embedding_function=embedding_function,
                    metadata={"description": "Conversation history for semantic search"}
                )
                logger.info(f"✓ Conversation collection '{CONVERSATION_COLLECTION_NAME}' ready")
                    
            except Exception as e:
                logger.error(f"Failed to initialize conversation ChromaDB: {e}")
                self._collection = None
        
        return self._collection
    
    def generate_session_id(self) -> str:
        """Generate a new unique session ID"""
        return str(uuid.uuid4())
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """Add a message to conversation history"""
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        if self._redis_available:
            self._add_message_redis(session_id, message)
        else:
            self._add_message_memory(session_id, message)
        
        # Also store in ChromaDB for semantic search
        self._store_in_chromadb(session_id, message)
        
        logger.debug(f"Added {role} message to session {session_id[:8]}...")
        return message
    
    def _add_message_redis(self, session_id: str, message: Message):
        """Add message to Redis"""
        key = self._get_redis_key(session_id)
        
        try:
            # Get existing messages
            existing = self._redis.get(key)
            messages = json.loads(existing) if existing else []
            
            # Add new message
            messages.append(message.to_dict())
            
            # Trim if exceeds limit
            if len(messages) > self.max_messages_per_session:
                messages = messages[-self.max_messages_per_session:]
            
            # Save with TTL
            self._redis.setex(
                key,
                self.session_ttl,
                json.dumps(messages)
            )
        except Exception as e:
            logger.error(f"Redis error in add_message: {e}")
            # Fallback to memory
            self._add_message_memory(session_id, message)
    
    def _add_message_memory(self, session_id: str, message: Message):
        """Add message to in-memory storage"""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        
        self._sessions[session_id].append(message)
        
        # Trim if exceeds limit
        if len(self._sessions[session_id]) > self.max_messages_per_session:
            self._sessions[session_id] = self._sessions[session_id][-self.max_messages_per_session:]
    
    def _store_in_chromadb(self, session_id: str, message: Message):
        """Store message in ChromaDB for semantic search"""
        collection = self._get_collection()
        if collection is None:
            return
        
        try:
            doc_id = f"{session_id}-{message.timestamp}"
            
            collection.add(
                ids=[doc_id],
                documents=[message.content],
                metadatas=[{
                    "session_id": session_id,
                    "role": message.role,
                    "timestamp": message.timestamp,
                    "datetime": datetime.fromtimestamp(message.timestamp).isoformat()
                }]
            )
        except Exception as e:
            logger.warning(f"Failed to store message in ChromaDB: {e}")
    
    def get_recent_history(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Message]:
        """Get recent messages from session"""
        if limit is None:
            limit = self.default_history_limit
        
        if self._redis_available:
            return self._get_history_redis(session_id, limit)
        else:
            return self._get_history_memory(session_id, limit)
    
    def _get_history_redis(self, session_id: str, limit: int) -> List[Message]:
        """Get history from Redis"""
        key = self._get_redis_key(session_id)
        
        try:
            data = self._redis.get(key)
            if not data:
                return []
            
            messages = [Message.from_dict(m) for m in json.loads(data)]
            
            # Refresh TTL on access
            self._redis.expire(key, self.session_ttl)
            
            return messages[-limit:] if len(messages) > limit else messages
        except Exception as e:
            logger.error(f"Redis error in get_history: {e}")
            return self._get_history_memory(session_id, limit)
    
    def _get_history_memory(self, session_id: str, limit: int) -> List[Message]:
        """Get history from in-memory storage"""
        if session_id not in self._sessions:
            return []
        
        messages = self._sessions[session_id]
        return messages[-limit:] if len(messages) > limit else messages
    
    def get_semantic_context(
        self,
        session_id: str,
        query: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Search for semantically relevant past conversations"""
        collection = self._get_collection()
        if collection is None:
            return []
        
        try:
            results = collection.query(
                query_texts=[query],
                n_results=limit * 2,
                where={"session_id": session_id}
            )
            
            if not results["documents"] or not results["documents"][0]:
                return []
            
            context = []
            for i, doc in enumerate(results["documents"][0][:limit]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                context.append({
                    "content": doc,
                    "role": meta.get("role", "unknown"),
                    "timestamp": meta.get("timestamp", 0),
                    "distance": results["distances"][0][i] if results["distances"] else None
                })
            
            return context
            
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []
    
    def format_history_for_prompt(
        self,
        messages: List[Message],
        max_chars: int = 2000
    ) -> str:
        """Format message history for inclusion in LLM prompt"""
        if not messages:
            return ""
        
        formatted_parts = []
        total_chars = 0
        
        for msg in messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            line = f"{role_label}: {msg.content}"
            
            if total_chars + len(line) > max_chars:
                remaining = max_chars - total_chars - 50
                if remaining > 100:
                    line = line[:remaining] + "..."
                    formatted_parts.append(line)
                break
            
            formatted_parts.append(line)
            total_chars += len(line) + 1
        
        if formatted_parts:
            return "Previous conversation:\n" + "\n".join(formatted_parts)
        return ""
    
    def format_semantic_context(
        self,
        semantic_results: List[Dict[str, Any]],
        max_chars: int = 1000
    ) -> str:
        """Format semantic search results for inclusion in LLM prompt"""
        if not semantic_results:
            return ""
        
        formatted_parts = []
        total_chars = 0
        
        for result in semantic_results:
            content = result.get("content", "")
            role = result.get("role", "unknown")
            role_label = "User" if role == "user" else "Assistant"
            
            line = f"{role_label}: {content}"
            
            if total_chars + len(line) > max_chars:
                remaining = max_chars - total_chars - 50
                if remaining > 50:
                    line = line[:remaining] + "..."
                    formatted_parts.append(line)
                break
            
            formatted_parts.append(line)
            total_chars += len(line) + 1
        
        if formatted_parts:
            return "Related past conversation:\n" + "\n".join(formatted_parts)
        return ""
    
    def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """Get information about a session"""
        messages = self.get_recent_history(session_id, limit=100)
        
        if not messages:
            return {"exists": False, "message_count": 0}
        
        return {
            "exists": True,
            "message_count": len(messages),
            "first_message": messages[0].timestamp if messages else None,
            "last_message": messages[-1].timestamp if messages else None,
            "user_messages": sum(1 for m in messages if m.role == "user"),
            "assistant_messages": sum(1 for m in messages if m.role == "assistant"),
            "storage": "redis" if self._redis_available else "memory"
        }
    
    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get full session history as list of dicts"""
        messages = self.get_recent_history(session_id, limit=100)
        return [msg.to_dict() for msg in messages]
    
    def clear_session(self, session_id: str) -> bool:
        """Clear a session"""
        cleared = False
        
        if self._redis_available:
            try:
                key = self._get_redis_key(session_id)
                result = self._redis.delete(key)
                cleared = result > 0
            except Exception as e:
                logger.error(f"Redis error in clear_session: {e}")
        
        # Also clear from memory (if fallback was used)
        if session_id in self._sessions:
            del self._sessions[session_id]
            cleared = True
        
        if cleared:
            logger.info(f"Cleared session {session_id[:8]}...")
        return cleared
    
    def clear_all_sessions(self):
        """Clear all sessions"""
        count = 0
        
        if self._redis_available:
            try:
                pattern = f"{self.redis_key_prefix}*"
                keys = self._redis.keys(pattern)
                if keys:
                    count = self._redis.delete(*keys)
            except Exception as e:
                logger.error(f"Redis error in clear_all: {e}")
        
        count += len(self._sessions)
        self._sessions.clear()
        logger.info(f"Cleared {count} sessions")
    
    def get_summarized_history(
        self,
        session_id: str,
        force_refresh: bool = False
    ) -> str:
        """
        Get conversation history, summarizing if > threshold messages.
        
        Token optimization: Instead of sending 6 full messages (~600 tokens),
        summarize to ~100 tokens when history exceeds threshold.
        
        Args:
            session_id: Session identifier
            force_refresh: Force regenerate summary even if cached
        
        Returns:
            Formatted history string (raw or summarized)
        """
        messages = self.get_recent_history(session_id, limit=self.default_history_limit)
        
        if not messages:
            return ""
        
        # If <= threshold, return raw formatted history
        if len(messages) <= self.summarize_threshold:
            return self.format_history_for_prompt(messages)
        
        # Check for cached summary
        if not force_refresh:
            cached_summary = self._get_cached_summary(session_id)
            if cached_summary:
                logger.debug(f"Using cached summary for {session_id[:8]}...")
                return cached_summary
        
        # Generate new summary
        summary = self._generate_summary(messages)
        
        # Cache the summary
        if summary:
            self._cache_summary(session_id, summary, len(messages))
        
        return summary or self.format_history_for_prompt(messages)
    
    def _get_cached_summary(self, session_id: str) -> Optional[str]:
        """Get cached summary from Redis/memory"""
        if self._redis_available:
            try:
                key = f"{self.summary_cache_prefix}{session_id}"
                data = self._redis.get(key)
                if data:
                    cached = json.loads(data)
                    # Check if message count changed (invalidate if new messages)
                    current_count = len(self.get_recent_history(session_id, limit=100))
                    if cached.get("msg_count") == current_count:
                        return cached.get("summary")
            except Exception as e:
                logger.warning(f"Error getting cached summary: {e}")
        return None
    
    def _cache_summary(self, session_id: str, summary: str, msg_count: int):
        """Cache summary in Redis"""
        if self._redis_available:
            try:
                key = f"{self.summary_cache_prefix}{session_id}"
                data = json.dumps({
                    "summary": summary,
                    "msg_count": msg_count,
                    "timestamp": time.time()
                })
                self._redis.setex(key, self.session_ttl, data)
            except Exception as e:
                logger.warning(f"Error caching summary: {e}")
    
    def _generate_summary(self, messages: List[Message]) -> Optional[str]:
        """
        Generate a summary of conversation history using LLM.
        
        Uses a lightweight GPT-4o-mini call to create concise summary.
        """
        try:
            from openai import OpenAI
            import os
            
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            # Format messages for summarization
            conversation_text = "\n".join([
                f"{'User' if m.role == 'user' else 'Assistant'}: {m.content[:200]}"
                for m in messages
            ])
            
            response = client.chat.completions.create(
                model=SUMMARIZE_MODEL,  # Cheap model for summarization
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize this conversation in 1-2 sentences (max 100 tokens). Focus on key topics discussed and user's main intent. Output only the summary, no prefixes."
                    },
                    {
                        "role": "user",
                        "content": conversation_text
                    }
                ],
                max_completion_tokens=100,  # Use max_completion_tokens for newer models
                temperature=0.3
            )
            
            summary = response.choices[0].message.content.strip()
            logger.debug(f"Generated summary: {summary[:50]}...")
            
            return f"Previous conversation summary: {summary}"
            
        except Exception as e:
            logger.warning(f"Failed to generate summary: {e}")
            return None
    
    def invalidate_summary_cache(self, session_id: str):
        """Invalidate cached summary (call when new messages added)"""
        if self._redis_available:
            try:
                key = f"{self.summary_cache_prefix}{session_id}"
                self._redis.delete(key)
            except:
                pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        # Count in-memory messages
        memory_sessions = len(self._sessions)
        memory_messages = sum(len(msgs) for msgs in self._sessions.values())
        
        # Count Redis sessions
        redis_sessions = 0
        if self._redis_available:
            try:
                pattern = f"{self.redis_key_prefix}*"
                redis_sessions = len(self._redis.keys(pattern))
            except:
                pass
        
        # Count ChromaDB messages
        collection = self._get_collection()
        chromadb_count = collection.count() if collection else 0
        
        return {
            "storage_type": "redis" if self._redis_available else "memory",
            "redis_available": self._redis_available,
            "redis_sessions": redis_sessions,
            "memory_sessions": memory_sessions,
            "memory_messages": memory_messages,
            "chromadb_messages": chromadb_count,
            "max_messages_per_session": self.max_messages_per_session,
            "session_ttl_seconds": self.session_ttl,
            "default_history_limit": self.default_history_limit
        }


# Singleton instance
def get_conversation_memory() -> ConversationMemory:
    """Get or create ConversationMemory singleton instance"""
    return ConversationMemory()
