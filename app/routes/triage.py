"""
Security Triage & Alert Summarization Routes
"""
from flask import Blueprint, request, jsonify
from app.services.llm_service import LLMService
from app.services.elasticsearch_service import ElasticsearchService
from app.services.alert_summarization_service import get_alert_summarization_service
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
alert_summarization_service = get_alert_summarization_service()


@triage_bp.route('/summarize-alerts', methods=['POST'])
@require_api_key('triage:summary')
def summarize_ml_alerts():
    """
    Summarize ML-classified alerts from Elasticsearch with risk scoring and AI analysis
    
    Request Body (POST):
        {
            "time_window_minutes": 10,  # Optional, uses config default if not provided
            "source_ip": "192.168.1.1",  # Optional, filter by source IP
            "include_ai_analysis": true  # Optional, include AI recommendations (default: false)
        }
    
    Response:
        {
            "success": true,
            "status": "completed",
            "count": 25,
            "time_window_minutes": 10,
            "grouped_alerts": [...],
            "summary": "Detailed summary with risk assessment...",
            "ai_analysis": "AI-generated recommendations...",  # If requested
            "risk_score": 65.5,
            "timestamp": "2024-..."
        }
    """
    try:
        # Get parameters from request body
        data = request.get_json() or {}
        time_window_minutes = data.get('time_window_minutes')
        source_ip = data.get('source_ip')
        include_ai = data.get('include_ai_analysis', False)
        index_pattern = data.get('index_pattern')  # New: filter by index pattern
        
        # Call alert summarization service
        result = alert_summarization_service.summarize_alerts(
            time_window_minutes=time_window_minutes,
            source_ip=source_ip,
            index_pattern=index_pattern
        )
        
        # Add AI analysis if requested and successful
        if include_ai and result.get('success'):
            ai_analysis = alert_summarization_service.get_ai_analysis(
                grouped_alerts=result.get('grouped_alerts', []),
                risk_score=result.get('risk_score', 0)
            )
            result['ai_analysis'] = ai_analysis
        
        # Return appropriate status code
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code
    
    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'error',
            'error': str(e)
        }), 500


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


@triage_bp.route('/send-report-email', methods=['POST'])
@require_api_key('triage:summary')
def send_report_email():
    """
    Send alert summary report via email
    
    Request Body:
        {
            "to_email": "analyst@example.com",  # Optional, uses FROM_EMAIL from .env if not provided
            "time_window_minutes": 10080,  # Optional, default from config
            "source_ip": "192.168.1.1",  # Optional
            "include_ai_analysis": true  # Optional, default: true
        }
    
    Response:
        {
            "success": true,
            "message": "Email sent successfully",
            "sent_to": "analyst@example.com",
            "timestamp": "2024-..."
        }
    """
    try:
        from app.services.email_service import get_email_service
        
        email_service = get_email_service()
        
        if not email_service.enabled:
            return jsonify({
                'success': False,
                'error': 'Email service not configured (check .env)'
            }), 503
        
        # Get parameters
        data = request.get_json() or {}
        to_email = data.get('to_email') or email_service.to_emails  # Use TO_EMAILS from .env
        time_window_minutes = data.get('time_window_minutes')
        source_ip = data.get('source_ip')
        include_ai = data.get('include_ai_analysis', True)
        
        # Get alert summary
        summary_data = alert_summarization_service.summarize_alerts(
            time_window_minutes=time_window_minutes,
            source_ip=source_ip
        )
        
        if not summary_data.get('success'):
            return jsonify({
                'success': False,
                'error': f"Failed to generate summary: {summary_data.get('error', 'Unknown')}"
            }), 500
        
        # Add AI analysis if requested
        if include_ai:
            ai_analysis = alert_summarization_service.get_ai_analysis(
                grouped_alerts=summary_data.get('grouped_alerts', []),
                risk_score=summary_data.get('risk_score', 0)
            )
            summary_data['ai_analysis'] = ai_analysis
        
        # Send email
        success = email_service.send_alert_summary_email(
            to_email=to_email,
            summary_data=summary_data
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Email sent successfully',
                'sent_to': to_email,
                'timestamp': summary_data.get('timestamp')
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send email'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@triage_bp.route('/daily-report/trigger', methods=['POST'])
@require_api_key('triage:admin')
def trigger_daily_report():
    """
    Manually trigger daily report email (for testing)
    
    Request Body:
        {
            "to_email": "analyst@example.com"  # Optional
        }
    
    Response:
        {
            "success": true,
            "message": "Report sent successfully"
        }
    """
    try:
        from app.services.daily_report_scheduler import get_daily_report_scheduler
        
        scheduler = get_daily_report_scheduler()
        
        if not scheduler.enabled:
            return jsonify({
                'success': False,
                'error': 'Daily report scheduler not configured'
            }), 503
        
        data = request.get_json() or {}
        to_email = data.get('to_email')
        
        success = scheduler.send_report_now(recipient_email=to_email)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Report sent successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send report'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
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
                "llm_service": true/false,
                "email_service": true/false,
                "daily_report": true/false
            }
        }
    """
    try:
        from app.services.email_service import get_email_service
        from app.services.daily_report_scheduler import get_daily_report_scheduler
        
        # Check Elasticsearch connection
        es_health = es_service.health_check() if hasattr(es_service, 'health_check') else True
        
        # LLM Service is always available (singleton)
        llm_health = True
        
        # Check email service
        email_service = get_email_service()
        email_health = email_service.enabled
        
        # Check daily report scheduler
        scheduler = get_daily_report_scheduler()
        scheduler_health = scheduler.enabled and scheduler.running
        
        all_healthy = es_health and llm_health
        
        return jsonify({
            'status': 'healthy' if all_healthy else 'degraded',
            'services': {
                'elasticsearch': es_health,
                'llm_service': llm_health,
                'email_service': email_health,
                'daily_report': scheduler_health
            }
        }), 200 if all_healthy else 503
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503
