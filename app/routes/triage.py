"""
Security Triage & Alert Summarization Routes
"""
from flask import Blueprint, request, jsonify
from app.services.llm_service import LLMService
from app.services.elasticsearch_service import ElasticsearchService
from app.middleware.auth import require_api_key

# Try to import source config
try:
    from app.sources_config import get_source_config, reload_source_config
    SOURCE_CONFIG = get_source_config()
except ImportError:
    SOURCE_CONFIG = None
    reload_source_config = None

triage_bp = Blueprint('triage', __name__)

# Initialize services (singleton)
llm_service = LLMService()
es_service = ElasticsearchService()


@triage_bp.route('/alerts/summary', methods=['GET', 'POST'])
@require_api_key('triage:summary')
def summarize_alerts():
    """
    Summarize security alerts from ElastAlert2 and Kibana Security
    
    Query Params (GET) or Request Body (POST):
        - hours: Time range in hours (default: 24, max: 168)
    
    Response:
        {
            "status": "success",
            "summary": "Tóm tắt cảnh báo bảo mật...",
            "severity_level": "CRITICAL/HIGH/MEDIUM/LOW",
            "key_findings": [...],
            "recommended_actions": [...],
            "metadata": {
                "time_range_hours": 24,
                "total_alerts": 150,
                "elastalert_count": 30,
                "kibana_count": 120,
                "generated_at": "2024-..."
            }
        }
    
    Error Response:
        {
            "status": "error",
            "message": "Error description"
        }
    """
    try:
        # Get time range from query params or request body
        if request.method == 'POST':
            data = request.get_json() or {}
            hours = data.get('hours', 24)
        else:
            hours = request.args.get('hours', 24, type=int)
        
        # Validate hours
        if not isinstance(hours, int) or hours < 1:
            hours = 24
        if hours > 240:  # Max 10 days
            hours = 240
        
        # Step 1: Get combined alert data from Elasticsearch
        combined_data = es_service.get_combined_alerts_for_daily_report(hours=hours)
        
        if combined_data.get('status') == 'error':
            return jsonify({
                'status': 'error',
                'message': f"Failed to fetch alert data: {combined_data.get('error', 'Unknown error')}"
            }), 500
        
        # Step 2: Call LLM Service to summarize
        result = llm_service.summarize_alerts(combined_data)
        
        if result.get('status') == 'error':
            return jsonify({
                'status': 'error',
                'message': result.get('error', 'Summarization failed'),
                'metadata': result.get('metadata', {})
            }), 500
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500


@triage_bp.route('/alerts/raw', methods=['GET'])
@require_api_key('triage:read')
def get_raw_alerts():
    """
    Get raw alert data without AI summarization
    
    Query Params:
        - hours: Time range in hours (default: 24, max: 240)
        - source: Data source to query:
            * "all" - Combined data from all sources (default)
            * "elastalert" - ElastAlert2 critical alerts
            * "kibana" - Kibana Security alerts
            * "ml" - ML predictions only
            * Log sources from config: "pfsense", "suricata", "zeek", etc.
            * Custom: Any string will be tried as {source}-* pattern
    
    Response:
        {
            "status": "success",
            "source": "suricata",
            "hours": 24,
            "data": {...}
        }
    """
    try:
        hours = request.args.get('hours', 24, type=int)
        source = request.args.get('source', 'all').lower()
        
        # Validate hours
        if hours < 1:
            hours = 24
        if hours > 240:
            hours = 240
        
        # Check if source is aggregated type
        aggregated_sources = ['all', 'elastalert', 'kibana', 'ml']
        
        # Fetch data based on source
        if source == 'all':
            data = es_service.get_combined_alerts_for_daily_report(hours=hours)
        elif source == 'elastalert':
            data = es_service.get_elastalert_alerts(hours=hours)
        elif source == 'kibana':
            data = es_service.get_kibana_security_alerts(hours=hours)
        elif source == 'ml':
            data = es_service.get_ml_predictions(hours=hours)
        else:
            # Use the new method that reads from config
            data = es_service.get_logs_by_source_name(
                source_name=source,
                hours=hours
            )
        
        if data.get('status') == 'error':
            return jsonify({
                'status': 'error',
                'message': data.get('error', 'Failed to fetch data')
            }), 500
        
        return jsonify({
            'status': 'success',
            'source': source,
            'hours': hours,
            'data': data
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500


@triage_bp.route('/sources', methods=['GET'])
@require_api_key('triage:read')
def list_available_sources():
    """
    List all available log sources from configuration
    
    Query Params:
        - reload: Set to "true" to reload config from file
    
    Response:
        {
            "status": "success",
            "sources": {
                "aggregated": ["all", "elastalert", "kibana", "ml"],
                "log_sources": {
                    "suricata": "suricata-*",
                    "pfsense": "*pfsense*",
                    ...
                },
                "categories": {...}
            },
            "usage": "..."
        }
    """
    try:
        # Check if reload requested
        should_reload = request.args.get('reload', 'false').lower() == 'true'
        
        if should_reload and reload_source_config:
            reload_source_config()
        
        # Get sources from config or service
        if SOURCE_CONFIG:
            sources = SOURCE_CONFIG.to_dict()
        else:
            sources = es_service.get_available_sources()
        
        return jsonify({
            'status': 'success',
            'sources': sources,
            'usage': {
                'aggregated': 'GET /api/triage/alerts/raw?source=elastalert&hours=24',
                'log_source': 'GET /api/triage/alerts/raw?source=suricata&hours=24',
                'custom': 'GET /api/triage/alerts/raw?source=custom-index&hours=24',
                'reload_config': 'GET /api/triage/sources?reload=true'
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error listing sources: {str(e)}'
        }), 500


@triage_bp.route('/alerts/statistics', methods=['GET'])
@require_api_key('triage:read')
def get_alert_statistics():
    """
    Get aggregated statistics from Elasticsearch
    
    Query Params:
        - hours: Time range in hours (default: 24)
    
    Response:
        {
            "status": "success",
            "statistics": {
                "top_attacked_ips": [...],
                "top_attacker_ips": [...],
                "event_distribution": {...},
                ...
            }
        }
    """
    try:
        hours = request.args.get('hours', 24, type=int)
        
        if hours < 1:
            hours = 24
        if hours > 240:
            hours = 240
        
        # Get aggregated statistics
        stats = es_service.get_aggregated_statistics(hours=hours)
        
        if stats.get('status') == 'error':
            return jsonify({
                'status': 'error',
                'message': stats.get('error', 'Failed to fetch statistics')
            }), 500
        
        return jsonify({
            'status': 'success',
            'hours': hours,
            'statistics': stats
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500


@triage_bp.route('/ml/predictions', methods=['GET'])
@require_api_key('triage:read')
def get_ml_predictions():
    """
    Get ML log classification predictions
    
    ML Pipeline classifies logs into:
    - EROR: Critical, needs immediate attention
    - WARN: Needs review, potential issue
    - INFO: Normal activity
    
    Query Params:
        - hours: Time range in hours (default: 24, max: 168)
        - min_probability: Minimum prediction probability (default: 0.5)
    
    Response:
        {
            "status": "success",
            "hours": 24,
            "total": 1500,
            "by_severity": {
                "EROR": {"count": 50, "samples": [...]},
                "WARN": {"count": 200, "samples": [...]},
                "INFO": {"count": 1250, "samples": [...]}
            },
            "summary": {
                "high_confidence_count": 800,
                "severity_distribution": {...}
            }
        }
    """
    try:
        hours = request.args.get('hours', 24, type=int)
        min_probability = request.args.get('min_probability', 0.5, type=float)
        
        # Validate
        if hours < 1:
            hours = 24
        if hours > 240:
            hours = 240
        if min_probability < 0 or min_probability > 1:
            min_probability = 0.5
        
        # Get ML predictions
        predictions = es_service.get_ml_predictions(
            hours=hours,
            min_probability=min_probability
        )
        
        if predictions.get('summary', {}).get('error'):
            return jsonify({
                'status': 'error',
                'message': predictions['summary']['error']
            }), 500
        
        return jsonify({
            'status': 'success',
            'hours': hours,
            'min_probability': min_probability,
            **predictions
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500


@triage_bp.route('/health', methods=['GET'])
def triage_health():
    """
    Health check for triage service
    
    Response:
        {
            "status": "healthy",
            "services": {
                "elasticsearch": true/false,
                "llm_service": true/false
            }
        }
    """
    try:
        # Check Elasticsearch connection
        es_health = es_service.health_check() if hasattr(es_service, 'health_check') else True
        
        # LLM Service is always available (singleton)
        llm_health = True
        
        all_healthy = es_health and llm_health
        
        return jsonify({
            'status': 'healthy' if all_healthy else 'degraded',
            'services': {
                'elasticsearch': es_health,
                'llm_service': llm_health
            }
        }), 200 if all_healthy else 503
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503
