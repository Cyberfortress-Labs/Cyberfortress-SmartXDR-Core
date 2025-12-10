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
    python scripts/ingest_optimized.py /path/to/docs --limit 10
    python scripts/ingest_optimized.py docs-for-rag
    
    # API mode (requires running server)
    python scripts/ingest_optimized.py /path/to/docs --api --api-url http://localhost:8080 --api-key YOUR_KEY
    
    # Dry run
    python scripts/ingest_optimized.py /path/to/docs --dry-run
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

from app.config import CHROMA_DB_PATH
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions


# Global shutdown flag
shutdown_requested = False

def signal_handler(sig, frame):
    global shutdown_requested
    print("\n⚠️  Stopping after current batch...")
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
        chunk_size=1000, 
        batch_size=100,
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
        print("🌐 API Mode")
        print(f"URL: {self.api_url}")
        
        # Validate connection
        try:
            resp = requests.get(
                f"{self.api_url}/health",
                timeout=5
            )
            if resp.status_code != 200:
                raise Exception(f"Health check failed: {resp.status_code}")
            print("✓ Server connection OK\n")
        except Exception as e:
            raise Exception(f"Cannot connect to API: {e}")
    
    def _init_direct_mode(self):
        """Initialize direct ChromaDB access"""
        print("⚡ Direct ChromaDB Mode")
        
        # Init ChromaDB with optimized settings
        print("Initializing ChromaDB...")
        self.client = chromadb.PersistentClient(
            path=str(CHROMA_DB_PATH),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False
            )
        )
        
        # OpenAI embeddings
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        self.embed_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-3-small"
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base",
            embedding_function=self.embed_fn,  # type: ignore
            metadata={"hnsw:space": "cosine"}
        )
        
        current_count = self.collection.count()
        print(f"✓ Collection ready: {current_count} docs")
        
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
                
                print(f"✓ Found {len(self.existing_sources)} existing unique files")
            except Exception as e:
                print(f"⚠️  Could not load existing sources: {e}")
        
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
    
    def chunk_text(self, text: str, file_ext: str = '') -> List[str]:
        """
        Smart chunking based on file type
        - JSON: Parse and chunk by logical objects (keep IP + name together)
        - Others: Simple paragraph-based chunking
        """
        if len(text) <= self.chunk_size:
            return [text]
        
        # Special handling for JSON files
        if file_ext.lower() == '.json':
            return self._chunk_json(text)
        
        # Default paragraph-based chunking
        chunks = []
        pos = 0
        while pos < len(text):
            end = pos + self.chunk_size
            
            # Try to break at paragraph
            if end < len(text):
                para = text.rfind('\n\n', pos, end)
                if para > pos:
                    end = para
            
            chunk = text[pos:end].strip()
            if chunk:
                chunks.append(chunk)
            
            pos = end
        
        return chunks
    
    def _chunk_json(self, text: str) -> List[str]:
        """
        Smart JSON chunking - parse and chunk by logical units
        For topology.json: each device should be in one chunk
        """
        try:
            data = json.loads(text)
            chunks = []
            
            # Handle topology.json structure
            if 'segments' in data:
                for segment in data.get('segments', []):
                    zone = segment.get('zone', 'Unknown')
                    
                    for device in segment.get('devices', []):
                        # Create chunk for each device with full context
                        device_chunk = {
                            'zone': zone,
                            'subnet': segment.get('subnet', ''),
                            'device': device
                        }
                        chunk_text = json.dumps(device_chunk, indent=2, ensure_ascii=False)
                        
                        # Add readable summary at top
                        name = device.get('name', 'Unknown')
                        ip = device.get('ip', 'N/A')
                        role = device.get('role', 'N/A')
                        
                        summary = f"Device: {name}\nIP Address: {ip}\nRole: {role}\nZone: {zone}\n\n"
                        chunks.append(summary + chunk_text)
            
            # Handle ecosystem JSON structure
            elif 'name' in data and 'category' in data:
                # Single device description
                name = data.get('name', 'Unknown')
                ip = data.get('ip', 'N/A')
                role = data.get('role', 'N/A')
                zone = data.get('zone', 'Unknown')
                
                summary = f"Device: {name}\nIP Address: {ip}\nRole: {role}\nZone: {zone}\n\n"
                chunks.append(summary + json.dumps(data, indent=2, ensure_ascii=False))
            
            # Fallback: chunk by size
            else:
                text_formatted = json.dumps(data, indent=2, ensure_ascii=False)
                if len(text_formatted) <= self.chunk_size:
                    chunks.append(text_formatted)
                else:
                    # Fallback to simple chunking
                    return self._simple_chunk(text_formatted)
            
            return chunks if chunks else [text[:self.chunk_size]]
            
        except json.JSONDecodeError:
            # Not valid JSON, use simple chunking
            return self._simple_chunk(text)
    
    def _simple_chunk(self, text: str) -> List[str]:
        """Simple paragraph-based chunking"""
        chunks = []
        pos = 0
        while pos < len(text):
            end = pos + self.chunk_size
            
            if end < len(text):
                para = text.rfind('\n\n', pos, end)
                if para > pos:
                    end = para
            
            chunk = text[pos:end].strip()
            if chunk:
                chunks.append(chunk)
            
            pos = end
        
        return chunks
    
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
        print("📚 RAG Document Ingestion")
        print("=" * 70)
        print(f"Source: {directory.absolute()}")
        print(f"Mode: {'🌐 API' if self.use_api else '⚡ Direct ChromaDB'}")
        print(f"Chunk size: {self.chunk_size}")
        print(f"Batch size: {self.batch_size}")
        if limit:
            print(f"Limit: {limit} files")
        if dry_run:
            print("⚠️  DRY RUN (no upload)")
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
                    print("\n⚠️  Shutdown requested, stopping...")
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
                    print(f"  ⏭️  Already indexed, skipping...")
                    self.stats['duplicates'] += 1
                    continue
                
                category = self.get_category(fpath, directory)
                
                # Chunk with file extension context
                chunks = self.chunk_text(content, fpath.suffix)
                
                # Progress
                elapsed = time.time() - self.start_time
                rate = self.stats['files'] / elapsed if elapsed > 0 else 0
                
                print(f"[{file_count}] {rel_path[:55]}")
                print(f"  📁 {category} | 📄 {len(content)/1024:.1f}KB | 🧩 {len(chunks)} chunks | ⏱️  {rate:.1f} files/s")
                
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
                    print(f"  ⬆️  Uploading batch ({len(batch)} chunks)...")
                    self.process_batch(batch)
                    batch = []
                
                # Check limit
                if limit and file_count >= limit:
                    print(f"\n✓ Reached limit of {limit} files")
                    break
            
            if shutdown_requested or (limit and file_count >= limit):
                break
        
        # Process remaining
        if batch and not dry_run:
            print(f"\n⬆️  Uploading final batch ({len(batch)} chunks)...")
            self.process_batch(batch)
        
        # Summary
        elapsed = time.time() - self.start_time
        print("\n" + "=" * 70)
        print("📊 Summary")
        print("=" * 70)
        print(f"✓ Files processed: {self.stats['files']}")
        print(f"✓ Chunks created: {self.stats['chunks']}")
        print(f"⏭️  Files skipped: {self.stats['skipped']}")
        print(f"🔄 Duplicates skipped: {self.stats['duplicates']}")
        print(f"✗ Errors: {self.stats['errors']}")
        print(f"⏱️  Time: {elapsed:.1f}s")
        print(f"📈 Rate: {self.stats['files']/elapsed:.1f} files/s" if elapsed > 0 else "")
        
        if not dry_run and not self.use_api:
            print(f"\n📚 Total in DB: {self.collection.count()} documents")
        
        if dry_run:
            print("\n⚠️  DRY RUN - run without --dry-run to import")
        elif self.stats['duplicates'] > 0:
            print(f"\n💡 Tip: Use --force to re-index existing files")
        else:
            print("\n✅ Done!")
        print("=" * 70)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    
    parser = argparse.ArgumentParser(
        description="Optimized RAG document ingestion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Direct mode (fastest)
  python scripts/ingest_optimized.py docs-for-rag --limit 10
  python scripts/ingest_optimized.py /path/to/my/docs
  
  # API mode (requires running server)
  python scripts/ingest_optimized.py docs-for-rag --api --api-url http://localhost:8080 --api-key YOUR_KEY
  
  # Dry run (test without upload)
  python scripts/ingest_optimized.py docs-for-rag --dry-run --limit 5
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
        default=1000,
        help="Chunk size in characters (default: 1000)"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help="Batch size for uploads (default: 100)"
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
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
