"""
Optimized Document Ingestion for RAG

Ultra-fast, memory-efficient implementation with two modes:
1. Direct ChromaDB access (bypass RAGService overhead)
2. REST API mode (use Flask RAG endpoints)

Features:
- Batch processing (bulk upsert)
- Minimal metadata
- Flexible directory selection
- Progress tracking
- Graceful shutdown (Ctrl+C)

Usage:
    # Direct mode (fastest)
    python scripts/quick_rag_docs.py /path/to/docs --limit 10
    python scripts/quick_rag_docs.py docs-for-rag
    
    # API mode (requires running server)
    python scripts/quick_rag_docs.py /path/to/docs --api --api-url http://localhost:8080 --api-key YOUR_KEY
    
    # Dry run
    python scripts/quick_rag_docs.py /path/to/docs --dry-run
"""
import argparse
import sys
import os
import signal
import time
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
import hashlib
import requests
import json

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import *
import chromadb
from app.core.embeddings import OpenAIEmbeddingFunction
from app.core.chunking import (
    json_to_natural_text, 
    mitre_to_natural_text,
    markdown_to_chunks,
    text_to_chunks
)


# Global shutdown flag
shutdown_requested = False

def signal_handler(sig, frame):
    global shutdown_requested
    print("\nStopping after current batch...")
    shutdown_requested = True
    signal.signal(signal.SIGINT, signal.SIG_DFL)


class OptimizedIngester:
    """
    Optimized ingestion with two modes:
    1. Direct ChromaDB access (fastest)
    2. REST API calls (requires running server)
    """
    
    SUPPORTED_EXT = {'.md', '.txt', '.rst', '.json', '.yaml', '.yml', '.py', '.js', '.ts', '.go', '.java'}
    SKIP = {'__pycache__', '.git', '.venv', 'node_modules', '.pytest_cache', 'chroma_db'}
    MAX_SIZE = 5 * 1024 * 1024  # 5MB
    
    def __init__(
        self, 
        chunk_size=MAX_CHUNK_SIZE, 
        batch_size=BATCH_SIZE,
        use_api=False,
        api_url=None,
        api_key=None,
        force_reindex=False
    ):
        self.chunk_size = chunk_size
        self.batch_size = batch_size
        self.use_api = use_api
        self.api_url = api_url
        self.api_key = api_key
        self.force_reindex = force_reindex
        self.stats = {'files': 0, 'chunks': 0, 'errors': 0, 'skipped': 0, 'duplicates': 0}
        self.start_time = time.time()
        self.existing_sources = set()  # Track existing file sources
        
        if use_api:
            self._init_api_mode()
        else:
            self._init_direct_mode()
    
    def _init_api_mode(self):
        """Initialize API mode"""
        print("API Mode")
        print(f"URL: {self.api_url}")
        
        # Validate connection
        try:
            resp = requests.get(
                f"{self.api_url}/health",
                timeout=5
            )
            if resp.status_code != 200:
                raise Exception(f"Health check failed: {resp.status_code}")
            print("Server connection OK\n")
        except Exception as e:
            raise Exception(f"Cannot connect to API: {e}")
    
    def _init_direct_mode(self):
        """Initialize direct ChromaDB access using RAGRepository"""
        print("⚡ Direct ChromaDB Mode (via RAGRepository)")
        
        # Use RAGRepository for unified ChromaDB initialization
        # This handles Docker vs local client selection automatically
        from app.rag.repository import RAGRepository
        
        print("Initializing ChromaDB via RAGRepository...")
        self.repo = RAGRepository(
            persist_directory=str(CHROMA_DB_PATH),
            collection_name="knowledge_base"
        )
        
        # Get collection reference for direct operations
        self.collection = self.repo.collection
        self.embed_fn = self.repo.embedding_function
        
        current_count = self.collection.count()
        print(f"Collection ready: {current_count} docs")
        
        # Load existing sources for duplicate detection
        if current_count > 0 and not self.force_reindex:
            print("Loading existing documents for duplicate detection...")
            try:
                # Get all documents with metadata
                results = self.collection.get(
                    include=['metadatas']
                )
                
                # Extract unique sources
                if results and results['metadatas']:
                    for meta in results['metadatas']:
                        if meta and 'source' in meta:
                            self.existing_sources.add(meta['source'])
                
                print(f"Found {len(self.existing_sources)} existing unique files")
            except Exception as e:
                print(f"Could not load existing sources: {e}")
        
        print()
    
    def should_skip(self, path: Path) -> bool:
        if any(s in str(path) for s in self.SKIP):
            return True
        if path.suffix.lower() not in self.SUPPORTED_EXT:
            return True
        try:
            size = path.stat().st_size
            if size == 0 or size > self.MAX_SIZE:
                return True
        except:
            return True
        return False
    
    def read_file(self, path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding='utf-8')
        except:
            try:
                return path.read_text(encoding='latin-1')
            except:
                return None
    
    def chunk_text(self, text: str, file_ext: str = '', filename: str = '') -> List[str]:
        """
        Smart chunking based on file type using LangChain splitters.
        Benefits: Chunk overlap for context, smart boundary detection.
        
        - JSON: Delegate to app.core.chunking for semantic processing
        - Markdown: Use markdown_to_chunks with header-aware splitting
        - Others: Use text_to_chunks with RecursiveCharacterTextSplitter
        """
        if not text or not text.strip():
            return []
        
        # Short content - no need to chunk
        if len(text) <= self.chunk_size:
            return [text]
        
        # Route by file extension
        ext_lower = file_ext.lower()
        
        # JSON files - semantic chunking
        if ext_lower == '.json':
            return self._chunk_json(text, filename)
        
        # Markdown files - header-aware chunking with overlap
        if ext_lower in {'.md', '.markdown', '.rst'}:
            return markdown_to_chunks(text, filename, self.chunk_size)
        
        # All other text files - use RecursiveCharacterTextSplitter with overlap
        return text_to_chunks(text, filename, self.chunk_size)
    
    def _chunk_json(self, text: str, filename: str = "") -> List[str]:
        """
        Smart JSON chunking - delegate to app.core.chunking.json_to_natural_text
        This reuses the semantic chunking logic with IP-first lookup chunks
        """
        try:
            data = json.loads(text)
            
            # Check if it's a device JSON (has id, name, category)
            if isinstance(data, dict) and 'id' in data and 'name' in data:
                # Use semantic chunking from app.core.chunking
                # This creates IP-first lookup chunks automatically
                return json_to_natural_text(data, filename)
            
            # Check for MITRE technique
            if isinstance(data, dict) and 'mitre_id' in data:
                return [mitre_to_natural_text(data)]
            
            # Fallback for other JSON - use text_to_chunks with overlap
            text_formatted = json.dumps(data, indent=2, ensure_ascii=False)
            if len(text_formatted) <= self.chunk_size:
                return [text_formatted]
            else:
                return text_to_chunks(text_formatted, filename, self.chunk_size)
            
        except json.JSONDecodeError:
            # Not valid JSON, use text_to_chunks with overlap
            return text_to_chunks(text, filename, self.chunk_size)
    
    def get_category(self, path: Path, base: Path) -> str:
        """Simple category extraction"""
        rel = path.relative_to(base)
        parts = [p.lower() for p in rel.parts]
        
        category_map = {
            'wazuh': 'wazuh',
            'suricata': 'suricata',
            'zeek': 'zeek',
            'dfir-iris': 'iris',
            'elastalert': 'elastalert',
            'mitre': 'mitre'
        }
        
        return category_map.get(parts[0], parts[0]) if parts else 'general'
    
    def process_batch(self, batch: List[Dict]):
        """
        Bulk upsert batch to ChromaDB or API
        Much faster than one-by-one
        """
        if not batch:
            return
        
        try:
            if self.use_api:
                self._process_batch_api(batch)
            else:
                self._process_batch_direct(batch)
            
            self.stats['chunks'] += len(batch)
        except Exception as e:
            print(f"  ✗ Batch failed: {str(e)[:100]}")
            self.stats['errors'] += 1
    
    def _process_batch_direct(self, batch: List[Dict]):
        """Direct ChromaDB upsert"""
        self.collection.upsert(
            ids=[item['id'] for item in batch],
            documents=[item['doc'] for item in batch],
            metadatas=[item['meta'] for item in batch]
        )
    
    def _process_batch_api(self, batch: List[Dict]):
        """API batch upload"""
        docs = []
        for item in batch:
            docs.append({
                'id': item['id'],
                'content': item['doc'],
                'metadata': item['meta']
            })
        
        resp = requests.post(
            f"{self.api_url}/api/rag/documents/batch",
            headers={
                'X-API-Key': self.api_key,
                'Content-Type': 'application/json'
            },
            json={'documents': docs},
            timeout=60
        )
        
        if resp.status_code not in [200, 201]:
            raise Exception(f"API error: {resp.status_code} - {resp.text[:200]}")
    
    def ingest(self, directory: Path, limit: Optional[int] = None, dry_run: bool = False):
        """Main ingestion loop with progress tracking"""
        global shutdown_requested
        
        print("=" * 70)
        print("RAG Document Ingestion")
        print("=" * 70)
        print(f"Source: {directory.absolute()}")
        print(f"Mode: {'API' if self.use_api else '⚡ Direct ChromaDB'}")
        print(f"Chunk size: {self.chunk_size}")
        print(f"Batch size: {self.batch_size}")
        if limit:
            print(f"Limit: {limit} files")
        if dry_run:
            print("DRY RUN (no upload)")
        print("=" * 70)
        print()
        
        batch = []
        file_count = 0
        last_progress = time.time()
        
        # Stream through files
        for root, dirs, files in os.walk(str(directory)):
            # Skip unwanted dirs
            dirs[:] = [d for d in dirs if not any(s in d for s in self.SKIP)]
            
            for fname in files:
                if shutdown_requested:
                    print("\nShutdown requested, stopping...")
                    break
                
                fpath = Path(root) / fname
                
                if self.should_skip(fpath):
                    self.stats['skipped'] += 1
                    continue
                
                # Read file
                content = self.read_file(fpath)
                if not content:
                    self.stats['skipped'] += 1
                    continue
                
                file_count += 1
                self.stats['files'] += 1
                
                # Get metadata
                rel_path = str(fpath.relative_to(directory))
                
                # Check if already indexed
                if not self.force_reindex and rel_path in self.existing_sources:
                    print(f"[{file_count}] {rel_path[:55]}")
                    print(f"Already indexed, skipping...")
                    self.stats['duplicates'] += 1
                    continue
                
                category = self.get_category(fpath, directory)
                
                # Chunk with file extension and filename context
                chunks = self.chunk_text(content, fpath.suffix, fpath.name)
                
                # Progress
                elapsed = time.time() - self.start_time
                rate = self.stats['files'] / elapsed if elapsed > 0 else 0
                
                print(f"[{file_count}] {rel_path[:55]}")
                print(f"{category} | 📄 {len(content)/1024:.1f}KB | 🧩 {len(chunks)} chunks | ⏱️  {rate:.1f} files/s")
                
                if dry_run:
                    self.stats['chunks'] += len(chunks)
                    if limit and file_count >= limit:
                        break
                    continue
                
                # Create batch items
                for i, chunk_text in enumerate(chunks):
                    # Generate unique ID
                    chunk_id = f"{category}-{fpath.stem}-{i}"
                    chunk_id = chunk_id.lower().replace(' ', '-').replace('_', '-')[:200]
                    
                    # Add hash for uniqueness
                    hash_suffix = hashlib.md5(chunk_text.encode()).hexdigest()[:8]
                    chunk_id = f"{chunk_id}-{hash_suffix}"
                    
                    batch.append({
                        'id': chunk_id,
                        'doc': chunk_text,
                        'meta': {
                            'source': rel_path,
                            'category': category,
                            'file': fpath.name,
                            'chunk': i,
                            'total': len(chunks),
                            'version': 'v1.0.0',
                            'is_active': True,
                            'date': datetime.now().isoformat()
                        }
                    })
                
                # Process batch when full
                if len(batch) >= self.batch_size:
                    print(f"Uploading batch ({len(batch)} chunks)...")
                    self.process_batch(batch)
                    batch = []
                
                # Check limit
                if limit and file_count >= limit:
                    print(f"\nReached limit of {limit} files")
                    break
            
            if shutdown_requested or (limit and file_count >= limit):
                break
        
        # Process remaining
        if batch and not dry_run:
            print(f"\n⬆Uploading final batch ({len(batch)} chunks)...")
            self.process_batch(batch)
        
        # Summary
        elapsed = time.time() - self.start_time
        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Files processed: {self.stats['files']}")
        print(f"Chunks created: {self.stats['chunks']}")
        print(f"Files skipped: {self.stats['skipped']}")
        print(f"Duplicates skipped: {self.stats['duplicates']}")
        print(f"Errors: {self.stats['errors']}")
        print(f"Time: {elapsed:.1f}s")
        print(f"Rate: {self.stats['files']/elapsed:.1f} files/s" if elapsed > 0 else "")
        
        if not dry_run and not self.use_api:
            print(f"\n📚 Total in DB: {self.collection.count()} documents")
        
        if dry_run:
            print("\nDRY RUN - run without --dry-run to import")
        elif self.stats['duplicates'] > 0:
            print(f"\nTip: Use --force to re-index existing files")
        else:
            print("\nDone!")
        print("=" * 70)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    
    parser = argparse.ArgumentParser(
        description="Optimized RAG document ingestion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Direct mode (fastest)
  python scripts/quick_rag_docs.py docs-for-rag --limit 10
  python scripts/quick_rag_docs.py /path/to/my/docs
  
  # API mode (requires running server)
  python scripts/quick_rag_docs.py docs-for-rag --api --api-url http://localhost:8080 --api-key YOUR_KEY
  
  # Dry run (test without upload)
  python scripts/quick_rag_docs.py docs-for-rag --dry-run --limit 5
        """
    )
    
    # Required
    parser.add_argument(
        'directory',
        help="Path to documents directory to ingest"
    )
    
    # Mode selection
    parser.add_argument(
        '--api',
        action='store_true',
        help="Use REST API instead of direct ChromaDB access"
    )
    parser.add_argument(
        '--api-url',
        default='http://localhost:8080',
        help="API base URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        '--api-key',
        help="API key for authentication (required if --api)"
    )
    
    # Processing options
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=MAX_CHUNK_SIZE,
        help=f"Chunk size in characters (default: {MAX_CHUNK_SIZE})"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=BATCH_SIZE,
        help=f"Batch size for uploads (default: {BATCH_SIZE})"
    )
    parser.add_argument(
        '--limit',
        type=int,
        help="Limit number of files to process"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Scan files without uploading"
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help="Force re-index existing files (ignore duplicates)"
    )
    
    args = parser.parse_args()
    
    # Validate directory
    docs = Path(args.directory)
    if not docs.exists():
        print(f"✗ Directory not found: {docs}")
        sys.exit(1)
    
    if not docs.is_dir():
        print(f"✗ Not a directory: {docs}")
        sys.exit(1)
    
    # Validate API mode
    if args.api and not args.api_key:
        print("✗ --api-key required when using --api mode")
        sys.exit(1)
    
    try:
        # Create ingester
        ingester = OptimizedIngester(
            chunk_size=args.chunk_size,
            batch_size=args.batch_size,
            use_api=args.api,
            api_url=args.api_url,
            api_key=args.api_key,
            force_reindex=args.force
        )
        
        # Run
        ingester.ingest(docs, args.limit, args.dry_run)
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
