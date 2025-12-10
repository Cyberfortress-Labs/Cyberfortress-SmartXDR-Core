"""
RAG Service - Business Logic Layer

Orchestrates RAG operations, manages embeddings, and integrates with LLM.
Uses dependency injection for testability and flexibility.
"""
import logging
import time
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from app.rag.repository import RAGRepository
from app.rag.models import Document, DocumentMetadata, QueryResult
from app.config import DEBUG_MODE


logger = logging.getLogger('smartxdr.rag.service')


class RAGService:
    """
    Service layer for RAG operations.
    Provides high-level API for document management and querying.
    """
    
    _instance = None
    
    def __new__(cls, repository: Optional[RAGRepository] = None):
        """Singleton pattern with optional dependency injection"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, repository: Optional[RAGRepository] = None):
        """
        Initialize RAG Service
        
        Args:
            repository: Optional RAGRepository instance (for dependency injection)
        """
        if self._initialized:
            return
        
        # Use injected repository or create default
        if repository is not None:
            self.repository = repository
        else:
            # Default configuration
            from app.config import CHROMA_DB_PATH
            self.repository = RAGRepository(
                persist_directory=CHROMA_DB_PATH,
                collection_name="knowledge_base"
            )
        
        # Stats tracking
        self.stats = {
            "total_queries": 0,
            "total_documents_added": 0,
            "total_documents_updated": 0,
            "total_documents_deleted": 0,
            "avg_query_time_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        self._initialized = True
        logger.info("RAGService initialized")
    
    # ==================== Document Management ====================
    
    def add_document(
        self,
        content: str,
        source: str,
        source_id: str,
        version: str,
        tags: Optional[List[str]] = None,
        is_active: bool = True,
        custom_metadata: Optional[Dict[str, Any]] = None,
        auto_deactivate_old: bool = True
    ) -> Dict[str, Any]:
        """
        Add a new document to the knowledge base
        
        Args:
            content: Document content
            source: Source identifier (file path, URL, module name)
            source_id: Unique logical ID
            version: Version identifier
            tags: Classification tags
            is_active: Active status
            custom_metadata: Additional metadata
            auto_deactivate_old: Automatically deactivate old versions
        
        Returns:
            Dict with status and document_id
        """
        try:
            # Create metadata
            metadata = DocumentMetadata(
                source=source,
                source_id=source_id,
                version=version,
                is_active=is_active,
                tags=tags or [],
                custom_metadata=custom_metadata or {}
            )
            
            # Add document
            doc_id = self.repository.add_document(content, metadata)
            
            # Optionally deactivate old versions
            if auto_deactivate_old and is_active:
                self.repository.deactivate_old_versions(source_id, version)
            
            self.stats["total_documents_added"] += 1
            
            logger.info(f"Document added: id={doc_id}, source_id={source_id}, version={version}")
            
            return {
                "status": "success",
                "document_id": doc_id,
                "message": f"Document added successfully"
            }
            
        except Exception as e:
            logger.error(f"Error adding document: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
    
    def add_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        auto_deactivate_old: bool = True
    ) -> Dict[str, Any]:
        """
        Add multiple documents in batch
        
        Args:
            documents: List of dicts with keys: content, source, source_id, version, tags, etc.
            auto_deactivate_old: Automatically deactivate old versions
        
        Returns:
            Dict with status and document_ids
        """
        try:
            contents = []
            metadatas = []
            
            for doc in documents:
                contents.append(doc['content'])
                
                metadata = DocumentMetadata(
                    source=doc['source'],
                    source_id=doc['source_id'],
                    version=doc['version'],
                    is_active=doc.get('is_active', True),
                    tags=doc.get('tags', []),
                    custom_metadata=doc.get('custom_metadata', {})
                )
                metadatas.append(metadata)
            
            # Add documents
            doc_ids = self.repository.add_documents_batch(contents, metadatas)
            
            # Optionally deactivate old versions
            if auto_deactivate_old:
                unique_source_ids = set(doc['source_id'] for doc in documents)
                for source_id in unique_source_ids:
                    # Get latest version for this source_id
                    latest_version = max(
                        (doc['version'] for doc in documents if doc['source_id'] == source_id),
                        default=None
                    )
                    if latest_version:
                        self.repository.deactivate_old_versions(source_id, latest_version)
            
            self.stats["total_documents_added"] += len(doc_ids)
            
            logger.info(f"Batch added {len(doc_ids)} documents")
            
            return {
                "status": "success",
                "document_ids": doc_ids,
                "count": len(doc_ids),
                "message": f"Successfully added {len(doc_ids)} documents"
            }
            
        except Exception as e:
            logger.error(f"Error adding documents batch: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
    
    def update_document(
        self,
        document_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update an existing document
        
        Args:
            document_id: Document ID to update
            content: New content (optional)
            metadata: New metadata fields (optional)
        
        Returns:
            Dict with status
        """
        try:
            # Get existing document
            existing = self.repository.get_document(document_id)
            if not existing:
                return {
                    "status": "error",
                    "error": f"Document {document_id} not found"
                }
            
            # Update metadata if provided
            updated_metadata = None
            if metadata:
                updated_metadata = existing.metadata
                
                # Update fields
                if 'source' in metadata:
                    updated_metadata.source = metadata['source']
                if 'source_id' in metadata:
                    updated_metadata.source_id = metadata['source_id']
                if 'version' in metadata:
                    updated_metadata.version = metadata['version']
                if 'is_active' in metadata:
                    updated_metadata.is_active = metadata['is_active']
                if 'tags' in metadata:
                    updated_metadata.tags = metadata['tags']
                if 'custom_metadata' in metadata:
                    updated_metadata.custom_metadata.update(metadata['custom_metadata'])
            
            # Update document
            success = self.repository.update_document(document_id, content, updated_metadata)
            
            if success:
                self.stats["total_documents_updated"] += 1
                logger.info(f"Document updated: id={document_id}")
                return {
                    "status": "success",
                    "message": "Document updated successfully"
                }
            else:
                return {
                    "status": "error",
                    "error": "Failed to update document"
                }
            
        except Exception as e:
            logger.error(f"Error updating document: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
    
    def delete_document(self, document_id: str, soft: bool = True) -> Dict[str, Any]:
        """
        Delete a document (soft or hard delete)
        
        Args:
            document_id: Document ID to delete
            soft: If True, mark as inactive; if False, permanently delete
        
        Returns:
            Dict with status
        """
        try:
            if soft:
                success = self.repository.soft_delete_document(document_id)
                action = "deactivated"
            else:
                success = self.repository.delete_document(document_id)
                action = "deleted"
            
            if success:
                self.stats["total_documents_deleted"] += 1
                logger.info(f"Document {action}: id={document_id}")
                return {
                    "status": "success",
                    "message": f"Document {action} successfully"
                }
            else:
                return {
                    "status": "error",
                    "error": f"Failed to {action} document"
                }
            
        except Exception as e:
            logger.error(f"Error deleting document: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single document by ID
        
        Args:
            document_id: Document ID
        
        Returns:
            Dict with document data or None
        """
        try:
            doc = self.repository.get_document(document_id)
            if doc:
                return {
                    "id": doc.id,
                    "content": doc.content,
                    "metadata": doc.metadata.to_dict()
                }
            return None
            
        except Exception as e:
            logger.error(f"Error getting document: {e}", exc_info=True)
            return None
    
    def list_documents(
        self,
        source_id: Optional[str] = None,
        source: Optional[str] = None,
        version: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        List documents with filtering and pagination
        
        Args:
            source_id: Filter by source_id
            source: Filter by source
            version: Filter by version
            tags: Filter by tags (AND logic)
            is_active: Filter by active status
            page: Page number (1-indexed)
            page_size: Items per page
        
        Returns:
            Dict with documents, total count, and pagination info
        """
        try:
            # Build filter
            where = {}
            if source_id:
                where['source_id'] = source_id
            if source:
                where['source'] = source
            if version:
                where['version'] = version
            if is_active is not None:
                where['is_active'] = is_active
            if tags:
                # ChromaDB doesn't support array contains, so we filter in Python
                pass
            
            # Get all matching documents (will filter tags in Python)
            all_docs = self.repository.list_documents(where=where if where else None)
            
            # Filter by tags if needed
            if tags:
                all_docs = [
                    doc for doc in all_docs
                    if all(tag in doc.metadata.tags for tag in tags)
                ]
            
            # Pagination
            total = len(all_docs)
            total_pages = (total + page_size - 1) // page_size
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            
            page_docs = all_docs[start_idx:end_idx]
            
            # Convert to dicts
            documents = [
                {
                    "id": doc.id,
                    "content": doc.content,
                    "metadata": doc.metadata.to_dict()
                }
                for doc in page_docs
            ]
            
            return {
                "status": "success",
                "documents": documents,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
            
        except Exception as e:
            logger.error(f"Error listing documents: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "documents": [],
                "total": 0
            }
    
    # ==================== Query Operations ====================
    
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        distance_threshold: float = 1.4
    ) -> Dict[str, Any]:
        """
        Query the knowledge base
        
        Args:
            query_text: Query text
            top_k: Number of results to return
            filters: Metadata filters (e.g., {"is_active": True})
            distance_threshold: Maximum distance for relevance
        
        Returns:
            Dict with query results
        """
        try:
            start_time = time.time()
            
            # Build where clause
            where = filters.copy() if filters else {}
            
            # Default to active documents only
            if 'is_active' not in where:
                where['is_active'] = True
            
            # Query repository
            results = self.repository.query(
                query_text=query_text,
                n_results=top_k,
                where=where if where else None
            )
            
            # Filter by distance threshold
            filtered_docs = []
            filtered_metadata = []
            filtered_distances = []
            filtered_ids = []
            
            for doc, meta, dist, doc_id in zip(
                results.documents, 
                results.metadatas, 
                results.distances, 
                results.ids
            ):
                if dist < distance_threshold:
                    filtered_docs.append(doc)
                    filtered_metadata.append(meta)
                    filtered_distances.append(dist)
                    filtered_ids.append(doc_id)
            
            # Calculate query time
            query_time_ms = (time.time() - start_time) * 1000
            
            # Update stats
            self.stats["total_queries"] += 1
            total_queries = self.stats["total_queries"]
            avg_time = self.stats["avg_query_time_ms"]
            self.stats["avg_query_time_ms"] = (avg_time * (total_queries - 1) + query_time_ms) / total_queries
            
            logger.info(f"Query executed: query='{query_text[:50]}...', results={len(filtered_docs)}, time={query_time_ms:.2f}ms")
            
            return {
                "status": "success",
                "documents": filtered_docs,
                "metadatas": [m.to_dict() for m in filtered_metadata],
                "distances": filtered_distances,
                "ids": filtered_ids,
                "sources": list(set(m.source for m in filtered_metadata)),
                "query_time_ms": query_time_ms,
                "total_results": len(filtered_docs)
            }
            
        except Exception as e:
            logger.error(f"Error querying knowledge base: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "documents": [],
                "metadatas": [],
                "distances": [],
                "ids": [],
                "sources": []
            }
    
    def build_context_from_query(
        self,
        query_text: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, List[str]]:
        """
        Build context string from query results
        
        Args:
            query_text: Query text
            top_k: Number of documents to retrieve
            filters: Metadata filters
        
        Returns:
            Tuple of (context_text, sources)
        """
        results = self.query(query_text, top_k, filters)
        
        if results["status"] == "error" or not results["documents"]:
            return "No relevant context found.", []
        
        # Build context
        context_parts = []
        for idx, doc in enumerate(results["documents"]):
            context_parts.append(f"[Document {idx + 1}]\n{doc}")
        
        context_text = "\n\n---\n\n".join(context_parts)
        sources = results["sources"]
        
        return context_text, sources
    
    # ==================== Statistics & Management ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        repo_stats = self.repository.get_stats()
        
        return {
            "repository": repo_stats,
            "service": self.stats
        }
    
    def invalidate_cache_by_source(self, source_id: str):
        """
        Invalidate cache for a specific source
        (Placeholder for future cache invalidation)
        """
        logger.info(f"Cache invalidation requested for source_id: {source_id}")
        # TODO: Implement cache invalidation logic
        pass
    
    def reset(self):
        """Reset the knowledge base (for testing)"""
        self.repository.reset_collection()
        self.stats = {
            "total_queries": 0,
            "total_documents_added": 0,
            "total_documents_updated": 0,
            "total_documents_deleted": 0,
            "avg_query_time_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        logger.warning("RAGService has been reset")
