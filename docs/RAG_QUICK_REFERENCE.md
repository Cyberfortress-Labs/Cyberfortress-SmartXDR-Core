# RAG Module - Quick Reference Card

## Installation & Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="sk-..."

# Start server
python run.py
```

## Python SDK - Common Operations

### Initialize Service
```python
from app.rag.service import RAGService
rag = RAGService()
```

### Add Document
```python
result = rag.add_document(
    content="Your document content here...",
    source="docs/guide.md",
    source_id="my-guide",
    version="v1.0.0",
    tags=["security", "guide"]
)
doc_id = result["document_id"]
```

### Update Document
```python
rag.update_document(
    document_id=doc_id,
    content="Updated content...",
    metadata={"version": "v1.1.0"}
)
```

### Query Knowledge Base
```python
result = rag.query(
    query_text="How do I configure Suricata?",
    top_k=5,
    filters={"is_active": True, "tags": "security"}
)
print(result["documents"])
print(result["sources"])
```

### List Documents
```python
result = rag.list_documents(
    source_id="my-guide",
    is_active=True,
    page=1,
    page_size=20
)
print(f"Total: {result['total']}")
```

### Delete Document
```python
# Soft delete (mark inactive)
rag.delete_document(doc_id, soft=True)

# Hard delete (permanent)
rag.delete_document(doc_id, soft=False)
```

### Get Statistics
```python
stats = rag.get_stats()
print(f"Total docs: {stats['repository']['total_documents']}")
print(f"Avg query time: {stats['service']['avg_query_time_ms']}ms")
```

## REST API - Quick Reference

### Authentication
```bash
# All requests need API key
-H "X-API-Key: your-api-key"
```

### Create Document
```bash
curl -X POST http://localhost:8080/api/rag/documents \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Document content...",
    "metadata": {
      "source": "docs/guide.md",
      "source_id": "guide",
      "version": "v1.0.0",
      "tags": ["security"]
    }
  }'
```

### List Documents
```bash
# All documents
curl "http://localhost:8080/api/rag/documents" \
  -H "X-API-Key: your-api-key"

# With filters
curl "http://localhost:8080/api/rag/documents?is_active=true&tags=security" \
  -H "X-API-Key: your-api-key"

# Pagination
curl "http://localhost:8080/api/rag/documents?page=2&page_size=10" \
  -H "X-API-Key: your-api-key"
```

### Get Document
```bash
curl "http://localhost:8080/api/rag/documents/doc_abc123" \
  -H "X-API-Key: your-api-key"
```

### Update Document
```bash
curl -X PUT "http://localhost:8080/api/rag/documents/doc_abc123" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Updated content...",
    "metadata": {"version": "v2.0.0"}
  }'
```

### Delete Document
```bash
# Soft delete
curl -X DELETE "http://localhost:8080/api/rag/documents/doc_abc123" \
  -H "X-API-Key: your-api-key"

# Hard delete
curl -X DELETE "http://localhost:8080/api/rag/documents/doc_abc123?hard=true" \
  -H "X-API-Key: your-api-key"
```

### Query Knowledge Base
```bash
curl -X POST http://localhost:8080/api/rag/query \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How to configure Suricata?",
    "top_k": 5,
    "filters": {"is_active": true}
  }'
```

### Get Statistics
```bash
curl "http://localhost:8080/api/rag/stats" \
  -H "X-API-Key: your-api-key"
```

### Health Check
```bash
curl "http://localhost:8080/api/rag/health"
```

## Common Patterns

### Batch Upload
```python
documents = [
    {
        "content": f"Document {i} content",
        "source": f"doc{i}.md",
        "source_id": f"doc-{i}",
        "version": "v1.0.0",
        "tags": ["batch"]
    }
    for i in range(10)
]
rag.add_documents_batch(documents)
```

### Version Management
```python
# Upload v1.0.0
rag.add_document(..., version="v1.0.0", source_id="guide")

# Upload v2.0.0 - automatically deactivates v1.0.0
rag.add_document(..., version="v2.0.0", source_id="guide")

# List only active versions
result = rag.list_documents(
    source_id="guide",
    is_active=True
)
```

### Filtered Query
```python
# Only search in Wazuh docs
result = rag.query(
    query_text="agent configuration",
    filters={
        "is_active": True,
        "tags": "wazuh"
    },
    top_k=3
)
```

### Context Building
```python
# Get context for LLM
context, sources = rag.build_context_from_query(
    query_text="Elasticsearch setup",
    top_k=5
)
print(f"Context:\n{context}")
print(f"Sources: {sources}")
```

## Testing

### Run All Tests
```bash
pytest tests/test_rag_module.py -v
```

### Run Specific Test
```bash
pytest tests/test_rag_module.py::TestRAGService::test_query -v
```

### Coverage Report
```bash
pytest tests/test_rag_module.py --cov=app.rag --cov-report=html
```

## Migration

### From Old RAG
```bash
# Preview migration (dry run)
python scripts/migrate_to_new_rag.py --dry-run

# Execute migration
python scripts/migrate_to_new_rag.py

# Verify
python scripts/migrate_to_new_rag.py --verify
```

## Troubleshooting

### Check Service Health
```python
stats = rag.get_stats()
print(stats)
```

### Check Document Count
```python
count = rag.repository.count_documents()
print(f"Total documents: {count}")
```

### View Recent Logs
```bash
tail -f logs/smartxdr.log | grep RAG
```

### Reset Collection (Testing Only!)
```python
rag.reset()  # Deletes all documents!
```

## Rate Limits

| Operation | Limit |
|-----------|-------|
| Create/Update/Delete | 30/min |
| Batch Operations | 10/min |
| Query | 30/min |
| List/Stats | 60/min |

## Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request (validation error) |
| 401 | Unauthorized (missing/invalid API key) |
| 404 | Not Found |
| 429 | Rate Limit Exceeded |
| 500 | Internal Server Error |

## Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...

# Optional
DEBUG=true
DEBUG_LLM=true
CHROMA_DB_PATH=chroma_db
```

## Documentation Links

- Full API Guide: `docs/RAG_API_GUIDE.md`
- Module README: `docs/RAG_MODULE_README.md`
- Implementation Summary: `docs/RAG_IMPLEMENTATION_SUMMARY.md`

---

**Quick Tip**: Use `--help` with any script:
```bash
python scripts/migrate_to_new_rag.py --help
```
