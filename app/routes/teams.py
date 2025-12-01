"""
Teams Middleware API Routes
Provides REST endpoints to manage the Teams middleware service
"""
from flask import Blueprint, jsonify, request
from app.services.teams_middleware_service import get_teams_middleware, TeamsConfig

teams_bp = Blueprint('teams', __name__)

# Get middleware singleton
middleware = None


def _get_middleware():
    """Lazy initialization of middleware"""
    global middleware
    if middleware is None:
        middleware = get_teams_middleware()
    return middleware


@teams_bp.route('/status', methods=['GET'])
def get_status():
    """
    Get Teams middleware status
    
    Response:
        {
            "status": "success",
            "middleware": {
                "running": true,
                "messages_received": 10,
                "messages_processed": 10,
                "messages_replied": 10,
                "errors": 0,
                "started_at": "2024-01-01T00:00:00",
                "last_poll": "2024-01-01T00:00:00"
            }
        }
    """
    try:
        mw = _get_middleware()
        stats = mw.get_stats()
        
        return jsonify({
            'status': 'success',
            'middleware': stats
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@teams_bp.route('/start', methods=['POST'])
def start_middleware():
    """
    Start Teams middleware service (non-blocking)
    
    Response:
        {
            "status": "success",
            "message": "Middleware started"
        }
    """
    try:
        mw = _get_middleware()
        
        # Check if already running
        stats = mw.get_stats()
        if stats.get('running'):
            return jsonify({
                'status': 'warning',
                'message': 'Middleware is already running'
            }), 200
        
        # Start in background
        success = mw.start(blocking=False)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Middleware started successfully'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to start middleware. Check configuration.'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@teams_bp.route('/stop', methods=['POST'])
def stop_middleware():
    """
    Stop Teams middleware service
    
    Response:
        {
            "status": "success",
            "message": "Middleware stopped"
        }
    """
    try:
        mw = _get_middleware()
        mw.stop()
        
        return jsonify({
            'status': 'success',
            'message': 'Middleware stopped'
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@teams_bp.route('/config', methods=['GET'])
def get_config():
    """
    Get current Teams middleware configuration (sanitized)
    
    Response:
        {
            "status": "success",
            "config": {
                "tenant_id": "abc***xyz",
                "client_id": "...",
                "team_id": "...",
                "channel_id": "...",
                "polling_interval": 3,
                "bot_mention": "@SmartXDR",
                "smartxdr_api_url": "http://..."
            }
        }
    """
    try:
        config = TeamsConfig()
        
        # Sanitize sensitive values
        def mask(value, show_chars=4):
            if not value:
                return "(not set)"
            if len(value) <= show_chars * 2:
                return "****"
            return value[:show_chars] + "***" + value[-show_chars:]
        
        return jsonify({
            'status': 'success',
            'config': {
                'tenant_id': mask(config.tenant_id),
                'client_id': mask(config.client_id),
                'client_secret_set': bool(config.client_secret),
                'team_id': mask(config.team_id),
                'channel_id': config.channel_id[:30] + '...' if len(config.channel_id) > 30 else config.channel_id,
                'polling_interval': config.polling_interval,
                'bot_mention': config.bot_mention,
                'smartxdr_api_url': config.smartxdr_api_url
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': str(e)
        }), 500


@teams_bp.route('/test', methods=['POST'])
def test_connection():
    """
    Test Teams connection (validates credentials)
    
    Response:
        {
            "status": "success",
            "message": "Connection successful",
            "details": {
                "token_acquired": true,
                "channel_accessible": true
            }
        }
    """
    try:
        import requests
        import msal
        
        config = TeamsConfig()
        
        # Validate config first
        valid, message = config.validate()
        if not valid:
            return jsonify({
                'status': 'error',
                'message': f'Invalid configuration: {message}'
            }), 400
        
        results = {
            'config_valid': True,
            'token_acquired': False,
            'channel_accessible': False
        }
        
        # Test MSAL token acquisition
        try:
            msal_app = msal.ConfidentialClientApplication(
                config.client_id,
                authority=f"https://login.microsoftonline.com/{config.tenant_id}",
                client_credential=config.client_secret
            )
            result = msal_app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )
            
            if "access_token" in result:
                results['token_acquired'] = True
                token = result['access_token']
            else:
                return jsonify({
                    'status': 'error',
                    'message': f"Token error: {result.get('error_description', 'Unknown')}",
                    'details': results
                }), 401
                
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'MSAL error: {str(e)}',
                'details': results
            }), 500
        
        # Test channel access
        try:
            headers = {"Authorization": f"Bearer {token}"}
            url = f"https://graph.microsoft.com/v1.0/teams/{config.team_id}/channels/{config.channel_id}"
            
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                results['channel_accessible'] = True
                channel_info = resp.json()
                results['channel_name'] = channel_info.get('displayName', 'Unknown')
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Channel access failed: HTTP {resp.status_code}',
                    'details': results
                }), 403
                
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Channel test error: {str(e)}',
                'details': results
            }), 500
        
        return jsonify({
            'status': 'success',
            'message': 'All tests passed! Connection ready.',
            'details': results
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
