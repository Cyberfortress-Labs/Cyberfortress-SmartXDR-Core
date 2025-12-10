"""
AI/LLM API Routes - RAG Query Endpoint
"""
import traceback
import logging
from flask import Blueprint, request, jsonify
from app import get_collection
from app.services.llm_service import LLMService
from app.middleware.auth import require_api_key

# Get logger
logger = logging.getLogger('smartxdr.ai')

ai_bp = Blueprint('ai', __name__)

# Initialize LLM Service (singleton)
try:
    llm_service = LLMService()
    logger.info("✓ LLM Service initialized")
except Exception as e:
    logger.error(f"✗ Failed to initialize LLM Service: {e}", exc_info=True)
    llm_service = None


@ai_bp.route('/ask', methods=['POST'])
@require_api_key('ai:ask')
def ask_llm():
    """
    Ask LLM a question using RAG (Retrieval-Augmented Generation)
    
    Request Body:
        {
            "query": "What is Suricata's management IP?",
            "n_results": 10,  // optional, default: 10
            "filter": {}      // optional, metadata filter
        }
    
    Response:
        {
            "status": "success",
            "query": "What is Suricata's management IP?",
            "answer": "Suricata's management IP is 10.10.21.11...",
            "cached": false
        }
    
    Error Response:
        {
            "status": "error",
            "message": "Error description"
        }
    """
    try:
        # Check if LLM service initialized
        if llm_service is None:
            logger.error("LLM Service not initialized")
            return jsonify({
                'status': 'error',
                'message': 'LLM Service not initialized'
            }), 503
        
        # Validate request
        if not request.is_json:
            return jsonify({
                'status': 'error',
                'message': 'Content-Type must be application/json'
            }), 400
        
        data = request.get_json()
        
        # Validate required fields
        if 'query' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing required field: query'
            }), 400
        
        query = data['query'].strip()
        if not query:
            return jsonify({
                'status': 'error',
                'message': 'Query cannot be empty'
            }), 400
        
        # Optional parameters
        n_results = data.get('n_results', 10)
        filter_metadata = data.get('filter', None)
        
        # Validate n_results
        if not isinstance(n_results, int) or n_results < 1 or n_results > 50:
            return jsonify({
                'status': 'error',
                'message': 'n_results must be an integer between 1 and 50'
            }), 400
        
        logger.info(f"Processing query: {query[:100]}...")
        
        # Call LLM Service with new RAG architecture
        result = llm_service.ask_rag(
            query=query,
            top_k=n_results,
            filters=filter_metadata
        )
        
        # Handle response
        if result['status'] == 'error':
            error_type = result.get('error_type', 'unknown')
            status_code = 429 if error_type == 'rate_limit' else 500
            
            logger.error(f"LLM query failed: {result['error']}")
            
            return jsonify({
                'status': 'error',
                'query': query,
                'message': result['error']
            }), status_code
        
        logger.info(f"Query successful: {len(result.get('answer', ''))} chars")
        
        return jsonify({
            'status': 'success',
            'query': query,
            'answer': result['answer'],
            'cached': result.get('cached', False),
            'sources': result.get('sources', []),
            'n_results': n_results
        }), 200
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Exception in ask_llm: {e}", exc_info=True)
        logger.debug(f"Traceback: {traceback.format_exc()}")
        
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500


@ai_bp.route('/stats', methods=['GET'])
@require_api_key('ai:stats')
def get_stats():
    """
    Get API usage statistics
    
    Response:
        {
            "status": "success",
            "stats": {
                "rate_limit": {...},
                "cost": {...},
                "cache": {...}
            }
        }
    """
    try:
        if llm_service is None:
            logger.error("LLM Service not initialized")
            return jsonify({
                'status': 'error',
                'message': 'LLM Service not initialized'
            }), 503
        
        stats = llm_service.get_stats()
        
        return jsonify({
            'status': 'success',
            'stats': stats
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Failed to get stats: {str(e)}'
        }), 500


@ai_bp.route('/cache/clear', methods=['POST'])
@require_api_key('ai:admin')
def clear_cache():
    """
    Clear response cache
    
    Response:
        {
            "status": "success",
            "message": "Cache cleared successfully"
        }
    """
    try:
        if llm_service is None:
            logger.error("LLM Service not initialized")
            return jsonify({
                'status': 'error',
                'message': 'LLM Service not initialized'
            }), 503
        
        llm_service.clear_cache()
        
        return jsonify({
            'status': 'success',
            'message': 'Cache cleared successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Failed to clear cache: {str(e)}'
        }), 500
