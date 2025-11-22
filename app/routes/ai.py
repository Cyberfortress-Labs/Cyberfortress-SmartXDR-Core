"""
AI/LLM API Routes - RAG Query Endpoint
"""
from flask import Blueprint, request, jsonify
from app.core.query import ask
from app import get_collection

ai_bp = Blueprint('ai', __name__)


@ai_bp.route('/ask', methods=['POST'])
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
        
        # Get collection
        collection = get_collection()
        if collection is None:
            return jsonify({
                'status': 'error',
                'message': 'Database not initialized'
            }), 500
        
        # Call RAG query
        answer = ask(collection, query, n_results=n_results, filter_metadata=filter_metadata)
        
        # Check if response is an error message
        is_error = answer.startswith('ERROR:')
        cached = 'Cache hit!' in answer or answer.startswith('Cache hit!')
        
        if is_error:
            return jsonify({
                'status': 'error',
                'query': query,
                'message': answer
            }), 429 if 'Rate limit' in answer or 'cost limit' in answer else 500
        
        return jsonify({
            'status': 'success',
            'query': query,
            'answer': answer,
            'cached': cached,
            'n_results': n_results
        }), 200
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500


@ai_bp.route('/stats', methods=['GET'])
def get_stats():
    """
    Get API usage statistics
    
    Response:
        {
            "status": "success",
            "stats": {
                "rate_limit": {
                    "calls_last_minute": 5,
                    "max_calls_per_minute": 20
                },
                "cost": {
                    "daily_cost": 0.0234,
                    "max_daily_cost": 1.0,
                    "reset_date": "2025-11-22"
                },
                "cache": {
                    "cache_size": 12,
                    "ttl": 3600,
                    "enabled": true
                }
            }
        }
    """
    try:
        from app.core.query import usage_tracker, response_cache
        
        usage_stats = usage_tracker.get_stats()
        cache_stats = response_cache.get_stats()
        
        return jsonify({
            'status': 'success',
            'stats': {
                'rate_limit': {
                    'calls_last_minute': usage_stats['calls_last_minute'],
                    'max_calls_per_minute': usage_stats['max_calls_per_minute']
                },
                'cost': {
                    'daily_cost': usage_stats['daily_cost'],
                    'max_daily_cost': usage_stats['max_daily_cost'],
                    'reset_date': usage_stats['cost_reset_date']
                },
                'cache': {
                    'cache_size': cache_stats['cache_size'],
                    'ttl': cache_stats['ttl'],
                    'enabled': cache_stats['enabled']
                }
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to get stats: {str(e)}'
        }), 500


@ai_bp.route('/cache/clear', methods=['POST'])
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
        from app.core.query import response_cache
        
        response_cache.clear()
        
        return jsonify({
            'status': 'success',
            'message': 'Cache cleared successfully'
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to clear cache: {str(e)}'
        }), 500
