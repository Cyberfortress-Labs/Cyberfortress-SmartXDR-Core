"""
AI/LLM API Routes - RAG Query Endpoint with Conversation Memory
"""
import traceback
from flask import Blueprint, request, jsonify
from app import get_collection
from app.services.llm_service import LLMService
from app.middleware.auth import require_api_key
from app.config import *
from app.utils.logger import ai_route_logger as logger

# Get logger

ai_bp = Blueprint('ai', __name__)

# Initialize LLM Service (singleton)
try:
    llm_service = LLMService()
    logger.info("LLM Service initialized")
except Exception as e:
    logger.error(f"Failed to initialize LLM Service: {e}", exc_info=True)
    llm_service = None

@ai_bp.route('/ask', methods=['POST'])
@require_api_key('ai:ask')
def ask_llm():
    """
    Ask LLM a question using RAG (Retrieval-Augmented Generation)
    
    Request Body:
        {
            "query": "What is Suricata's management IP?",
            "n_results": 25,  // optional, default: DEFAULT_RESULTS
            "filter": {},     // optional, metadata filter
            "session_id": "uuid"  // optional, for conversation memory
        }
    
    Response:
        {
            "status": "success",
            "query": "What is Suricata's management IP?",
            "answer": "Suricata's management IP is 10.10.21.11...",
            "cached": false,
            "session_id": "uuid"  // returned if session was used
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
        
        # Get JSON with proper UTF-8 encoding handling
        try:
            data = request.get_json(force=True, silent=False)
            if data is None:
                # Fallback: manually decode with UTF-8
                import json
                data = json.loads(request.get_data(as_text=True))
        except UnicodeDecodeError:
            # Handle non-UTF-8 encoded requests
            import json
            raw_data = request.get_data()
            data = json.loads(raw_data.decode('utf-8', errors='replace'))
        except Exception as e:
            logger.error(f"Failed to parse JSON: {e}")
            return jsonify({
                'status': 'error',
                'message': f'Invalid JSON format: {str(e)}'
            }), 400
        
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
        n_results = data.get('n_results', DEFAULT_RESULTS)
        filter_metadata = data.get('filter', None)
        session_id = data.get('session_id', None)  # NEW: conversation memory
        
        # Validate n_results
        if not isinstance(n_results, int) or n_results < 1 or n_results > 100:
            return jsonify({
                'status': 'error',
                'message': f'n_results must be an integer between 1 and 100'
            }), 400
        
        # Validate session_id if provided
        if session_id is not None and not isinstance(session_id, str):
            return jsonify({
                'status': 'error',
                'message': 'session_id must be a string'
            }), 400
        
        logger.info(f"Processing query: {query[:DEBUG_TEXT_LENGTH]}..." + (f" [session: {session_id[:DEBUG_TEXT_LENGTH]}...]" if session_id else ""))
        
        # Call LLM Service with new RAG architecture
        result = llm_service.ask_rag(
            query=query,
            top_k=n_results,
            filters=filter_metadata,
            session_id=session_id  # NEW: pass session_id
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
        
        response = {
            'status': 'success',
            'query': query,
            'answer': result['answer'],
            'cached': result.get('cached', False),
            'sources': result.get('sources', []),
            'n_results': n_results
        }
        
        # Include session_id if used
        if result.get('session_id'):
            response['session_id'] = result['session_id']
        
        return jsonify(response), 200
        
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

@ai_bp.route('/sessions/<session_id>/history', methods=['GET'])
@require_api_key('ai:ask')
def get_session_history(session_id: str):
    """
    Get conversation history for a session
    
    Response:
        {
            "status": "success",
            "session_id": "...",
            "history": [
                {"role": "user", "content": "...", "timestamp": ...},
                {"role": "assistant", "content": "...", "timestamp": ...}
            ],
            "message_count": 4
        }
    """
    try:
        from app.services.conversation_memory import get_conversation_memory
        memory = get_conversation_memory()
        
        history = memory.get_session_history(session_id)
        info = memory.get_session_info(session_id)
        
        return jsonify({
            'status': 'success',
            'session_id': session_id,
            'history': history,
            'message_count': info.get('message_count', 0),
            'exists': info.get('exists', False)
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get session history: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Failed to get history: {str(e)}'
        }), 500

@ai_bp.route('/sessions/<session_id>', methods=['DELETE'])
@require_api_key('ai:admin')
def clear_session(session_id: str):
    """
    Clear a conversation session
    
    Response:
        {
            "status": "success",
            "message": "Session cleared successfully"
        }
    """
    try:
        from app.services.conversation_memory import get_conversation_memory
        memory = get_conversation_memory()
        
        cleared = memory.clear_session(session_id)
        
        if cleared:
            return jsonify({
                'status': 'success',
                'message': f'Session {session_id} cleared successfully'
            }), 200
        else:
            return jsonify({
                'status': 'success',
                'message': f'Session {session_id} not found (may already be cleared)'
            }), 200
        
    except Exception as e:
        logger.error(f"Failed to clear session: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Failed to clear session: {str(e)}'
        }), 500

@ai_bp.route('/sessions/stats', methods=['GET'])
@require_api_key('ai:stats')
def get_conversation_stats():
    """
    Get conversation memory statistics
    
    Response:
        {
            "status": "success",
            "stats": {
                "active_sessions": 5,
                "in_memory_messages": 42,
                "chromadb_messages": 150
            }
        }
    """
    try:
        from app.services.conversation_memory import get_conversation_memory
        memory = get_conversation_memory()
        
        stats = memory.get_stats()
        
        return jsonify({
            'status': 'success',
            'stats': stats
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get conversation stats: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Failed to get stats: {str(e)}'
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

