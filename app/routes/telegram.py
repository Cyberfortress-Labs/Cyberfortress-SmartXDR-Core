"""
Telegram Bot API Routes
Provides REST endpoints to manage the Telegram middleware service
Supports both Long Polling and Webhook modes
"""
import os
import hmac
import hashlib
from flask import Blueprint, jsonify, request
from app.services.telegram_middleware_service import TelegramMiddlewareService

telegram_bp = Blueprint('telegram', __name__)

# Singleton instance - initialized once at module load
_middleware_instance = None
_initialized = False

def get_telegram_middleware() -> TelegramMiddlewareService:
    """Get or create singleton middleware instance"""
    global _middleware_instance, _initialized
    if _middleware_instance is None:
        _middleware_instance = TelegramMiddlewareService()
        # Pre-fetch bot info on first init
        _middleware_instance.get_bot_info()
        _initialized = True
        print(f"[Telegram] Middleware initialized, bot: @{_middleware_instance._bot_info.get('username') if _middleware_instance._bot_info else 'unknown'}")
        
        # Auto-start polling if webhook is disabled
        webhook_enabled = os.getenv('TELEGRAM_WEBHOOK_ENABLED', 'true').lower() == 'true'
        bot_enabled = os.getenv('TELEGRAM_BOT_ENABLED', 'true').lower() == 'true'
        
        if bot_enabled and not webhook_enabled:
            print("[Telegram] Auto-starting polling mode (webhook disabled)...")
            _middleware_instance.start_polling(threaded=True)
    return _middleware_instance


# ============================================================
# Webhook Endpoint (Real-time, recommended with Cloudflare Tunnel)
# ============================================================

@telegram_bp.route('/webhook', methods=['POST'])
def telegram_webhook():
    """
    Telegram Webhook endpoint - receives updates from Telegram servers
    
    This is called by Telegram when a new message arrives.
    Much more efficient than polling - no constant requests!
    
    Setup:
        1. Start Cloudflare Tunnel: cloudflared tunnel --url http://localhost:8080
        2. Set webhook: POST /api/telegram/webhook/set with {"url": "https://your-tunnel.trycloudflare.com"}
    """
    try:
        update = request.get_json()
        if not update:
            return jsonify({'error': 'No data'}), 400
        
        # Debug logging
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        chat_type = message.get("chat", {}).get("type")
        text = message.get("text", "")[:50]
        user = message.get("from", {})
        print(f"[Webhook] Chat: {chat_id} ({chat_type}) | From: {user.get('username', user.get('first_name', 'unknown'))} | Text: {text}")
        
        # Get middleware and process update
        mw = get_telegram_middleware()
        
        # Process the update (same logic as polling)
        mw.process_update(update)
        
        # Telegram expects 200 OK
        return '', 200
        
    except Exception as e:
        # Log error but return 200 to prevent Telegram from retrying
        print(f"Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return '', 200


@telegram_bp.route('/webhook/set', methods=['POST'])
def set_webhook():
    """
    Set Telegram webhook URL
    
    Request body:
        {
            "url": "https://your-tunnel.trycloudflare.com"
        }
    
    The webhook will be set to: {url}/api/telegram/webhook
    """
    try:
        data = request.get_json() or {}
        base_url = data.get('url', '').rstrip('/')
        
        if not base_url:
            return jsonify({
                'status': 'error',
                'message': 'URL is required. Example: {"url": "https://abc123.trycloudflare.com"}'
            }), 400
        
        webhook_url = f"{base_url}/api/telegram/webhook"
        
        mw = get_telegram_middleware()
        
        # Call Telegram API to set webhook
        import requests
        response = requests.post(
            f"https://api.telegram.org/bot{mw.bot_token}/setWebhook",
            json={
                "url": webhook_url,
                "allowed_updates": ["message"],
                "drop_pending_updates": True  # Don't process old messages
            },
            timeout=10
        )
        
        result = response.json()
        
        if result.get('ok'):
            # Stop polling if running (webhook and polling are mutually exclusive)
            if mw.is_running():
                mw.stop_polling()
            
            return jsonify({
                'status': 'success',
                'message': 'Webhook set successfully!',
                'webhook_url': webhook_url,
                'telegram_response': result
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': result.get('description', 'Failed to set webhook'),
                'telegram_response': result
            }), 400
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@telegram_bp.route('/webhook/delete', methods=['POST'])
def delete_webhook():
    """Delete Telegram webhook (switch back to polling mode)"""
    try:
        mw = get_telegram_middleware()
        
        import requests
        response = requests.post(
            f"https://api.telegram.org/bot{mw.bot_token}/deleteWebhook",
            json={"drop_pending_updates": True},
            timeout=10
        )
        
        result = response.json()
        
        if result.get('ok'):
            return jsonify({
                'status': 'success',
                'message': 'Webhook deleted. You can now use polling mode.',
                'telegram_response': result
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': result.get('description', 'Failed to delete webhook'),
                'telegram_response': result
            }), 400
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@telegram_bp.route('/webhook/info', methods=['GET'])
def get_webhook_info():
    """Get current webhook info from Telegram"""
    try:
        mw = get_telegram_middleware()
        
        import requests
        response = requests.get(
            f"https://api.telegram.org/bot{mw.bot_token}/getWebhookInfo",
            timeout=10
        )
        
        result = response.json()
        
        if result.get('ok'):
            info = result.get('result', {})
            return jsonify({
                'status': 'success',
                'webhook': {
                    'url': info.get('url') or '(not set)',
                    'has_custom_certificate': info.get('has_custom_certificate'),
                    'pending_update_count': info.get('pending_update_count'),
                    'last_error_date': info.get('last_error_date'),
                    'last_error_message': info.get('last_error_message'),
                    'max_connections': info.get('max_connections'),
                    'allowed_updates': info.get('allowed_updates')
                },
                'mode': 'webhook' if info.get('url') else 'polling'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': result.get('description', 'Failed to get webhook info')
            }), 400
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ============================================================
# Polling Mode Endpoints (fallback when no public URL)
# ============================================================


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
