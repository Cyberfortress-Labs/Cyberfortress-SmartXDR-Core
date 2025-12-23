# RAG Data Directory

This directory contains documents for the RAG (Retrieval-Augmented Generation) knowledge base.

## Auto-Sync Feature

Files in this directory are automatically synchronized with ChromaDB:

```bash
# Sync all files (detect new/updated/deleted)
./start rag_sync

# Dry run (see what would happen)
./start rag_sync --dry-run

# Force re-index all files
./start rag_sync --force
```

## Directory Structure

Subdirectories are treated as **categories/topics**:

```
data/
├── wazuh/           → category: "wazuh"
│   ├── alerts.md
│   └── rules.pdf
├── suricata/        → category: "suricata"
│   └── signatures.json
└── general/         → category: "general"
    └── doc.txt
```

## Supported File Types

- **Text**: `.md`, `.txt`, `.rst`
- **Code**: `.py`, `.js`, `.ts`, `.go`, `.java`
- **Data**: `.json`, `.yaml`, `.yml`
- **PDF**: `.pdf` (text extracted automatically)

## How It Works

1. **Detect**: Scans directory, compares file hashes with indexed documents
2. **Action**: Processes new files, updates changed files, removes deleted files
3. **Clean**: Removes orphaned entries from ChromaDB

File changes are detected using SHA256 hash of content (not just modification time).

## Notes

- This directory is gitignored (except README.md)
- Files are mounted read-only in Docker (`./data:/app/data:ro`)
- Max file size: 10MB
