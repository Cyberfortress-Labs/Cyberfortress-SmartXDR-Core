"""
RAG Repository - Data Access Layer for ChromaDB

Handles all direct interactions with ChromaDB vector database.
Supports dependency injection for easy testing and future database swapping.
"""
import logging
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import chromadb
from chromadb.config import Settings

from app.rag.models import Document, DocumentMetadata, QueryResult
from app.config import DEBUG_MODE
from app.core.embeddings import OpenAIEmbeddingFunction


logger = logging.getLogger('smartxdr.rag.repository')


class RAGRepository:
    """
    Repository pattern for RAG database operations.
    Abstracts ChromaDB implementation for easy swapping to other vector DBs.
    """
    
    def __init__(
        self, 
        persist_directory: str,
        collection_name: str = "knowledge_base",
        embedding_function: Optional[Any] = None
    ):
        """
        Initialize RAG Repository
        
        Args:
            persist_directory: Path to ChromaDB persistent storage (local mode only)
            collection_name: Name of the collection
            embedding_function: Optional custom embedding function
        """
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name
        
        # Check if we should use HTTP client (Docker mode) or persistent client (local mode)
        from app.config import CHROMA_HOST, CHROMA_PORT
        
        if CHROMA_HOST:
            # Docker mode: Connect to ChromaDB service via HTTP
            logger.info(f"Connecting to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")
            self.client = chromadb.HttpClient(
                host=CHROMA_HOST,
                port=CHROMA_PORT,
                settings=Settings(
                    anonymized_telemetry=False,
                )
            )
        else:
            # Local mode: Use persistent client
            logger.info(f"Using local ChromaDB at {self.persist_directory}")
            self.client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
        
        # Set up embedding function
        if embedding_function is None:
            # Use custom OpenAIEmbeddingFunction with timeout/retry config from app.config
            self.embedding_function = OpenAIEmbeddingFunction()
        else:
            self.embedding_function = embedding_function
        
        # Get or create collection
        self.collection = self._get_or_create_collection()
        
        logger.info(f"RAGRepository initialized: collection={collection_name}")
    
    def _get_or_create_collection(self):
        """Get or create ChromaDB collection"""
        try:
            collection = self.client.get_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function
            )
            logger.info(f"Loaded existing collection: {self.collection_name}")
        except Exception:
            collection = self.client.create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Created new collection: {self.collection_name}")
        
        return collection
    
    def add_document(
        self, 
        content: str, 
        metadata: DocumentMetadata,
        document_id: Optional[str] = None
    ) -> str:
        """
        Add a single document to the knowledge base
        
        Args:
            content: Document text content
            metadata: Document metadata
            document_id: Optional custom document ID (auto-generated if None)
        
        Returns:
            str: Document ID
        """
        # Generate ID if not provided
        if document_id is None:
            document_id = self._generate_document_id(content, metadata)
        
        # Ensure timestamps
        if not metadata.created_at:
            metadata.created_at = datetime.utcnow().isoformat()
        if not metadata.updated_at:
            metadata.updated_at = datetime.utcnow().isoformat()
        
        # Convert metadata to dict
        metadata_dict = metadata.to_dict()
        
        # Add to ChromaDB
        self.collection.add(
            ids=[document_id],
            documents=[content],
            metadatas=[metadata_dict]
        )
        
        logger.info(f"Added document: id={document_id}, source_id={metadata.source_id}, version={metadata.version}")
        
        return document_id
    
    def add_documents_batch(
        self, 
        contents: List[str], 
        metadatas: List[DocumentMetadata],
        document_ids: Optional[List[str]] = None
    ) -> List[str]:
        """
        Add multiple documents in batch
        
        Args:
            contents: List of document contents
            metadatas: List of document metadata
            document_ids: Optional list of custom IDs
        
        Returns:
            List[str]: List of document IDs
        """
        if len(contents) != len(metadatas):
            raise ValueError("Contents and metadatas must have the same length")
        
        # Generate IDs if not provided
        if document_ids is None:
            document_ids = [
                self._generate_document_id(content, metadata)
                for content, metadata in zip(contents, metadatas)
            ]
        
        # Ensure timestamps
        for metadata in metadatas:
            if not metadata.created_at:
                metadata.created_at = datetime.utcnow().isoformat()
            if not metadata.updated_at:
                metadata.updated_at = datetime.utcnow().isoformat()
        
        # Convert metadata to dicts
        metadata_dicts = [m.to_dict() for m in metadatas]
        
        # Add to ChromaDB
        self.collection.add(
            ids=document_ids,
            documents=contents,
            metadatas=metadata_dicts
        )
        
        logger.info(f"Added {len(document_ids)} documents in batch")
        
        return document_ids
    
    def get_document(self, document_id: str) -> Optional[Document]:
        """
        Get a single document by ID
        
        Args:
            document_id: Document ID
        
        Returns:
            Document or None if not found
        """
        try:
            result = self.collection.get(
                ids=[document_id],
                include=["documents", "metadatas"]
            )
            
            if not result['ids']:
                return None
            
            metadata = DocumentMetadata.from_dict(result['metadatas'][0])
            
            return Document(
                id=result['ids'][0],
                content=result['documents'][0],
                metadata=metadata
            )
        except Exception as e:
            logger.error(f"Error getting document {document_id}: {e}")
            return None
    
    def update_document(
        self, 
        document_id: str, 
        content: Optional[str] = None,
        metadata: Optional[DocumentMetadata] = None
    ) -> bool:
        """
        Update an existing document
        
        Args:
            document_id: Document ID to update
            content: New content (optional)
            metadata: New metadata (optional)
        
        Returns:
            bool: True if updated successfully
        """
        try:
            # Get existing document
            existing = self.get_document(document_id)
            if not existing:
                logger.warning(f"Document {document_id} not found for update")
                return False
            
            # Prepare update
            update_content = content if content is not None else existing.content
            
            if metadata is not None:
                # Update timestamp
                metadata.updated_at = datetime.utcnow().isoformat()
                # Preserve created_at
                if not metadata.created_at:
                    metadata.created_at = existing.metadata.created_at
                update_metadata = metadata.to_dict()
            else:
                # Keep existing metadata but update timestamp
                existing.metadata.updated_at = datetime.utcnow().isoformat()
                update_metadata = existing.metadata.to_dict()
            
            # Update in ChromaDB
            self.collection.update(
                ids=[document_id],
                documents=[update_content],
                metadatas=[update_metadata]
            )
            
            logger.info(f"Updated document: id={document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating document {document_id}: {e}")
            return False
    
    def delete_document(self, document_id: str) -> bool:
        """
        Delete a document by ID
        
        Args:
            document_id: Document ID to delete
        
        Returns:
            bool: True if deleted successfully
        """
        try:
            self.collection.delete(ids=[document_id])
            logger.info(f"Deleted document: id={document_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            return False
    
    def soft_delete_document(self, document_id: str) -> bool:
        """
        Soft delete by marking is_active=False
        
        Args:
            document_id: Document ID to soft delete
        
        Returns:
            bool: True if updated successfully
        """
        try:
            existing = self.get_document(document_id)
            if not existing:
                return False
            
            existing.metadata.is_active = False
            existing.metadata.updated_at = datetime.utcnow().isoformat()
            
            self.collection.update(
                ids=[document_id],
                metadatas=[existing.metadata.to_dict()]
            )
            
            logger.info(f"Soft deleted document: id={document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error soft deleting document {document_id}: {e}")
            return False
    
    def query(
        self, 
        query_text: str, 
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None
    ) -> QueryResult:
        """
        Query documents by semantic similarity
        
        Args:
            query_text: Query text
            n_results: Number of results to return
            where: Metadata filter (e.g., {"is_active": True})
            where_document: Document content filter
        
        Returns:
            QueryResult with documents, metadata, distances, and IDs
        """
        try:
            query_params = {
                "query_texts": [query_text],
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"]
            }
            
            if where:
                query_params["where"] = where
            if where_document:
                query_params["where_document"] = where_document
            
            results = self.collection.query(**query_params)
            
            # Parse results
            documents = results['documents'][0] if results['documents'] else []
            metadatas = [
                DocumentMetadata.from_dict(m) 
                for m in (results['metadatas'][0] if results['metadatas'] else [])
            ]
            distances = results['distances'][0] if results['distances'] else []
            ids = results['ids'][0] if results['ids'] else []
            
            return QueryResult(
                documents=documents,
                metadatas=metadatas,
                distances=distances,
                ids=ids
            )
            
        except Exception as e:
            logger.error(f"Error querying documents: {e}")
            return QueryResult(documents=[], metadatas=[], distances=[], ids=[])
    
    def list_documents(
        self,
        where: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Document]:
        """
        List documents with optional filtering and pagination
        
        Args:
            where: Metadata filter
            limit: Maximum number of documents to return
            offset: Number of documents to skip
        
        Returns:
            List of Document objects
        """
        try:
            get_params = {
                "include": ["documents", "metadatas"]
            }
            
            if where:
                get_params["where"] = where
            if limit:
                get_params["limit"] = limit
            if offset:
                get_params["offset"] = offset
            
            results = self.collection.get(**get_params)
            
            documents = []
            for i, doc_id in enumerate(results['ids']):
                metadata = DocumentMetadata.from_dict(results['metadatas'][i])
                doc = Document(
                    id=doc_id,
                    content=results['documents'][i],
                    metadata=metadata
                )
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            return []
    
    def count_documents(self, where: Optional[Dict[str, Any]] = None) -> int:
        """
        Count documents matching filter
        
        Args:
            where: Metadata filter
        
        Returns:
            int: Number of documents
        """
        try:
            if where:
                results = self.collection.get(where=where, include=[])
                return len(results['ids'])
            else:
                return self.collection.count()
        except Exception as e:
            logger.error(f"Error counting documents: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the knowledge base
        
        Returns:
            Dict with statistics
        """
        try:
            all_docs = self.list_documents()
            
            active_count = sum(1 for doc in all_docs if doc.metadata.is_active)
            sources = set(doc.metadata.source for doc in all_docs)
            source_ids = set(doc.metadata.source_id for doc in all_docs)
            
            # Tags distribution
            tags_dist = {}
            for doc in all_docs:
                for tag in doc.metadata.tags:
                    tags_dist[tag] = tags_dist.get(tag, 0) + 1
            
            # Version distribution
            version_dist = {}
            for doc in all_docs:
                version = doc.metadata.version
                version_dist[version] = version_dist.get(version, 0) + 1
            
            return {
                "total_documents": len(all_docs),
                "active_documents": active_count,
                "unique_sources": len(sources),
                "unique_source_ids": len(source_ids),
                "tags_distribution": tags_dist,
                "version_distribution": version_dist
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                "total_documents": 0,
                "active_documents": 0,
                "unique_sources": 0,
                "unique_source_ids": 0,
                "tags_distribution": {},
                "version_distribution": {}
            }
    
    def deactivate_old_versions(self, source_id: str, current_version: str) -> int:
        """
        Deactivate all versions of a source_id except the current one
        
        Args:
            source_id: Source ID to update
            current_version: Version to keep active
        
        Returns:
            int: Number of documents deactivated
        """
        try:
            # Get all documents with this source_id
            docs = self.list_documents(where={"source_id": source_id})
            
            deactivated = 0
            for doc in docs:
                if doc.metadata.version != current_version and doc.metadata.is_active:
                    if self.soft_delete_document(doc.id):
                        deactivated += 1
            
            logger.info(f"Deactivated {deactivated} old versions of {source_id}")
            return deactivated
            
        except Exception as e:
            logger.error(f"Error deactivating old versions: {e}")
            return 0
    
    def _generate_document_id(self, content: str, metadata: DocumentMetadata) -> str:
        """
        Generate a unique document ID based on content and metadata
        
        Args:
            content: Document content
            metadata: Document metadata
        
        Returns:
            str: Generated document ID
        """
        # Create hash from source_id, version, and content hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        id_string = f"{metadata.source_id}:{metadata.version}:{content_hash}"
        doc_id = hashlib.sha256(id_string.encode()).hexdigest()[:24]
        
        return f"doc_{doc_id}"
    
    def reset_collection(self):
        """Reset the collection (for testing purposes)"""
        try:
            self.client.delete_collection(name=self.collection_name)
            self.collection = self._get_or_create_collection()
            logger.warning(f"Collection {self.collection_name} has been reset")
        except Exception as e:
            logger.error(f"Error resetting collection: {e}")
