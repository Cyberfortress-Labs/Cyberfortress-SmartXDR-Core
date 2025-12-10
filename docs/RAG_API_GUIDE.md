# RAG Module - API Documentation

## Overview

The RAG (Retrieval-Augmented Generation) module provides a comprehensive knowledge base management system for Cyberfortress SmartXDR Core. It enables:

- **Document Management**: CRUD operations for knowledge base documents
- **Version Control**: Track and manage different versions of documents
- **Semantic Search**: Query documents using natural language
- **AI-Powered Q&A**: Get intelligent answers from your knowledge base

## Architecture

```
app/rag/
├── __init__.py          # Module initialization
├── models.py            # Data models (Document, DocumentMetadata, QueryResult)
├── schemas.py           # Pydantic schemas for API validation
├── repository.py        # Data access layer (ChromaDB)
├── service.py           # Business logic layer
├── monitoring.py        # Logging and metrics
└── routes/
    └── rag.py          # REST API endpoints
```

### Design Patterns

- **Repository Pattern**: Abstracts data access for easy database swapping
- **Service Layer**: Encapsulates business logic
- **Dependency Injection**: Services can be injected for testing
- **Singleton Pattern**: Ensures single instance of service components

## API Endpoints

Base URL: `/api/rag`

### Authentication

All endpoints (except `/health`) require API key authentication:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:8080/api/rag/stats
```

### Rate Limiting

- Document CRUD: 30 requests/minute
- Batch operations: 10 requests/minute
- Queries: 30 requests/minute
- Stats/List: 60 requests/minute

---

## Document Management

### 1. Create Document

**Endpoint**: `POST /api/rag/documents`

**Description**: Add a new document to the knowledge base.

**Request Body**:
```json
{
  "content": "Suricata is an open-source intrusion detection system...",
  "metadata": {
    "source": "docs/suricata_guide.md",
    "source_id": "suricata-guide",
    "version": "v2.0.0",
    "is_active": true,
    "tags": ["security", "ids", "suricata"],
    "custom_metadata": {
      "author": "security_team",
      "reviewed": true
    }
  }
}
```

**Response** (201 Created):
```json
{
  "status": "success",
  "data": {
    "id": "doc_a1b2c3d4e5f6",
    "content": "Suricata is an open-source...",
    "metadata": {
      "source": "docs/suricata_guide.md",
      "source_id": "suricata-guide",
      "version": "v2.0.0",
      "is_active": true,
      "tags": "security,ids,suricata",
      "created_at": "2025-12-10T10:30:00Z",
      "updated_at": "2025-12-10T10:30:00Z"
    },
    "created_at": "2025-12-10T10:30:00Z"
  },
  "message": "Document added successfully"
}
```

**Example**:
```bash
curl -X POST http://localhost:8080/api/rag/documents \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Elasticsearch is a distributed search engine...",
    "metadata": {
      "source": "docs/elasticsearch.md",
      "source_id": "elasticsearch-doc",
      "version": "v1.0.0",
      "tags": ["elasticsearch", "search"]
    }
  }'
```

---

### 2. Create Documents (Batch)

**Endpoint**: `POST /api/rag/documents/batch`

**Description**: Add multiple documents at once.

**Request Body**:
```json
[
  {
    "content": "Document 1 content...",
    "metadata": {
      "source": "doc1.md",
      "source_id": "doc-1",
      "version": "v1.0.0",
      "tags": ["tag1"]
    }
  },
  {
    "content": "Document 2 content...",
    "metadata": {
      "source": "doc2.md",
      "source_id": "doc-2",
      "version": "v1.0.0",
      "tags": ["tag2"]
    }
  }
]
```

**Response** (201 Created):
```json
{
  "status": "success",
  "data": {
    "document_ids": ["doc_abc123", "doc_def456"],
    "count": 2
  },
  "message": "Successfully added 2 documents"
}
```

---

### 3. List Documents

**Endpoint**: `GET /api/rag/documents`

**Description**: List documents with filtering and pagination.

**Query Parameters**:
- `source_id` (optional): Filter by source ID
- `source` (optional): Filter by source path
- `version` (optional): Filter by version
- `tags` (optional): Comma-separated tags (AND logic)
- `is_active` (optional): Filter by active status (`true`/`false`)
- `page` (optional, default=1): Page number
- `page_size` (optional, default=20, max=100): Items per page

**Example**:
```bash
# List all active documents
curl "http://localhost:8080/api/rag/documents?is_active=true" \
  -H "X-API-Key: your-api-key"

# Filter by source_id and tags
curl "http://localhost:8080/api/rag/documents?source_id=suricata-guide&tags=security,ids" \
  -H "X-API-Key: your-api-key"

# Pagination
curl "http://localhost:8080/api/rag/documents?page=2&page_size=10" \
  -H "X-API-Key: your-api-key"
```

**Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "documents": [
      {
        "id": "doc_abc123",
        "content": "Document content...",
        "metadata": {
          "source": "docs/guide.md",
          "source_id": "guide-doc",
          "version": "v1.0.0",
          "is_active": true,
          "tags": "security,guide",
          "created_at": "2025-12-10T10:00:00Z",
          "updated_at": "2025-12-10T10:00:00Z"
        }
      }
    ],
    "total": 25,
    "page": 1,
    "page_size": 20,
    "total_pages": 2
  }
}
```

---

### 4. Get Document

**Endpoint**: `GET /api/rag/documents/{document_id}`

**Description**: Retrieve a single document by ID.

**Example**:
```bash
curl http://localhost:8080/api/rag/documents/doc_abc123 \
  -H "X-API-Key: your-api-key"
```

**Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "id": "doc_abc123",
    "content": "Full document content here...",
    "metadata": {
      "source": "docs/guide.md",
      "source_id": "guide-doc",
      "version": "v1.0.0",
      "is_active": true,
      "tags": "security,guide",
      "created_at": "2025-12-10T10:00:00Z",
      "updated_at": "2025-12-10T10:00:00Z"
    },
    "created_at": "2025-12-10T10:00:00Z"
  }
}
```

**Response** (404 Not Found):
```json
{
  "status": "error",
  "error": "Document doc_xyz789 not found"
}
```

---

### 5. Update Document

**Endpoint**: `PUT /api/rag/documents/{document_id}`

**Description**: Update document content and/or metadata.

**Request Body** (all fields optional):
```json
{
  "content": "Updated content...",
  "metadata": {
    "version": "v2.0.0",
    "is_active": true,
    "tags": ["security", "updated"]
  }
}
```

**Example**:
```bash
curl -X PUT http://localhost:8080/api/rag/documents/doc_abc123 \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Updated document content...",
    "metadata": {
      "version": "v2.0.0"
    }
  }'
```

**Response** (200 OK):
```json
{
  "status": "success",
  "message": "Document updated successfully"
}
```

---

### 6. Delete Document

**Endpoint**: `DELETE /api/rag/documents/{document_id}`

**Description**: Delete a document (soft delete by default).

**Query Parameters**:
- `hard` (optional, default=false): Set to `true` for permanent deletion

**Example**:
```bash
# Soft delete (mark as inactive)
curl -X DELETE http://localhost:8080/api/rag/documents/doc_abc123 \
  -H "X-API-Key: your-api-key"

# Hard delete (permanent)
curl -X DELETE "http://localhost:8080/api/rag/documents/doc_abc123?hard=true" \
  -H "X-API-Key: your-api-key"
```

**Response** (200 OK):
```json
{
  "status": "success",
  "message": "Document deactivated successfully"
}
```

---

## RAG Query

### Query Knowledge Base

**Endpoint**: `POST /api/rag/query`

**Description**: Ask questions and get AI-powered answers from your knowledge base.

**Request Body**:
```json
{
  "query": "How do I configure Suricata IDS?",
  "top_k": 5,
  "filters": {
    "is_active": true,
    "tags": "security"
  },
  "include_sources": true
}
```

**Parameters**:
- `query` (required): Your question
- `top_k` (optional, default=5, max=20): Number of documents to retrieve
- `filters` (optional): Metadata filters
  - `source`: Filter by source path
  - `source_id`: Filter by source ID
  - `version`: Filter by version
  - `is_active`: Filter by active status
  - `tags`: Filter by tag
- `include_sources` (optional, default=true): Include source documents in response

**Example**:
```bash
curl -X POST http://localhost:8080/api/rag/query \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the difference between Suricata and Snort?",
    "top_k": 3,
    "filters": {
      "is_active": true,
      "tags": "ids"
    }
  }'
```

**Response** (200 OK):
```json
{
  "status": "success",
  "answer": "Suricata and Snort are both open-source intrusion detection systems, but they have key differences:\n\n1. **Multi-threading**: Suricata supports multi-threading natively, while Snort is primarily single-threaded...\n\n2. **Protocol Support**: Suricata includes better support for modern protocols like HTTP/2...\n\nSources: docs/suricata_guide.md, docs/ids_comparison.md",
  "sources": [
    "docs/suricata_guide.md",
    "docs/ids_comparison.md"
  ],
  "cached": false,
  "metadata": {
    "documents_retrieved": 3,
    "processing_time_ms": 234
  }
}
```

---

## Statistics

### Get Statistics

**Endpoint**: `GET /api/rag/stats`

**Description**: Get knowledge base statistics and metrics.

**Example**:
```bash
curl http://localhost:8080/api/rag/stats \
  -H "X-API-Key: your-api-key"
```

**Response** (200 OK):
```json
{
  "status": "success",
  "data": {
    "total_documents": 150,
    "active_documents": 145,
    "unique_sources": 42,
    "unique_source_ids": 38,
    "tags_distribution": {
      "security": 65,
      "ids": 23,
      "elasticsearch": 18,
      "wazuh": 15
    },
    "version_distribution": {
      "v1.0.0": 80,
      "v2.0.0": 60,
      "v3.0.0": 10
    },
    "service_stats": {
      "total_queries": 1250,
      "total_documents_added": 150,
      "total_documents_updated": 45,
      "total_documents_deleted": 5,
      "avg_query_time_ms": 187.5
    }
  }
}
```

---

## Health Check

### Health Check

**Endpoint**: `GET /api/rag/health`

**Description**: Check if RAG service is healthy (no authentication required).

**Example**:
```bash
curl http://localhost:8080/api/rag/health
```

**Response** (200 OK):
```json
{
  "status": "healthy",
  "service": "rag",
  "version": "1.0.0"
}
```

---

## Usage Examples

### Example 1: Import Documentation

```bash
# Add Suricata documentation
curl -X POST http://localhost:8080/api/rag/documents \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Suricata Configuration Guide\n\nTo configure Suricata...",
    "metadata": {
      "source": "docs/suricata/config_guide.md",
      "source_id": "suricata-config",
      "version": "v1.0.0",
      "tags": ["suricata", "ids", "configuration"]
    }
  }'
```

### Example 2: Update Documentation Version

```bash
# Upload new version
curl -X POST http://localhost:8080/api/rag/documents \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Suricata Configuration Guide v2\n\nUpdated for Suricata 7.0...",
    "metadata": {
      "source": "docs/suricata/config_guide.md",
      "source_id": "suricata-config",
      "version": "v2.0.0",
      "tags": ["suricata", "ids", "configuration"]
    }
  }'

# Old v1.0.0 is automatically marked as inactive
```

### Example 3: Query for Information

```bash
# Ask a question
curl -X POST http://localhost:8080/api/rag/query \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I enable JSON logging in Suricata?",
    "filters": {
      "is_active": true
    }
  }'
```

---

## Python SDK Usage

```python
from app.rag.service import RAGService

# Initialize service
rag_service = RAGService()

# Add document
result = rag_service.add_document(
    content="Elasticsearch is a distributed search engine...",
    source="docs/elasticsearch.md",
    source_id="elasticsearch-doc",
    version="v1.0.0",
    tags=["elasticsearch", "search"]
)

print(f"Document added: {result['document_id']}")

# Query knowledge base
query_result = rag_service.query(
    query_text="How do I configure Elasticsearch?",
    top_k=5,
    filters={"is_active": True}
)

print(f"Found {len(query_result['documents'])} relevant documents")
print(f"Sources: {query_result['sources']}")

# Get statistics
stats = rag_service.get_stats()
print(f"Total documents: {stats['repository']['total_documents']}")
```

---

## Error Handling

All endpoints return consistent error responses:

```json
{
  "status": "error",
  "error": "Error message describing what went wrong",
  "details": {
    // Optional additional error details
  }
}
```

Common HTTP Status Codes:
- `200 OK`: Successful operation
- `201 Created`: Resource created successfully
- `400 Bad Request`: Invalid request (validation error)
- `401 Unauthorized`: Missing or invalid API key
- `404 Not Found`: Resource not found
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error

---

## Best Practices

### 1. Version Management

Always use semantic versioning and let the system auto-deactivate old versions:

```python
# Good
result = rag_service.add_document(
    content="Updated content...",
    source="docs/guide.md",
    source_id="security-guide",
    version="v2.1.0",  # Clear version
    auto_deactivate_old=True  # Auto-deactivate v2.0.0 and older
)
```

### 2. Use Tags for Organization

```python
rag_service.add_document(
    content="...",
    source="docs/wazuh.md",
    source_id="wazuh-guide",
    version="v1.0.0",
    tags=["wazuh", "siem", "security", "logging"]  # Multiple tags
)
```

### 3. Query Optimization

Use filters to narrow down search scope:

```python
# Good - specific query with filters
result = rag_service.query(
    query_text="Wazuh agent configuration",
    top_k=3,
    filters={
        "is_active": True,
        "tags": "wazuh"
    }
)

# Less optimal - too broad
result = rag_service.query(
    query_text="configuration",
    top_k=20
)
```

### 4. Batch Operations

Use batch endpoints for bulk operations:

```python
# Good - single batch request
documents = [...]  # 100 documents
rag_service.add_documents_batch(documents)

# Bad - 100 separate requests
for doc in documents:
    rag_service.add_document(...)  # Slow!
```

---

## Migration Guide

### From Old RAG to New Module

**Old Code**:
```python
from app.services.llm_service import LLMService

llm_service = LLMService()

# Legacy code (deprecated):
# collection = initialize_database()
# result = llm_service.ask_rag(collection=collection, query="...", n_results=5)

# Current recommended approach:
result = llm_service.ask_rag(
    query="How to configure Suricata?",
    top_k=5,
    filters={"is_active": True}
)
```

---

## Troubleshooting

### Issue: Documents not found in query

**Solution**: Check if documents are active and filters are correct:
```bash
# Verify document exists and is active
curl "http://localhost:8080/api/rag/documents?source_id=my-doc&is_active=true" \
  -H "X-API-Key: your-api-key"
```

### Issue: Rate limit exceeded

**Solution**: Reduce request frequency or use batch endpoints:
```bash
# Error response
{
  "status": "error",
  "error": "Rate limit exceeded. Please wait a moment before trying again."
}
```

Wait 60 seconds or use batch operations.

### Issue: Empty query results

**Possible causes**:
1. No documents match the filters
2. Distance threshold too strict
3. Query too vague

**Solution**:
```python
# Broaden search
result = rag_service.query(
    query_text="your query",
    top_k=10,  # Increase results
    filters={"is_active": True}  # Remove specific filters
)
```

---

## Support

For issues or questions:
- Check logs: `logs/` directory
- Review test cases: `tests/test_rag_module.py`
- API errors include `request_id` for debugging

---

**Version**: 1.0.0  
**Last Updated**: 2025-12-10
