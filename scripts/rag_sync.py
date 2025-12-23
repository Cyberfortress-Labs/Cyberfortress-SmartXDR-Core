#!/usr/bin/env python3
"""
RAG Sync - Auto-sync documents from data/ directory to ChromaDB

Implements Detect → Action → Clean flow:
1. DETECT: Scan data/ directory and compare with indexed documents
2. ACTION: Handle new files, updated files, deleted files
3. CLEAN: Remove orphaned entries from ChromaDB

Features:
- File hash tracking for accurate change detection
- Subdirectory categories (each subdirectory = topic/domain)
- Safe update order: process new chunks before deleting old
- Backward compatibility: re-index if file_hash missing

Usage:
    # Sync data/ directory (default)
    python scripts/rag_sync.py
    
    # Sync specific directory
    python scripts/rag_sync.py /path/to/docs
    
    # Dry run (show what would happen)
    python scripts/rag_sync.py --dry-run
    
    # Force re-index all files
    python scripts/rag_sync.py --force
"""
import argparse
import sys
import os
import hashlib
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass
import fnmatch
# Force unbuffered output for real-time display in Docker
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import CHROMA_DB_PATH, BATCH_SIZE as CONFIG_BATCH_SIZE, MAX_CHUNK_SIZE
from app.utils.logger import setup_logger
from app.core.chunking import (
    json_to_natural_text, 
    mitre_to_natural_text,
    markdown_to_chunks,
    text_to_chunks,
    dataflow_to_natural_text,
    pdf_to_chunks
)
import json

# Setup logger
logger = setup_logger("rag_sync")


@dataclass
class FileInfo:
    """Information about a file for sync comparison"""
    path: str  # Relative path from data dir
    file_hash: str
    mtime: float
    size: int


@dataclass
class SyncResult:
    """Results from sync operation"""
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    errors: int = 0
    

SUPPORTED_EXT = {'.md', '.txt', '.rst', '.json', '.yaml', '.yml', '.py', '.js', '.ts', '.go', '.java', '.pdf'}
SKIP_DIRS = {'__pycache__', '.git', '.venv', 'node_modules', '.pytest_cache', 'chroma_db'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
# Use config batch size, with lower fallback for embedding API limits
BATCH_SIZE = min(CONFIG_BATCH_SIZE, 50) if CONFIG_BATCH_SIZE else 50

# Skip files from .env (comma-separated patterns like README.md,*.log)
_skip_files_str = os.environ.get('RAG_SYNC_SKIP_FILES', 'README.md')
SKIP_FILES = set(f.strip() for f in _skip_files_str.split(',') if f.strip())


# def log(msg: str):
#     """Log message using app logger"""
#     logger.info(msg)


class RAGSync:
    """Auto-sync documents from data/ directory to ChromaDB"""
    
    def __init__(self, data_dir: Path, force: bool = False, dry_run: bool = False):
        self.data_dir = data_dir
        self.force = force
        self.dry_run = dry_run
        self.result = SyncResult()
        self.start_time = time.time()
        
        # Initialize ChromaDB repository
        if not dry_run:
            self._init_repository()
    
    def _init_repository(self):
        """Initialize ChromaDB via RAGRepository"""
        from app.rag.repository import RAGRepository
        
        logger.info("Connecting to ChromaDB...")
        self.repo = RAGRepository(
            persist_directory=str(CHROMA_DB_PATH),
            collection_name="knowledge_base"
        )
        self.collection = self.repo.collection
        logger.info(f"Connected. Current docs: {self.collection.count()}")
    
    def compute_file_hash(self, path: Path) -> str:
        """Compute SHA256 hash of file content"""
        try:
            if path.suffix.lower() == '.pdf':
                with open(path, 'rb') as f:
                    return hashlib.sha256(f.read()).hexdigest()
            else:
                content = path.read_text(encoding='utf-8')
                return hashlib.sha256(content.encode('utf-8')).hexdigest()
        except:
            return hashlib.sha256(str(path).encode()).hexdigest()
    
    def should_skip(self, path: Path) -> bool:
        """Check if file should be skipped"""
        # 1. Check directories (giữ nguyên)
        if any(s in str(path) for s in SKIP_DIRS):
            return True
            
        # 2. Check extensions (giữ nguyên)
        if path.suffix.lower() not in SUPPORTED_EXT:
            return True

        # 3. Check patterns from ENV (SỬA LẠI ĐOẠN NÀY)
        # Lấy đường dẫn tương đối để so sánh (ví dụ: wazuh/config.txt)
        try:
            rel_path = str(path.relative_to(self.data_dir))
        except ValueError:
            rel_path = path.name # Fallback

        for pattern in SKIP_FILES:
            # Case A: So sánh tên file (ví dụ pattern="*.log" khớp "error.log")
            if fnmatch.fnmatch(path.name, pattern):
                return True
            # Case B: So sánh đường dẫn (ví dụ pattern="secret/*" khớp "secret/pass.txt")
            if fnmatch.fnmatch(rel_path, pattern):
                return True

        # 4. Check file size (giữ nguyên)
        try:
            size = path.stat().st_size
            if size == 0 or size > MAX_FILE_SIZE:
                return True
        except:
            return True
            
        return False
    
    def scan_directory(self) -> Dict[str, FileInfo]:
        """Scan data directory and build file index"""
        logger.info(f"\n[DETECT] Scanning {self.data_dir}...")
        files = {}
        
        for root, dirs, filenames in os.walk(str(self.data_dir)):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            
            for fname in filenames:
                fpath = Path(root) / fname
                
                if self.should_skip(fpath):
                    continue
                
                rel_path = str(fpath.relative_to(self.data_dir))
                
                files[rel_path] = FileInfo(
                    path=rel_path,
                    file_hash=self.compute_file_hash(fpath),
                    mtime=fpath.stat().st_mtime,
                    size=fpath.stat().st_size
                )
        
        logger.info(f"Found {len(files)} files in data directory")
        return files
    
    def get_indexed_files(self) -> Dict[str, Dict]:
        """Get currently indexed files from ChromaDB"""
        if self.dry_run:
            return {}
        
        logger.info("[DETECT] Loading indexed documents...")
        indexed = {}
        
        try:
            results = self.collection.get(include=['metadatas'])
            
            if results and results['metadatas']:
                for i, meta in enumerate(results['metadatas']):
                    if not meta:
                        continue
                    
                    source = meta.get('source', '')
                    if not source:
                        continue
                    
                    # Group by source file
                    if source not in indexed:
                        indexed[source] = {
                            'file_hash': meta.get('file_hash'),
                            'mtime': meta.get('mtime'),
                            'doc_ids': [],
                            'meta': meta
                        }
                    indexed[source]['doc_ids'].append(results['ids'][i])
            
            logger.info(f"Found {len(indexed)} indexed files")
        except Exception as e:
            logger.error(f"Error loading indexed documents: {e}")
        
        return indexed
    
    def diff_files(
        self, 
        current_files: Dict[str, FileInfo], 
        indexed_files: Dict[str, Dict]
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Compare current files with indexed files.
        
        Returns:
            Tuple of (new_files, updated_files, deleted_files)
        """
        current_paths = set(current_files.keys())
        indexed_paths = set(indexed_files.keys())
        
        # New files: in current but not indexed
        new_files = list(current_paths - indexed_paths)
        
        # Deleted files: in indexed but not current
        deleted_files = list(indexed_paths - current_paths)
        
        # Updated files: in both but content changed
        updated_files = []
        for path in current_paths & indexed_paths:
            current = current_files[path]
            indexed = indexed_files.get(path, {})
            indexed_hash = indexed.get('file_hash')
            
            # If no file_hash in indexed (backward compatibility), treat as updated
            if indexed_hash is None:
                updated_files.append(path)
                continue
            
            # If hash differs, file was updated
            if current.file_hash != indexed_hash:
                updated_files.append(path)
        
        logger.info(f"\n[DETECT] Diff results:")
        logger.info(f"  New files:     {len(new_files)}")
        logger.info(f"  Updated files: {len(updated_files)}")
        logger.info(f"  Deleted files: {len(deleted_files)}")
        logger.info(f"  Unchanged:     {len(current_paths) - len(new_files) - len(updated_files)}")
        
        return new_files, updated_files, deleted_files
    
    def get_category(self, rel_path: str) -> str:
        """Extract category from relative path (first subdirectory)"""
        parts = Path(rel_path).parts
        if len(parts) > 1:
            return parts[0].lower()
        return 'general'
    
    def read_file(self, path: Path) -> Optional[str]:
        """Read file content (for text files)"""
        if path.suffix.lower() == '.pdf':
            return "[PDF]"
        try:
            return path.read_text(encoding='utf-8')
        except:
            try:
                return path.read_text(encoding='latin-1')
            except:
                return None
    
    def chunk_file(self, path: Path, content: str) -> List[str]:
        """Chunk file content based on file type"""
        ext_lower = path.suffix.lower()
        filename = path.name
        
        # PDF files - use binary processing
        if ext_lower == '.pdf':
            return pdf_to_chunks(str(path), filename)
        
        if not content or not content.strip():
            return []
        
        # JSON files
        if ext_lower == '.json':
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    if 'phases' in data:
                        return dataflow_to_natural_text(data, filename)
                    if 'mitre_id' in data:
                        return [mitre_to_natural_text(data)]
                    if 'id' in data and 'name' in data:
                        return json_to_natural_text(data, filename)
                return text_to_chunks(json.dumps(data, indent=2), filename)
            except:
                return text_to_chunks(content, filename)
        
        # Markdown files
        if ext_lower in {'.md', '.markdown', '.rst'}:
            return markdown_to_chunks(content, filename)
        
        # Other text files
        return text_to_chunks(content, filename)
    
    def process_file(self, rel_path: str) -> List[Dict]:
        """Process a file and return chunk documents"""
        fpath = self.data_dir / rel_path
        
        if not fpath.exists():
            return []
        
        content = self.read_file(fpath)
        if content is None:
            return []
        
        file_hash = self.compute_file_hash(fpath)
        category = self.get_category(rel_path)
        mtime = fpath.stat().st_mtime
        
        chunks = self.chunk_file(fpath, content)
        
        if not chunks:
            return []
        
        documents = []
        for i, chunk_text in enumerate(chunks):
            # Generate unique ID
            chunk_id = f"{category}-{fpath.stem}-{i}"
            chunk_id = chunk_id.lower().replace(' ', '-').replace('_', '-')[:200]
            hash_suffix = hashlib.md5(chunk_text.encode()).hexdigest()[:8]
            chunk_id = f"{chunk_id}-{hash_suffix}"
            
            documents.append({
                'id': chunk_id,
                'document': chunk_text,
                'metadata': {
                    'source': rel_path,
                    'category': category,
                    'file': fpath.name,
                    'chunk': i,
                    'total': len(chunks),
                    'version': 'v1.0.0',
                    'is_active': True,
                    'date': datetime.now().isoformat(),
                    'file_hash': file_hash,
                    'mtime': mtime
                }
            })
        
        return documents
    
    def add_files(self, files: List[str]):
        """Add new files to ChromaDB"""
        if not files:
            return
        
        logger.info(f"\n[ACTION] Adding {len(files)} new files...")
        
        for path in files:
            try:
                documents = self.process_file(path)
                
                if not documents:
                    logger.info(f"  ! No content: {path[:50]}")
                    self.result.skipped += 1
                    continue
                
                if not self.dry_run:
                    # Batch upsert to avoid token limits
                    for i in range(0, len(documents), BATCH_SIZE):
                        batch = documents[i:i + BATCH_SIZE]
                        self.collection.upsert(
                            ids=[d['id'] for d in batch],
                            documents=[d['document'] for d in batch],
                            metadatas=[d['metadata'] for d in batch]
                        )
                
                logger.info(f"  + Added: {path[:50]} ({len(documents)} chunks)")
                self.result.added += 1
                
            except Exception as e:
                logger.error(f"  x Error: {path[:50]} - {e}")
                self.result.errors += 1
    
    def update_files(self, files: List[str], indexed_files: Dict[str, Dict]):
        """
        Update modified files in ChromaDB.
        
        Safe order: Process new chunks FIRST, then delete old, then add new.
        This prevents data loss if file processing fails.
        """
        if not files:
            return
        
        logger.info(f"\n[ACTION] Updating {len(files)} modified files...")
        
        for path in files:
            try:
                # Step 1: Process new chunks FIRST (before any deletion)
                new_documents = self.process_file(path)
                
                if not new_documents:
                    logger.info(f"  No content after update: {path[:50]}")
                    self.result.skipped += 1
                    continue
                
                # Step 2: Delete old chunks
                if not self.dry_run:
                    old_doc_ids = indexed_files.get(path, {}).get('doc_ids', [])
                    if old_doc_ids:
                        self.collection.delete(ids=old_doc_ids)
                
                # Step 3: Add new chunks in batches
                if not self.dry_run:
                    for i in range(0, len(new_documents), BATCH_SIZE):
                        batch = new_documents[i:i + BATCH_SIZE]
                        self.collection.upsert(
                            ids=[d['id'] for d in batch],
                            documents=[d['document'] for d in batch],
                            metadatas=[d['metadata'] for d in batch]
                        )
                
                logger.info(f"  ✓ Updated: {path[:50]} ({len(new_documents)} chunks)")
                self.result.updated += 1
                
            except Exception as e:
                logger.error(f"  ✗ Error: {path[:50]} - {e}")
                self.result.errors += 1
    
    def delete_files(self, files: List[str], indexed_files: Dict[str, Dict]):
        """Delete removed files from ChromaDB"""
        if not files:
            return
        
        logger.info(f"\n[ACTION] Deleting {len(files)} removed files...")
        
        for path in files:
            try:
                doc_ids = indexed_files.get(path, {}).get('doc_ids', [])
                
                if not doc_ids:
                    logger.info(f"  No docs found: {path[:50]}")
                    continue
                
                if not self.dry_run:
                    self.collection.delete(ids=doc_ids)
                
                logger.info(f"  ✓ Deleted: {path[:50]} ({len(doc_ids)} chunks)")
                self.result.deleted += 1
                
            except Exception as e:
                logger.error(f"  ✗ Error: {path[:50]} - {e}")
                self.result.errors += 1
    
    def sync(self):
        """Run full sync: Detect → Action → Clean"""
        logger.info("=" * 70)
        logger.info("RAG Sync - Auto-sync documents to ChromaDB")
        logger.info("=" * 70)
        logger.info(f"Data directory: {self.data_dir}")
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        logger.info(f"Force re-index: {self.force}")
        logger.info("=" * 70)
        
        # DETECT: Scan and compare
        current_files = self.scan_directory()
        indexed_files = self.get_indexed_files()
        
        if self.force:
            # Force mode: treat all current files as new
            new_files = list(current_files.keys())
            updated_files = []
            deleted_files = list(indexed_files.keys())
            logger.info(f"\n[FORCE MODE] Re-indexing all {len(new_files)} files")
        else:
            new_files, updated_files, deleted_files = self.diff_files(
                current_files, indexed_files
            )
        
        # Check if anything to do
        total_changes = len(new_files) + len(updated_files) + len(deleted_files)
        if total_changes == 0:
            logger.info("\n✓ Everything is in sync! No changes needed.")
            return self.result
        
        # ACTION: Process changes
        self.add_files(new_files)
        self.update_files(updated_files, indexed_files)
        self.delete_files(deleted_files, indexed_files)
        
        # CLEAN: Remove orphaned entries (already handled by delete_files)
        
        # Summary
        elapsed = time.time() - self.start_time
        logger.info("\n" + "=" * 70)
        logger.info("[SUMMARY]")
        logger.info("=" * 70)
        logger.info(f"  Added:   {self.result.added} files")
        logger.info(f"  Updated: {self.result.updated} files")
        logger.info(f"  Deleted: {self.result.deleted} files")
        logger.info(f"  Skipped: {self.result.skipped} files")
        logger.info(f"  Errors:  {self.result.errors}")
        logger.info(f"  Time:    {elapsed:.1f}s")
        
        if not self.dry_run:
            logger.info(f"\nTotal in DB: {self.collection.count()} documents")
        
        if self.dry_run:
            logger.info("\nDRY RUN - No changes were made")
        else:
            logger.info("\n✓ Sync complete!")
        
        logger.info("=" * 70)
        
        return self.result


def main():
    parser = argparse.ArgumentParser(
        description="Auto-sync documents from data/ directory to ChromaDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync data/ directory (default)
  python scripts/rag_sync.py
  
  # Sync specific directory
  python scripts/rag_sync.py /path/to/docs
  
  # Dry run (show what would happen)
  python scripts/rag_sync.py --dry-run
  
  # Force re-index all files
  python scripts/rag_sync.py --force
        """
    )
    
    parser.add_argument(
        'directory',
        nargs='?',
        default='data',
        help="Directory to sync (default: data)"
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Show what would happen without making changes"
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help="Force re-index all files (ignore existing hashes)"
    )
    
    args = parser.parse_args()
    
    # Validate directory
    data_dir = Path(args.directory)
    if not data_dir.exists():
        logger.error(f"Error: Directory not found: {data_dir}")
        sys.exit(1)
    
    if not data_dir.is_dir():
        logger.error(f"Error: Not a directory: {data_dir}")
        sys.exit(1)
    
    try:
        syncer = RAGSync(
            data_dir=data_dir,
            force=args.force,
            dry_run=args.dry_run
        )
        result = syncer.sync()
        
        # Exit with error code if there were errors
        if result.errors > 0:
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
