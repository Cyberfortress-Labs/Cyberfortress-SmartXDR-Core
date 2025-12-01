"""
Telegram Bot API Routes
Provides REST endpoints to manage the Telegram middleware service
"""
from flask import Blueprint, jsonify
from app.services.telegram_middleware_service import get_telegram_middleware, TelegramConfig

telegram_bp = Blueprint('telegram', __name__)


@telegram_bp.route('/status', methods=['GET'])
def get_status():
    """
    Get Telegram middleware status
    
    Response:
        {
            "status": "success",
            "middleware": {
                "running": true,
                "bot": "SmartXDR_Bot",
                "messages_received": 10,
                ...
            }
        }
    """
    try:
        mw = get_telegram_middleware()
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


@telegram_bp.route('/start', methods=['POST'])
def start_middleware():
    """Start Telegram middleware (non-blocking)"""
    try:
        mw = get_telegram_middleware()
        
        stats = mw.get_stats()
        if stats.get('running'):
            return jsonify({
                'status': 'warning',
                'message': 'Middleware is already running'
            }), 200
        
        success = mw.start(blocking=False)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Telegram middleware started',
                'bot': mw._bot_info.get('username') if mw._bot_info else None
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to start. Check TELEGRAM_BOT_TOKEN.'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@telegram_bp.route('/stop', methods=['POST'])
def stop_middleware():
    """Stop Telegram middleware"""
    try:
        mw = get_telegram_middleware()
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


@telegram_bp.route('/config', methods=['GET'])
def get_config():
    """Get configuration (sanitized)"""
    try:
        config = TelegramConfig()
        
        # Mask token
        token = config.bot_token
        if token and ':' in token:
            parts = token.split(':')
            masked = f"{parts[0]}:****...{parts[1][-4:]}"
        elif token:
            masked = f"{token[:8]}****"
        else:
            masked = "(not set)"
        
        return jsonify({
            'status': 'success',
            'config': {
                'bot_token_set': bool(config.bot_token),
                'bot_token_masked': masked,
                'allowed_chats': config.get_allowed_chats() or 'all',
                'polling_timeout': config.polling_timeout,
                'smartxdr_api_url': config.smartxdr_api_url
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@telegram_bp.route('/test', methods=['POST'])
def test_connection():
    """Test Telegram connection"""
    try:
        from app.services.telegram_middleware_service import TelegramMiddlewareService
        
        service = TelegramMiddlewareService()
        bot_info = service.get_bot_info()
        
        if bot_info:
            return jsonify({
                'status': 'success',
                'message': 'Connection successful!',
                'bot': {
                    'id': bot_info.get('id'),
                    'name': bot_info.get('first_name'),
                    'username': bot_info.get('username'),
                    'can_join_groups': bot_info.get('can_join_groups'),
                    'can_read_all_group_messages': bot_info.get('can_read_all_group_messages')
                }
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to connect. Check TELEGRAM_BOT_TOKEN.'
            }), 401
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
