# RAG Module - Quick Start Guide

## Overview

The RAG (Retrieval-Augmented Generation) module is a comprehensive knowledge base management system that enables:

- ✅ **Document Management**: Upload, update, delete documents
- ✅ **Version Control**: Track multiple versions of documents
- ✅ **Semantic Search**: Find relevant information using natural language
- ✅ **AI-Powered Q&A**: Get intelligent answers from your knowledge base
- ✅ **REST API**: Full CRUD operations via HTTP endpoints
- ✅ **Monitoring**: Built-in logging and metrics tracking

## Quick Start

### 1. Installation

The module is already integrated into Cyberfortress SmartXDR Core. No additional installation needed.

Required dependencies:
```
chromadb
openai
pydantic
flask
```

### 2. Start the Server

```bash
python run.py
```

The RAG endpoints will be available at: `http://localhost:8080/api/rag`

### 3. Add Your First Document

```bash
curl -X POST http://localhost:8080/api/rag/documents \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Suricata is an open-source IDS/IPS system that provides network security monitoring.",
    "metadata": {
      "source": "docs/suricata_guide.md",
      "source_id": "suricata-intro",
      "version": "v1.0.0",
      "tags": ["suricata", "ids", "security"]
    }
  }'
```

### 4. Query Your Knowledge Base

```bash
curl -X POST http://localhost:8080/api/rag/query \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is Suricata?",
    "top_k": 3
  }'
```

You'll get an AI-generated answer based on your documents!

## Architecture

```
┌─────────────────────────────────────────────┐
│          Flask REST API                     │
│         (app/routes/rag.py)                 │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│          RAG Service Layer                  │
│         (app/rag/service.py)                │
│  • Business Logic                           │
│  • Document Management                      │
│  • Query Orchestration                      │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│       RAG Repository Layer                  │
│      (app/rag/repository.py)                │
│  • ChromaDB Interface                       │
│  • CRUD Operations                          │
│  • Version Management                       │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│           ChromaDB                          │
│    (Vector Database Storage)                │
└─────────────────────────────────────────────┘
```

## Key Features

### 1. **Dependency Injection**

```python
from app.rag.repository import RAGRepository
from app.rag.service import RAGService

# Custom repository (e.g., for testing)
custom_repo = RAGRepository(
    persist_directory="/path/to/test/db",
    collection_name="test_collection"
)

# Inject into service
rag_service = RAGService(repository=custom_repo)
```

### 2. **Version Management**

```python
# Add v1.0.0
rag_service.add_document(
    content="Original content",
    source="guide.md",
    source_id="my-guide",
    version="v1.0.0"
)

# Add v2.0.0 - automatically deactivates v1.0.0
rag_service.add_document(
    content="Updated content",
    source="guide.md",
    source_id="my-guide",
    version="v2.0.0",
    auto_deactivate_old=True  # Default
)
```

### 3. **Flexible Querying**

```python
# Basic query
result = rag_service.query(
    query_text="How to configure Suricata?",
    top_k=5
)

# Query with filters
result = rag_service.query(
    query_text="Elasticsearch setup",
    top_k=3,
    filters={
        "is_active": True,
        "tags": "elasticsearch"
    }
)
```

### 4. **Monitoring & Metrics**

```python
# Get comprehensive stats
stats = rag_service.get_stats()

print(f"Total documents: {stats['repository']['total_documents']}")
print(f"Active documents: {stats['repository']['active_documents']}")
print(f"Total queries: {stats['service']['total_queries']}")
print(f"Avg query time: {stats['service']['avg_query_time_ms']}ms")
```

## Usage Examples

### Python SDK

```python
from app.rag.service import RAGService

# Initialize (singleton pattern)
rag = RAGService()

# === Document Management ===

# Add single document
result = rag.add_document(
    content="Wazuh is an open-source security monitoring platform...",
    source="docs/wazuh.md",
    source_id="wazuh-intro",
    version="v1.0.0",
    tags=["wazuh", "siem", "security"]
)
doc_id = result["document_id"]

# Add multiple documents
documents = [
    {
        "content": "Document 1 content",
        "source": "doc1.md",
        "source_id": "doc-1",
        "version": "v1.0.0",
        "tags": ["tag1"]
    },
    {
        "content": "Document 2 content",
        "source": "doc2.md",
        "source_id": "doc-2",
        "version": "v1.0.0",
        "tags": ["tag2"]
    }
]
result = rag.add_documents_batch(documents)

# Update document
rag.update_document(
    document_id=doc_id,
    content="Updated content...",
    metadata={"version": "v1.1.0"}
)

# Get document
doc = rag.get_document(doc_id)
print(doc["content"])

# List documents with filters
result = rag.list_documents(
    source_id="wazuh-intro",
    is_active=True,
    page=1,
    page_size=20
)

# Delete document (soft delete)
rag.delete_document(doc_id, soft=True)

# Hard delete
rag.delete_document(doc_id, soft=False)

# === Query & Search ===

# Query knowledge base
result = rag.query(
    query_text="How do I install Wazuh agents?",
    top_k=5,
    filters={"is_active": True}
)

for doc, source in zip(result["documents"], result["metadatas"]):
    print(f"Source: {source['source']}")
    print(f"Content: {doc[:100]}...")

# Build context for LLM
context, sources = rag.build_context_from_query(
    query_text="Configure Suricata",
    top_k=3
)
print(f"Context: {context}")
print(f"Sources: {sources}")

# === Statistics ===

stats = rag.get_stats()
print(f"Repository Stats: {stats['repository']}")
print(f"Service Stats: {stats['service']}")
```

### REST API

See [RAG_API_GUIDE.md](./RAG_API_GUIDE.md) for full API documentation.

## Testing

### Run Unit Tests

```bash
# Run all RAG tests
pytest tests/test_rag_module.py -v

# Run specific test
pytest tests/test_rag_module.py::TestRAGRepository::test_add_document -v

# Run with coverage
pytest tests/test_rag_module.py --cov=app.rag --cov-report=html
```

### Manual Testing

```python
# tests/manual_test_rag.py
from app.rag.service import RAGService

rag = RAGService()

# Add test document
result = rag.add_document(
    content="Test document about Elasticsearch",
    source="test.md",
    source_id="test-doc",
    version="v1.0.0",
    tags=["test", "elasticsearch"]
)

print(f"Added: {result}")

# Query
query_result = rag.query(
    query_text="Tell me about Elasticsearch",
    top_k=1
)

print(f"Query result: {query_result}")

# Clean up
rag.delete_document(result["document_id"], soft=False)
```

## Configuration

### Environment Variables

```bash
# .env
OPENAI_API_KEY=sk-...
DEBUG=true
DEBUG_LLM=true
```

### Application Config

```python
# app/config.py
CHROMA_DB_PATH = "chroma_db"  # Vector database path
COLLECTION_NAME = "knowledge_base"  # Default collection name
```

## Migration from Old RAG

If you're using the old RAG implementation:

**Before**:
```python
```python
from app.services.llm_service import LLMService

llm = LLMService()

# Legacy approach (deprecated):
# collection = initialize_database()
# result = llm.ask_rag(collection, query="What is Suricata?")

# Current recommended approach:
result = llm.ask_rag(query="What is Suricata?", top_k=5)
```

The method now uses `RAGService` internally - no need to pass collection.

## Best Practices

### 1. Use Semantic Versioning

```python
# ✅ Good
version="v1.0.0"
version="v2.1.0"
version="2024-12-10"

# ❌ Avoid
version="latest"
version="1"
```

### 2. Tag Your Documents

```python
# ✅ Good - specific tags
tags=["suricata", "ids", "network-security", "configuration"]

# ❌ Avoid - too generic
tags=["security"]
```

### 3. Use Filters for Queries

```python
# ✅ Good - narrow down search
rag.query(
    query_text="agent configuration",
    filters={
        "is_active": True,
        "tags": "wazuh"
    }
)

# ❌ Less optimal - too broad
rag.query(query_text="configuration")
```

### 4. Batch Operations

```python
# ✅ Good - single batch request
documents = [...]  # 100 documents
rag.add_documents_batch(documents)

# ❌ Avoid - multiple single requests
for doc in documents:
    rag.add_document(...)
```

## Troubleshooting

### Issue: "OPENAI_API_KEY not found"

**Solution**: Add your API key to `.env`:
```bash
OPENAI_API_KEY=sk-your-key-here
```

### Issue: ChromaDB initialization error

**Solution**: Ensure write permissions on the `chroma_db` directory:
```bash
chmod -R 755 chroma_db/
```

### Issue: Empty query results

**Causes**:
1. No documents in database
2. Filters too restrictive
3. Documents marked as inactive

**Solution**:
```python
# Check total documents
stats = rag.get_stats()
print(stats["repository"]["total_documents"])

# Query without filters
result = rag.query(query_text="your query", filters={})
```

## Performance Tips

1. **Use filters**: Reduce search space for faster queries
2. **Batch operations**: Add multiple documents at once
3. **Cache**: Enable semantic cache for repeated queries
4. **Limit top_k**: Don't retrieve more documents than needed

```python
# Optimized query
result = rag.query(
    query_text="specific question",
    top_k=3,  # Only get top 3
    filters={"is_active": True, "tags": "relevant-tag"}
)
```

## API Reference

- **Full API Documentation**: [RAG_API_GUIDE.md](./RAG_API_GUIDE.md)
- **Schema Reference**: `app/rag/schemas.py`
- **Models Reference**: `app/rag/models.py`

## Support

- **Issues**: Check `logs/` directory for error logs
- **Tests**: Run `pytest tests/test_rag_module.py -v`
- **Stats**: `GET /api/rag/stats` for system health

## License

Part of Cyberfortress SmartXDR Core - Internal Module

---

**Version**: 1.0.0  
**Last Updated**: 2025-12-10
