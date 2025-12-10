"""
Pydantic Schemas for RAG API validation
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime


class DocumentMetadataSchema(BaseModel):
    """Schema for document metadata"""
    source: str = Field(..., description="Source of the document (file path, URL, module name)")
    source_id: str = Field(..., description="Unique logical identifier for the document")
    version: str = Field(..., description="Version identifier (e.g., v1.0.0, ISO date, commit hash)")
    is_active: bool = Field(default=True, description="Whether this version is active")
    tags: List[str] = Field(default_factory=list, description="Classification tags")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp (ISO format)")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp (ISO format)")
    custom_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional custom metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source": "docs/security_guide.md",
                "source_id": "security-guide",
                "version": "v2.0.0",
                "is_active": True,
                "tags": ["security", "documentation"],
                "custom_metadata": {"author": "security_team"}
            }
        }


class CreateDocumentRequest(BaseModel):
    """Request to create a new document"""
    content: str = Field(..., description="Document content (text or chunks joined)")
    metadata: DocumentMetadataSchema = Field(..., description="Document metadata")
    chunks: Optional[List[str]] = Field(default=None, description="Optional: pre-chunked content")
    
    class Config:
        json_schema_extra = {
            "example": {
                "content": "This is a security guide for Cyberfortress...",
                "metadata": {
                    "source": "docs/security_guide.md",
                    "source_id": "security-guide",
                    "version": "v2.0.0",
                    "tags": ["security", "documentation"]
                }
            }
        }


class UpdateDocumentRequest(BaseModel):
    """Request to update an existing document"""
    content: Optional[str] = Field(default=None, description="Updated document content")
    metadata: Optional[DocumentMetadataSchema] = Field(default=None, description="Updated metadata")
    chunks: Optional[List[str]] = Field(default=None, description="Optional: updated chunks")
    
    class Config:
        json_schema_extra = {
            "example": {
                "content": "Updated security guide content...",
                "metadata": {
                    "version": "v2.1.0",
                    "is_active": True
                }
            }
        }


class DocumentResponse(BaseModel):
    """Response with document details"""
    id: str = Field(..., description="Document ID")
    content: str = Field(..., description="Document content")
    metadata: DocumentMetadataSchema = Field(..., description="Document metadata")
    created_at: str = Field(..., description="Creation timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "doc_123abc",
                "content": "This is a security guide...",
                "metadata": {
                    "source": "docs/security_guide.md",
                    "source_id": "security-guide",
                    "version": "v2.0.0",
                    "tags": ["security"]
                },
                "created_at": "2025-01-01T00:00:00Z"
            }
        }


class ListDocumentsRequest(BaseModel):
    """Request to list/filter documents"""
    source_id: Optional[str] = Field(default=None, description="Filter by source_id")
    source: Optional[str] = Field(default=None, description="Filter by source")
    version: Optional[str] = Field(default=None, description="Filter by version")
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags (AND logic)")
    is_active: Optional[bool] = Field(default=None, description="Filter by active status")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_id": "security-guide",
                "is_active": True,
                "tags": ["security"],
                "page": 1,
                "page_size": 20
            }
        }


class ListDocumentsResponse(BaseModel):
    """Response with list of documents"""
    documents: List[DocumentResponse] = Field(..., description="List of documents")
    total: int = Field(..., description="Total number of matching documents")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")


class RAGQueryRequest(BaseModel):
    """Request for RAG query"""
    query: str = Field(..., description="User's question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of documents to retrieve")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Metadata filters")
    include_sources: bool = Field(default=True, description="Include source documents in response")
    
    @validator('filters')
    def validate_filters(cls, v):
        """Validate filter format"""
        if v is not None:
            allowed_keys = {'source', 'source_id', 'version', 'is_active', 'tags'}
            invalid_keys = set(v.keys()) - allowed_keys
            if invalid_keys:
                raise ValueError(f"Invalid filter keys: {invalid_keys}. Allowed: {allowed_keys}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "How do I configure Suricata IDS?",
                "top_k": 5,
                "filters": {
                    "is_active": True,
                    "tags": "security"
                },
                "include_sources": True
            }
        }


class RAGQueryResponse(BaseModel):
    """Response from RAG query"""
    status: str = Field(..., description="Response status (success/error)")
    answer: str = Field(..., description="Generated answer")
    sources: List[str] = Field(default_factory=list, description="Source documents")
    cached: bool = Field(default=False, description="Whether response was cached")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    error: Optional[str] = Field(default=None, description="Error message if status is error")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "answer": "To configure Suricata IDS, you need to...",
                "sources": ["docs/suricata_guide.md", "config/suricata.yaml"],
                "cached": False,
                "metadata": {
                    "documents_retrieved": 5,
                    "processing_time_ms": 234
                }
            }
        }


class DocumentStatsResponse(BaseModel):
    """Statistics about RAG documents"""
    total_documents: int = Field(..., description="Total number of documents")
    active_documents: int = Field(..., description="Number of active documents")
    unique_sources: int = Field(..., description="Number of unique sources")
    unique_source_ids: int = Field(..., description="Number of unique source IDs")
    tags_distribution: Dict[str, int] = Field(..., description="Distribution of tags")
    version_distribution: Dict[str, int] = Field(..., description="Distribution of versions")
