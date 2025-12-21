"""
Conversation Memory Service - Hybrid Redis + ChromaDB + LangChain storage

Production-ready implementation with:
- LangChain: ConversationBufferWindowMemory for token-aware windowing
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

# LangChain imports for conversation memory
try:
    from langchain_community.chat_message_histories import ChatMessageHistory
    from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
    LANGCHAIN_MEMORY_AVAILABLE = True
except ImportError:
    LANGCHAIN_MEMORY_AVAILABLE = False
    ChatMessageHistory = None
    HumanMessage = None
    AIMessage = None
    BaseMessage = None

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
        
        # LangChain per-session memory cache (for token-aware windowing)
        self._langchain_memories: Dict[str, Any] = {}
        self.langchain_window_size = 3  # k=3 exchanges (6 messages total) - reduced for speed
        
        # Configuration
        self.max_messages_per_session = 20  # Max messages to keep
        self.default_history_limit = 10  # Default: last 5 pairs (user + assistant)
        self.session_ttl = 3600  # 1 hour TTL for sessions
        self.redis_key_prefix = "conv:"  # Redis key prefix
        
        # Summarization config (for token optimization)
        self.summarize_threshold = 12  # Raised from 8 to 12 - summarize only when really needed
        self.summarize_max_tokens = 200  # Target summary length (enough for IPs, entities)
        self.summary_cache_prefix = "summary:"  # Redis key prefix for summaries
        
        # Initialize Redis connection
        self._init_redis()
        
        self._initialized = True
        storage_type = "Redis" if self._redis_available else "In-Memory"
        langchain_status = "enabled" if LANGCHAIN_MEMORY_AVAILABLE else "disabled"
        logger.info(f"ConversationMemory initialized (storage: {storage_type}, LangChain: {langchain_status})")
    
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
                logger.info(f"Redis connected at {redis_host}:{redis_port}")
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
                        logger.info(f"Connected to conversation ChromaDB at {conv_host}:{conv_port}")
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
                logger.info(f"Conversation collection '{CONVERSATION_COLLECTION_NAME}' ready")
                    
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
        
        # Sync with LangChain memory for token-aware windowing
        self._sync_to_langchain(session_id, message)
        
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
    
    # ==================== LangChain Integration ====================
    
    def _get_langchain_memory(self, session_id: str):
        """
        Get or create LangChain ChatMessageHistory for session.
        Uses simple message history - windowing is handled by format_langchain_history.
        """
        if not LANGCHAIN_MEMORY_AVAILABLE:
            return None
        
        if session_id not in self._langchain_memories:
            self._langchain_memories[session_id] = ChatMessageHistory()
            logger.debug(f"Created LangChain ChatMessageHistory for session {session_id[:8]}...")
        
        return self._langchain_memories[session_id]
    
    def _sync_to_langchain(self, session_id: str, message: Message):
        """Sync a message to LangChain memory for token-aware windowing."""
        if not LANGCHAIN_MEMORY_AVAILABLE:
            return
        
        memory = self._get_langchain_memory(session_id)
        if memory is None:
            return
        
        try:
            # LangChain expects pairs - we need to track state
            # Store messages and let get_langchain_messages handle pairing
            # The ConversationBufferWindowMemory will auto-prune old messages
            pass  # Memory is populated via get_langchain_messages from Redis/RAM
        except Exception as e:
            logger.debug(f"LangChain sync skipped: {e}")
    
    def get_langchain_messages(self, session_id: str) -> List[Any]:
        """
        Get conversation history as LangChain message objects.
        Returns List[HumanMessage | AIMessage] for prompt injection.
        
        This method:
        1. Gets recent history from Redis/RAM (source of truth)
        2. Ensures message pairs (user + assistant together)
        3. Converts to LangChain format
        """
        if not LANGCHAIN_MEMORY_AVAILABLE:
            return []
        
        # Get raw messages from storage (Redis or RAM)
        messages = self.get_recent_history(session_id, limit=self.langchain_window_size * 2)
        
        if not messages:
            return []
        
        # Ensure we get complete pairs (user + assistant)
        messages = self._ensure_message_pairs(messages)
        
        # Convert to LangChain format
        langchain_messages = []
        for msg in messages:
            if msg.role == "user":
                langchain_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                langchain_messages.append(AIMessage(content=msg.content))
        
        return langchain_messages
    
    def _ensure_message_pairs(self, messages: List[Message]) -> List[Message]:
        """
        Ensure messages are in complete pairs (user + assistant).
        If last message is user (no response yet), include it.
        If first message is assistant (orphaned), skip it.
        """
        if not messages:
            return []
        
        result = []
        i = 0
        
        # Skip leading assistant messages (orphaned responses)
        while i < len(messages) and messages[i].role == "assistant":
            i += 1
        
        # Process remaining messages
        while i < len(messages):
            msg = messages[i]
            result.append(msg)
            i += 1
        
        return result
    
    def format_langchain_history(self, session_id: str, max_chars: int = 3000) -> str:
        """
        Format conversation history from LangChain messages for prompt.
        Better than raw formatting - ensures pairs and proper windowing.
        """
        lc_messages = self.get_langchain_messages(session_id)
        
        if not lc_messages:
            return ""
        
        parts = []
        total_chars = 0
        
        for msg in lc_messages:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            content = msg.content
            
            # Truncate individual message if too long
            if len(content) > 500:
                content = content[:500] + "..."
            
            line = f"{role}: {content}"
            
            if total_chars + len(line) > max_chars:
                break
            
            parts.append(line)
            total_chars += len(line) + 1
        
        if parts:
            return "Previous conversation:\n" + "\n".join(parts)
        return ""

    
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
        
        Loads prompt from prompts/instructions/summarization_rule.json via PromptBuilder.
        Falls back to hardcoded prompt if JSON not available.
        """
        try:
            from app.core.openai_client import get_openai_client
            
            client = get_openai_client()
            
            # Format messages for summarization
            conversation_text = "\n".join([
                f"{'User' if m.role == 'user' else 'Assistant'}: {m.content[:300]}"
                for m in messages
            ])
            
            logger.debug(f"Summarizing {len(messages)} messages ({len(conversation_text)} chars)")
            
            # Try to load prompt from JSON via PromptBuilder
            system_prompt, max_tokens = self._load_summarization_prompt()
            
            response = client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": conversation_text}
                ],
                max_completion_tokens=max_tokens
            )
            
            summary = response.choices[0].message.content
            
            # Debug: log raw response
            logger.debug(f"Raw LLM summary response: '{summary}'")
            
            if summary:
                summary = summary.strip()
            
            # Check if summary is valid
            if not summary or len(summary) < 10:
                logger.warning(f"LLM returned empty/short summary, using smart fallback")
                # Smart fallback: extract key info from both user and assistant messages
                summary = self._build_smart_fallback_summary(messages)
            
            logger.info(f"Generated summary ({len(summary)} chars): {summary[:80]}...")
            
            return f"Previous conversation summary: {summary}"
            
        except Exception as e:
            logger.warning(f"Failed to generate summary: {e}")
            return None
    
    def _build_smart_fallback_summary(self, messages: List[Message]) -> str:
        """
        Build a smart fallback summary when LLM summarization fails.
        Extracts key entities (IPs, device names, etc.) from both user and assistant messages.
        """
        import re
        
        # Get last user question (most relevant context)
        last_user = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user = m.content[:100]
                break
        
        # Extract IPs from all messages (especially assistant responses)
        all_text = " ".join([m.content for m in messages])
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ips = list(set(re.findall(ip_pattern, all_text)))[:5]  # Max 5 IPs
        
        # Extract device/system names
        systems = ['Suricata', 'pfSense', 'Wazuh', 'SIEM', 'Zeek', 'IRIS', 'Router', 
                   'Firewall', 'Server', 'NAT', 'Gateway', 'Switch', 'Elasticsearch']
        found_systems = []
        for system in systems:
            if re.search(rf'\b{system}\b', all_text, re.IGNORECASE):
                found_systems.append(system)
                if len(found_systems) >= 3:
                    break
        
        # Build summary
        parts = []
        if last_user:
            parts.append(f"User asked: {last_user}")
        if found_systems:
            parts.append(f"Systems: {', '.join(found_systems)}")
        if ips:
            parts.append(f"IPs mentioned: {', '.join(ips)}")
        
        return " | ".join(parts) if parts else "Ongoing conversation"
    
    def _load_summarization_prompt(self) -> tuple:
        """
        Load summarization prompt from JSON file.
        
        Returns:
            tuple: (system_prompt, max_tokens)
        """
        default_prompt = """Summarize this conversation for context continuity.
IMPORTANT: Keep ALL device names, system names (SIEM, Wazuh, pfSense, etc.), IP addresses.
Identify what 'it/this/that' or 'nó/này/đó' refers to.
Format: "User discussing [TOPIC]. Current focus: [ENTITY]. Key details: [INFO]"
Output only the summary."""
        default_max_tokens = 150
        
        try:
            from app.services.prompt_builder_service import PromptBuilder
            import json
            
            builder = PromptBuilder()
            prompt_json = builder.build_task_prompt("summarization_rule")
            prompt_data = json.loads(prompt_json)
            
            system_prompt = prompt_data.get("system_prompt", default_prompt)
            settings = prompt_data.get("settings", {})
            max_tokens = settings.get("max_completion_tokens", default_max_tokens)
            
            logger.debug(f"Loaded summarization prompt from JSON")
            return (system_prompt, max_tokens)
            
        except FileNotFoundError:
            logger.warning("summarization_rule.json not found, using fallback prompt")
            return (default_prompt, default_max_tokens)
        except Exception as e:
            logger.warning(f"Error loading summarization prompt: {e}, using fallback")
            return (default_prompt, default_max_tokens)
    
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
