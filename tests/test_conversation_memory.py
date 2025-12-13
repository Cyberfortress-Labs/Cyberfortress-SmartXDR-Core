"""
Tests for Conversation Memory Service

Run with:
    python -m pytest tests/test_conversation_memory.py -v
"""
import pytest
import time
from unittest.mock import Mock, patch, MagicMock


class TestConversationMemory:
    """Test suite for ConversationMemory class"""
    
    @pytest.fixture
    def memory(self):
        """Create fresh ConversationMemory instance for each test"""
        # Reset singleton for testing
        from app.services.conversation_memory import ConversationMemory
        ConversationMemory._instance = None
        
        with patch('app.services.conversation_memory.ConversationMemory._get_collection', return_value=None):
            memory = ConversationMemory()
            yield memory
            # Clear after test
            memory.clear_all_sessions()
    
    def test_add_and_get_messages(self, memory):
        """Test basic add and get message functionality"""
        session_id = "test-session-1"
        
        # Add messages
        memory.add_message(session_id, "user", "Hello")
        memory.add_message(session_id, "assistant", "Hi there!")
        memory.add_message(session_id, "user", "How are you?")
        memory.add_message(session_id, "assistant", "I'm doing well!")
        
        # Get history
        history = memory.get_recent_history(session_id)
        
        assert len(history) == 4
        assert history[0].role == "user"
        assert history[0].content == "Hello"
        assert history[3].role == "assistant"
        assert history[3].content == "I'm doing well!"
    
    def test_session_isolation(self, memory):
        """Test that different sessions don't share history"""
        session1 = "session-1"
        session2 = "session-2"
        
        memory.add_message(session1, "user", "Message for session 1")
        memory.add_message(session2, "user", "Message for session 2")
        
        history1 = memory.get_recent_history(session1)
        history2 = memory.get_recent_history(session2)
        
        assert len(history1) == 1
        assert len(history2) == 1
        assert history1[0].content == "Message for session 1"
        assert history2[0].content == "Message for session 2"
    
    def test_history_limit(self, memory):
        """Test that history respects limit parameter"""
        session_id = "test-limit"
        
        # Add 10 messages
        for i in range(10):
            memory.add_message(session_id, "user", f"Message {i}")
        
        # Get only last 4
        history = memory.get_recent_history(session_id, limit=4)
        
        assert len(history) == 4
        assert history[0].content == "Message 6"  # Should be last 4 messages
        assert history[3].content == "Message 9"
    
    def test_format_history_for_prompt(self, memory):
        """Test formatting history for LLM prompt"""
        session_id = "test-format"
        
        memory.add_message(session_id, "user", "What is Suricata?")
        memory.add_message(session_id, "assistant", "Suricata is an IDS/IPS.")
        
        history = memory.get_recent_history(session_id)
        formatted = memory.format_history_for_prompt(history)
        
        assert "Previous conversation:" in formatted
        assert "User: What is Suricata?" in formatted
        assert "Assistant: Suricata is an IDS/IPS." in formatted
    
    def test_clear_session(self, memory):
        """Test clearing a session"""
        session_id = "test-clear"
        
        memory.add_message(session_id, "user", "Test message")
        assert len(memory.get_recent_history(session_id)) == 1
        
        # Clear session
        result = memory.clear_session(session_id)
        
        assert result is True
        assert len(memory.get_recent_history(session_id)) == 0
    
    def test_clear_nonexistent_session(self, memory):
        """Test clearing a session that doesn't exist"""
        result = memory.clear_session("nonexistent-session")
        assert result is False
    
    def test_get_session_info(self, memory):
        """Test session info retrieval"""
        session_id = "test-info"
        
        memory.add_message(session_id, "user", "Hello")
        memory.add_message(session_id, "assistant", "Hi")
        memory.add_message(session_id, "user", "Bye")
        
        info = memory.get_session_info(session_id)
        
        assert info["exists"] is True
        assert info["message_count"] == 3
        assert info["user_messages"] == 2
        assert info["assistant_messages"] == 1
    
    def test_get_session_history_as_dict(self, memory):
        """Test getting history as list of dicts"""
        session_id = "test-dict"
        
        memory.add_message(session_id, "user", "Test", {"key": "value"})
        
        history = memory.get_session_history(session_id)
        
        assert isinstance(history, list)
        assert len(history) == 1
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Test"
        assert "timestamp" in history[0]
    
    def test_max_messages_per_session(self, memory):
        """Test that messages are trimmed when exceeding max"""
        session_id = "test-max"
        memory.max_messages_per_session = 5  # Set low for testing
        
        # Add more than max
        for i in range(10):
            memory.add_message(session_id, "user", f"Message {i}")
        
        # Should only have last 5
        history = memory.get_recent_history(session_id, limit=10)
        assert len(history) == 5
        assert history[0].content == "Message 5"
    
    def test_get_stats(self, memory):
        """Test statistics retrieval"""
        memory.add_message("session-1", "user", "Hello")
        memory.add_message("session-2", "user", "World")
        
        stats = memory.get_stats()
        
        assert stats["active_sessions"] == 2
        assert stats["in_memory_messages"] == 2


class TestConversationMemoryWithChromaDB:
    """Tests that require ChromaDB mock"""
    
    @pytest.fixture
    def mock_collection(self):
        """Create mock ChromaDB collection"""
        collection = Mock()
        collection.add = Mock()
        collection.query = Mock(return_value={
            "documents": [["Previous relevant message"]],
            "metadatas": [[{"role": "user", "timestamp": 123456}]],
            "distances": [[0.5]]
        })
        collection.count = Mock(return_value=10)
        return collection
    
    @pytest.fixture
    def memory_with_chromadb(self, mock_collection):
        """Create ConversationMemory with mocked ChromaDB"""
        from app.services.conversation_memory import ConversationMemory
        ConversationMemory._instance = None
        
        with patch.object(ConversationMemory, '_get_collection', return_value=mock_collection):
            memory = ConversationMemory()
            yield memory
            memory.clear_all_sessions()
    
    def test_semantic_context_search(self, memory_with_chromadb, mock_collection):
        """Test semantic search for relevant context"""
        session_id = "test-semantic"
        
        context = memory_with_chromadb.get_semantic_context(session_id, "What is Suricata?")
        
        mock_collection.query.assert_called_once()
        assert len(context) > 0
        assert context[0]["content"] == "Previous relevant message"
    
    def test_chromadb_storage(self, memory_with_chromadb, mock_collection):
        """Test that messages are stored in ChromaDB"""
        session_id = "test-chromadb"
        
        memory_with_chromadb.add_message(session_id, "user", "Test message")
        
        # Verify add was called
        mock_collection.add.assert_called_once()
        call_args = mock_collection.add.call_args
        assert "Test message" in call_args.kwargs["documents"]


class TestGenerateSessionId:
    """Test session ID generation"""
    
    def test_generate_session_id_format(self):
        """Test that generated session IDs are valid UUIDs"""
        from app.services.conversation_memory import ConversationMemory
        ConversationMemory._instance = None
        
        with patch('app.services.conversation_memory.ConversationMemory._get_collection', return_value=None):
            memory = ConversationMemory()
            session_id = memory.generate_session_id()
            
            # Should be valid UUID format (8-4-4-4-12)
            parts = session_id.split("-")
            assert len(parts) == 5
            assert len(parts[0]) == 8
            assert len(parts[4]) == 12
