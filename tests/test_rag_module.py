"""
Unit Tests for RAG Module

Tests for:
- RAGRepository
- RAGService
- API endpoints
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from app.rag.repository import RAGRepository
from app.rag.service import RAGService
from app.rag.models import DocumentMetadata, Document


@pytest.fixture
def temp_db_path():
    """Create temporary database for testing"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def repository(temp_db_path):
    """Create RAGRepository instance for testing"""
    return RAGRepository(
        persist_directory=temp_db_path,
        collection_name="test_collection"
    )


@pytest.fixture
def service(repository):
    """Create RAGService instance with test repository"""
    return RAGService(repository=repository)


# ==================== RAGRepository Tests ====================

class TestRAGRepository:
    """Test RAGRepository functionality"""
    
    def test_add_document(self, repository):
        """Test adding a single document"""
        metadata = DocumentMetadata(
            source="test.txt",
            source_id="test-doc",
            version="v1.0.0",
            tags=["test"]
        )
        
        doc_id = repository.add_document(
            content="This is a test document.",
            metadata=metadata
        )
        
        assert doc_id is not None
        assert doc_id.startswith("doc_")
        
        # Verify document was added
        doc = repository.get_document(doc_id)
        assert doc is not None
        assert doc.content == "This is a test document."
        assert doc.metadata.source_id == "test-doc"
    
    def test_add_documents_batch(self, repository):
        """Test adding multiple documents"""
        contents = ["Doc 1", "Doc 2", "Doc 3"]
        metadatas = [
            DocumentMetadata(source="test.txt", source_id=f"doc-{i}", version="v1.0.0")
            for i in range(3)
        ]
        
        doc_ids = repository.add_documents_batch(contents, metadatas)
        
        assert len(doc_ids) == 3
        assert all(doc_id.startswith("doc_") for doc_id in doc_ids)
    
    def test_get_document(self, repository):
        """Test retrieving a document"""
        metadata = DocumentMetadata(
            source="test.txt",
            source_id="test-doc",
            version="v1.0.0"
        )
        
        doc_id = repository.add_document("Test content", metadata)
        doc = repository.get_document(doc_id)
        
        assert doc is not None
        assert doc.id == doc_id
        assert doc.content == "Test content"
        assert doc.metadata.source_id == "test-doc"
    
    def test_update_document(self, repository):
        """Test updating a document"""
        metadata = DocumentMetadata(
            source="test.txt",
            source_id="test-doc",
            version="v1.0.0"
        )
        
        doc_id = repository.add_document("Original content", metadata)
        
        # Update content
        success = repository.update_document(doc_id, content="Updated content")
        assert success
        
        # Verify update
        doc = repository.get_document(doc_id)
        assert doc.content == "Updated content"
    
    def test_delete_document(self, repository):
        """Test hard delete"""
        metadata = DocumentMetadata(
            source="test.txt",
            source_id="test-doc",
            version="v1.0.0"
        )
        
        doc_id = repository.add_document("Test content", metadata)
        
        # Delete
        success = repository.delete_document(doc_id)
        assert success
        
        # Verify deletion
        doc = repository.get_document(doc_id)
        assert doc is None
    
    def test_soft_delete_document(self, repository):
        """Test soft delete (deactivation)"""
        metadata = DocumentMetadata(
            source="test.txt",
            source_id="test-doc",
            version="v1.0.0"
        )
        
        doc_id = repository.add_document("Test content", metadata)
        
        # Soft delete
        success = repository.soft_delete_document(doc_id)
        assert success
        
        # Verify document exists but is inactive
        doc = repository.get_document(doc_id)
        assert doc is not None
        assert doc.metadata.is_active is False
    
    def test_query_documents(self, repository):
        """Test semantic search query"""
        # Add test documents
        docs = [
            ("Python is a programming language", "python-doc"),
            ("Java is also a programming language", "java-doc"),
            ("Cybersecurity is important", "security-doc")
        ]
        
        for content, source_id in docs:
            metadata = DocumentMetadata(
                source="test.txt",
                source_id=source_id,
                version="v1.0.0"
            )
            repository.add_document(content, metadata)
        
        # Query for programming-related content
        result = repository.query("programming languages", n_results=2)
        
        assert len(result.documents) > 0
        assert len(result.metadatas) == len(result.documents)
        assert len(result.distances) == len(result.documents)
    
    def test_list_documents(self, repository):
        """Test listing documents with filters"""
        # Add documents with different metadata
        for i in range(5):
            metadata = DocumentMetadata(
                source="test.txt",
                source_id=f"doc-{i}",
                version="v1.0.0" if i < 3 else "v2.0.0",
                is_active=True if i < 4 else False
            )
            repository.add_document(f"Document {i}", metadata)
        
        # List all documents
        all_docs = repository.list_documents()
        assert len(all_docs) == 5
        
        # Filter by version
        v1_docs = repository.list_documents(where={"version": "v1.0.0"})
        assert len(v1_docs) == 3
        
        # Filter by active status
        active_docs = repository.list_documents(where={"is_active": True})
        assert len(active_docs) == 4
    
    def test_count_documents(self, repository):
        """Test document counting"""
        # Initially empty
        assert repository.count_documents() == 0
        
        # Add documents
        for i in range(5):
            metadata = DocumentMetadata(
                source="test.txt",
                source_id=f"doc-{i}",
                version="v1.0.0"
            )
            repository.add_document(f"Document {i}", metadata)
        
        # Count all
        assert repository.count_documents() == 5
        
        # Count with filter
        metadata = DocumentMetadata(
            source="other.txt",
            source_id="other-doc",
            version="v1.0.0"
        )
        repository.add_document("Other document", metadata)
        
        count = repository.count_documents(where={"source": "test.txt"})
        assert count == 5
    
    def test_deactivate_old_versions(self, repository):
        """Test version management"""
        # Add multiple versions of same document
        for version in ["v1.0.0", "v2.0.0", "v3.0.0"]:
            metadata = DocumentMetadata(
                source="test.txt",
                source_id="my-doc",
                version=version,
                is_active=True
            )
            repository.add_document(f"Content {version}", metadata)
        
        # Deactivate old versions, keep v3.0.0
        deactivated = repository.deactivate_old_versions("my-doc", "v3.0.0")
        assert deactivated == 2
        
        # Verify only v3.0.0 is active
        docs = repository.list_documents(where={"source_id": "my-doc"})
        active_docs = [d for d in docs if d.metadata.is_active]
        assert len(active_docs) == 1
        assert active_docs[0].metadata.version == "v3.0.0"


# ==================== RAGService Tests ====================

class TestRAGService:
    """Test RAGService functionality"""
    
    def test_add_document(self, service):
        """Test adding document via service"""
        result = service.add_document(
            content="Test document",
            source="test.txt",
            source_id="test-doc",
            version="v1.0.0",
            tags=["test", "example"]
        )
        
        assert result["status"] == "success"
        assert "document_id" in result
    
    def test_add_documents_batch(self, service):
        """Test batch adding documents"""
        documents = [
            {
                "content": f"Document {i}",
                "source": "test.txt",
                "source_id": f"doc-{i}",
                "version": "v1.0.0",
                "tags": ["test"]
            }
            for i in range(3)
        ]
        
        result = service.add_documents_batch(documents)
        
        assert result["status"] == "success"
        assert result["count"] == 3
    
    def test_get_document(self, service):
        """Test getting document via service"""
        # Add document
        add_result = service.add_document(
            content="Test content",
            source="test.txt",
            source_id="test-doc",
            version="v1.0.0"
        )
        
        doc_id = add_result["document_id"]
        
        # Get document
        doc = service.get_document(doc_id)
        
        assert doc is not None
        assert doc["content"] == "Test content"
        assert doc["metadata"]["source_id"] == "test-doc"
    
    def test_update_document(self, service):
        """Test updating document via service"""
        # Add document
        add_result = service.add_document(
            content="Original",
            source="test.txt",
            source_id="test-doc",
            version="v1.0.0"
        )
        
        doc_id = add_result["document_id"]
        
        # Update
        update_result = service.update_document(
            document_id=doc_id,
            content="Updated content"
        )
        
        assert update_result["status"] == "success"
        
        # Verify
        doc = service.get_document(doc_id)
        assert doc["content"] == "Updated content"
    
    def test_delete_document(self, service):
        """Test deleting document via service"""
        # Add document
        add_result = service.add_document(
            content="Test",
            source="test.txt",
            source_id="test-doc",
            version="v1.0.0"
        )
        
        doc_id = add_result["document_id"]
        
        # Delete (soft)
        delete_result = service.delete_document(doc_id, soft=True)
        assert delete_result["status"] == "success"
        
        # Verify soft delete
        doc = service.get_document(doc_id)
        assert doc is not None
        assert doc["metadata"]["is_active"] is False
    
    def test_list_documents(self, service):
        """Test listing documents with pagination"""
        # Add documents
        for i in range(25):
            service.add_document(
                content=f"Doc {i}",
                source="test.txt",
                source_id=f"doc-{i}",
                version="v1.0.0"
            )
        
        # Get first page
        result = service.list_documents(page=1, page_size=10)
        
        assert result["status"] == "success"
        assert len(result["documents"]) == 10
        assert result["total"] == 25
        assert result["total_pages"] == 3
    
    def test_query(self, service):
        """Test querying knowledge base"""
        # Add test documents
        service.add_document(
            content="Python is a high-level programming language",
            source="python.txt",
            source_id="python-doc",
            version="v1.0.0",
            tags=["programming"]
        )
        
        service.add_document(
            content="Cybersecurity protects systems from attacks",
            source="security.txt",
            source_id="security-doc",
            version="v1.0.0",
            tags=["security"]
        )
        
        # Query
        result = service.query(
            query_text="programming language",
            top_k=2
        )
        
        assert result["status"] == "success"
        assert len(result["documents"]) > 0
    
    def test_get_stats(self, service):
        """Test getting service statistics"""
        # Add some documents
        service.add_document(
            content="Test",
            source="test.txt",
            source_id="test-doc",
            version="v1.0.0"
        )
        
        # Get stats
        stats = service.get_stats()
        
        assert "repository" in stats
        assert "service" in stats
        assert stats["repository"]["total_documents"] > 0


# ==================== Run Tests ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
