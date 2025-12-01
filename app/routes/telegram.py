"""
Telegram Bot API Routes
Provides REST endpoints to manage the Telegram middleware service
"""
import os
from flask import Blueprint, jsonify
from app.services.telegram_middleware_service import TelegramMiddlewareService

telegram_bp = Blueprint('telegram', __name__)

# Singleton instance
_middleware_instance = None

def get_telegram_middleware() -> TelegramMiddlewareService:
    """Get or create singleton middleware instance"""
    global _middleware_instance
    if _middleware_instance is None:
        _middleware_instance = TelegramMiddlewareService()
    return _middleware_instance


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
        
        if mw.is_running():
            return jsonify({
                'status': 'warning',
                'message': 'Middleware is already running'
            }), 200
        
        mw.start_polling(threaded=True)
        
        return jsonify({
            'status': 'success',
            'message': 'Telegram middleware started',
            'bot': mw._bot_info.get('username') if mw._bot_info else None
        }), 200
            
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
        mw.stop_polling()
        
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
        mw = get_telegram_middleware()
        
        # Mask token
        token = mw.bot_token
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
                'bot_token_set': bool(mw.bot_token),
                'bot_token_masked': masked,
                'allowed_chats': list(mw.allowed_chats) if mw.allowed_chats else 'all',
                'polling_timeout': mw.polling_timeout,
                'smartxdr_api_url': mw.smartxdr_api_url
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
