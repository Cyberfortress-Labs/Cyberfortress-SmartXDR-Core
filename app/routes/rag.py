"""
RAG API Routes - REST endpoints for knowledge base management

Provides endpoints for:
- Document CRUD operations (POST/GET/PUT/DELETE /api/rag/documents)
- RAG query (POST /api/rag/query)
- Statistics (GET /api/rag/stats)
"""
from typing import Optional, List
from flask import Blueprint, request, jsonify
from pydantic import ValidationError

from app.rag.service import RAGService
from app.rag import schemas
from app.middleware.auth import require_api_key
from app.utils.rate_limit import rate_limit
from app.config import DEBUG_MODE
from app.utils.logger import rag_route_logger as logger

# Create Blueprint
rag_bp = Blueprint('rag', __name__, url_prefix='/api/rag')

# Initialize RAG Service (singleton)
rag_service = RAGService()

# ==================== Document Management Endpoints ====================

@rag_bp.route('/documents', methods=['POST'])
@require_api_key
@rate_limit(max_calls=30, window=60)  # 30 requests per minute
def create_document():
    """
    Create a new document in the knowledge base
    
    Request Body: CreateDocumentRequest
    Response: DocumentResponse
    """
    try:
        # Validate request
        data = request.get_json()
        req = schemas.CreateDocumentRequest(**data)
        
        # Add document
        result = rag_service.add_document(
            content=req.content,
            source=req.metadata.source,
            source_id=req.metadata.source_id,
            version=req.metadata.version,
            tags=req.metadata.tags,
            is_active=req.metadata.is_active,
            custom_metadata=req.metadata.custom_metadata,
            auto_deactivate_old=True
        )
        
        if result["status"] == "success":
            # Get created document
            doc = rag_service.get_document(result["document_id"])
            
            return jsonify({
                "status": "success",
                "data": {
                    "id": result["document_id"],
                    "content": doc["content"],
                    "metadata": doc["metadata"],
                    "created_at": doc["metadata"].get("created_at")
                },
                "message": result["message"]
            }), 201
        else:
            return jsonify({
                "status": "error",
                "error": result.get("error", "Failed to create document")
            }), 400
            
    except ValidationError as e:
        return jsonify({
            "status": "error",
            "error": "Validation error",
            "details": e.errors()
        }), 400
    except Exception as e:
        logger.error(f"Error creating document: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@rag_bp.route('/documents/batch', methods=['POST'])
@require_api_key
@rate_limit(max_calls=10, window=60)  # 10 batch requests per minute
def create_documents_batch():
    """
    Create multiple documents in batch
    
    Request Body: List[CreateDocumentRequest]
    Response: List of document IDs
    """
    try:
        data = request.get_json()
        
        if not isinstance(data, list):
            return jsonify({
                "status": "error",
                "error": "Request body must be a list of documents"
            }), 400
        
        # Validate each document
        documents = []
        for item in data:
            req = schemas.CreateDocumentRequest(**item)
            documents.append({
                "content": req.content,
                "source": req.metadata.source,
                "source_id": req.metadata.source_id,
                "version": req.metadata.version,
                "tags": req.metadata.tags,
                "is_active": req.metadata.is_active,
                "custom_metadata": req.metadata.custom_metadata
            })
        
        # Add documents
        result = rag_service.add_documents_batch(
            documents=documents,
            auto_deactivate_old=True
        )
        
        if result["status"] == "success":
            return jsonify({
                "status": "success",
                "data": {
                    "document_ids": result["document_ids"],
                    "count": result["count"]
                },
                "message": result["message"]
            }), 201
        else:
            return jsonify({
                "status": "error",
                "error": result.get("error", "Failed to create documents")
            }), 400
            
    except ValidationError as e:
        return jsonify({
            "status": "error",
            "error": "Validation error",
            "details": e.errors()
        }), 400
    except Exception as e:
        logger.error(f"Error creating documents batch: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@rag_bp.route('/documents', methods=['GET'])
@require_api_key
@rate_limit(max_calls=60, window=60)  # 60 requests per minute
def list_documents():
    """
    List documents with filtering and pagination
    
    Query Parameters: source_id, source, version, tags, is_active, page, page_size
    Response: ListDocumentsResponse
    """
    try:
        # Parse query parameters
        source_id = request.args.get('source_id')
        source = request.args.get('source')
        version = request.args.get('version')
        tags_str = request.args.get('tags')
        is_active_str = request.args.get('is_active')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        
        # Parse tags
        tags = None
        if tags_str:
            tags = [t.strip() for t in tags_str.split(',') if t.strip()]
        
        # Parse is_active
        is_active = None
        if is_active_str:
            is_active = is_active_str.lower() in ('true', '1', 'yes')
        
        # List documents
        result = rag_service.list_documents(
            source_id=source_id,
            source=source,
            version=version,
            tags=tags,
            is_active=is_active,
            page=page,
            page_size=page_size
        )
        
        if result["status"] == "success":
            return jsonify({
                "status": "success",
                "data": {
                    "documents": result["documents"],
                    "total": result["total"],
                    "page": result["page"],
                    "page_size": result["page_size"],
                    "total_pages": result["total_pages"]
                }
            }), 200
        else:
            return jsonify({
                "status": "error",
                "error": result.get("error", "Failed to list documents")
            }), 400
            
    except Exception as e:
        logger.error(f"Error listing documents: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@rag_bp.route('/documents/<document_id>', methods=['GET'])
@require_api_key
@rate_limit(max_calls=60, window=60)
def get_document(document_id: str):
    """
    Get a single document by ID
    
    Response: DocumentResponse
    """
    try:
        doc = rag_service.get_document(document_id)
        
        if doc:
            return jsonify({
                "status": "success",
                "data": {
                    "id": doc["id"],
                    "content": doc["content"],
                    "metadata": doc["metadata"],
                    "created_at": doc["metadata"].get("created_at")
                }
            }), 200
        else:
            return jsonify({
                "status": "error",
                "error": f"Document {document_id} not found"
            }), 404
            
    except Exception as e:
        logger.error(f"Error getting document: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@rag_bp.route('/documents/<document_id>', methods=['PUT'])
@require_api_key
@rate_limit(max_calls=30, window=60)
def update_document(document_id: str):
    """
    Update an existing document
    
    Request Body: UpdateDocumentRequest
    Response: Success message
    """
    try:
        data = request.get_json()
        req = schemas.UpdateDocumentRequest(**data)
        
        # Prepare update data
        update_metadata = None
        if req.metadata:
            update_metadata = req.metadata.dict(exclude_none=True)
        
        # Update document
        result = rag_service.update_document(
            document_id=document_id,
            content=req.content,
            metadata=update_metadata
        )
        
        if result["status"] == "success":
            return jsonify({
                "status": "success",
                "message": result["message"]
            }), 200
        else:
            return jsonify({
                "status": "error",
                "error": result.get("error", "Failed to update document")
            }), 400
            
    except ValidationError as e:
        return jsonify({
            "status": "error",
            "error": "Validation error",
            "details": e.errors()
        }), 400
    except Exception as e:
        logger.error(f"Error updating document: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@rag_bp.route('/documents/<document_id>', methods=['DELETE'])
@require_api_key
@rate_limit(max_calls=30, window=60)
def delete_document(document_id: str):
    """
    Delete a document (soft delete by default)
    
    Query Parameters: hard=true (for permanent deletion)
    Response: Success message
    """
    try:
        hard_delete = request.args.get('hard', 'false').lower() in ('true', '1', 'yes')
        
        result = rag_service.delete_document(
            document_id=document_id,
            soft=not hard_delete
        )
        
        if result["status"] == "success":
            return jsonify({
                "status": "success",
                "message": result["message"]
            }), 200
        else:
            return jsonify({
                "status": "error",
                "error": result.get("error", "Failed to delete document")
            }), 400
            
    except Exception as e:
        logger.error(f"Error deleting document: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# ==================== RAG Query Endpoint ====================

@rag_bp.route('/query', methods=['POST'])
@require_api_key
@rate_limit(max_calls=30, window=60)  # 30 queries per minute
def rag_query():
    """
    Query the knowledge base with RAG
    
    Request Body: RAGQueryRequest
    Response: RAGQueryResponse
    """
    try:
        data = request.get_json()
        req = schemas.RAGQueryRequest(**data)
        
        # Query knowledge base ONCE
        query_result = rag_service.query(
            query_text=req.query,
            top_k=req.top_k,
            filters=req.filters
        )
        
        if query_result["status"] == "error":
            return jsonify({
                "status": "error",
                "error": query_result["error"]
            }), 400
        
        # Build context from query result (NO EXTRA RAG QUERY)
        context_text = query_result.get("context", "")
        if not context_text and query_result.get("documents"):
            # Fallback: build context from documents if not provided
            context_text = "\n\n---\n\n".join(query_result["documents"][:req.top_k])
        
        # Call LLM with pre-built context
        from app.services.llm_service import LLMService
        llm_service = LLMService()
        
        # Use internal method to generate answer with existing context
        llm_result = llm_service._generate_answer_from_context(
            query=req.query,
            context=context_text,
            sources=query_result.get("sources", [])
        )
        
        # Build response
        response_data = {
            "status": "success",
            "answer": llm_result.get("answer", "No answer generated"),
            "sources": query_result["sources"] if req.include_sources else [],
            "cached": llm_result.get("cached", False),
            "metadata": {
                "documents_retrieved": len(query_result["documents"]),
                "processing_time_ms": query_result.get("query_time_ms", 0),
                "distances": query_result["distances"] if DEBUG_MODE else None
            }
        }
        
        return jsonify(response_data), 200
        
    except ValidationError as e:
        return jsonify({
            "status": "error",
            "error": "Validation error",
            "details": e.errors()
        }), 400
    except Exception as e:
        logger.error(f"Error processing RAG query: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# ==================== Statistics & Management ====================

@rag_bp.route('/stats', methods=['GET'])
@require_api_key
@rate_limit(max_calls=60, window=60)
def get_stats():
    """
    Get knowledge base statistics
    
    Response: DocumentStatsResponse
    """
    try:
        stats = rag_service.get_stats()
        
        repo_stats = stats["repository"]
        service_stats = stats["service"]
        
        return jsonify({
            "status": "success",
            "data": {
                "total_documents": repo_stats["total_documents"],
                "active_documents": repo_stats["active_documents"],
                "unique_sources": repo_stats["unique_sources"],
                "unique_source_ids": repo_stats["unique_source_ids"],
                "tags_distribution": repo_stats["tags_distribution"],
                "version_distribution": repo_stats["version_distribution"],
                "service_stats": {
                    "total_queries": service_stats["total_queries"],
                    "total_documents_added": service_stats["total_documents_added"],
                    "total_documents_updated": service_stats["total_documents_updated"],
                    "total_documents_deleted": service_stats["total_documents_deleted"],
                    "avg_query_time_ms": service_stats["avg_query_time_ms"]
                }
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@rag_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint (no auth required)"""
    return jsonify({
        "status": "healthy",
        "service": "rag",
        "version": "1.0.0"
    }), 200
