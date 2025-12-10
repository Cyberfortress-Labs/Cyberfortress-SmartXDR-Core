"""
RAG Data Models
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field


@dataclass
class DocumentMetadata:
    """Metadata for RAG documents"""
    source: str  # File path, URL, module name
    source_id: str  # Unique logical ID for document
    version: str  # Version string (e.g., "v1.0.0", ISO date, commit hash)
    is_active: bool = True  # Is this version active?
    tags: List[str] = field(default_factory=list)  # Classification tags
    created_at: Optional[str] = None  # ISO format datetime
    updated_at: Optional[str] = None  # ISO format datetime
    custom_metadata: Dict[str, Any] = field(default_factory=dict)  # Additional metadata
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ChromaDB storage"""
        return {
            'source': self.source,
            'source_id': self.source_id,
            'version': self.version,
            'is_active': self.is_active,
            'tags': ','.join(self.tags) if self.tags else '',
            'created_at': self.created_at or datetime.utcnow().isoformat(),
            'updated_at': self.updated_at or datetime.utcnow().isoformat(),
            **self.custom_metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DocumentMetadata':
        """Create from dictionary"""
        tags_str = data.get('tags', '')
        tags = [t.strip() for t in tags_str.split(',') if t.strip()] if tags_str else []
        
        # Extract known fields
        known_fields = {'source', 'source_id', 'version', 'is_active', 'tags', 'created_at', 'updated_at'}
        custom_metadata = {k: v for k, v in data.items() if k not in known_fields}
        
        return cls(
            source=data.get('source', ''),
            source_id=data.get('source_id', ''),
            version=data.get('version', ''),
            is_active=data.get('is_active', True),
            tags=tags,
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            custom_metadata=custom_metadata
        )


@dataclass
class Document:
    """RAG Document with content and metadata"""
    id: str  # ChromaDB document ID
    content: str  # Document text content
    metadata: DocumentMetadata
    embedding: Optional[List[float]] = None  # Optional embedding vector
    
    def to_chroma_format(self) -> Dict[str, Any]:
        """Convert to ChromaDB storage format"""
        return {
            'id': self.id,
            'document': self.content,
            'metadata': self.metadata.to_dict()
        }


@dataclass
class QueryResult:
    """Result from RAG query"""
    documents: List[str]  # Retrieved document contents
    metadatas: List[DocumentMetadata]  # Document metadata
    distances: List[float]  # Distance scores
    ids: List[str]  # Document IDs
    
    def get_sources(self) -> List[str]:
        """Extract unique sources"""
        return list(set(meta.source for meta in self.metadatas))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'documents': self.documents,
            'metadatas': [m.to_dict() for m in self.metadatas],
            'distances': self.distances,
            'ids': self.ids,
            'sources': self.get_sources()
        }
