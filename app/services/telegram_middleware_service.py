"""
Telegram Bot Middleware Service for SmartXDR
Simple polling-based integration with SmartXDR API

Advantages over Teams:
- Works with personal accounts (no organization required)
- Free and easy to setup
- No Azure configuration needed
- Just need a bot token from @BotFather

Architecture:
Telegram <-- Bot API (Long Polling) --> Middleware --> SmartXDR API
"""

import os
import time
import logging
import threading
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('TelegramMiddleware')


@dataclass
class TelegramConfig:
    """Configuration for Telegram Bot Middleware"""
    bot_token: str = field(default_factory=lambda: os.getenv('TELEGRAM_BOT_TOKEN', ''))
    allowed_chat_ids: str = field(default_factory=lambda: os.getenv('TELEGRAM_ALLOWED_CHATS', ''))
    polling_timeout: int = field(default_factory=lambda: int(os.getenv('TELEGRAM_POLLING_TIMEOUT', '30')))
    smartxdr_api_url: str = field(default_factory=lambda: os.getenv('SMARTXDR_API_URL', 'http://localhost:8080/api/ai/ask'))
    
    def validate(self) -> tuple[bool, str]:
        """Validate configuration"""
        if not self.bot_token:
            return False, "TELEGRAM_BOT_TOKEN is required. Get it from @BotFather on Telegram."
        return True, "Configuration valid"
    
    def get_allowed_chats(self) -> List[int]:
        """Get list of allowed chat IDs (empty = allow all)"""
        if not self.allowed_chat_ids:
            return []
        try:
            return [int(x.strip()) for x in self.allowed_chat_ids.split(',') if x.strip()]
        except ValueError:
            return []


class TelegramMiddlewareService:
    """
    Telegram Bot Middleware using Long Polling
    
    Features:
    - Simple setup (just need bot token from @BotFather)
    - Works with any Telegram account
    - Supports private chats and groups
    - Long polling (efficient, no webhooks needed)
    - Typing indicator support
    - Markdown formatting
    """
    
    TELEGRAM_API = "https://api.telegram.org/bot"
    
    def __init__(self, config: Optional[TelegramConfig] = None):
        self.config = config or TelegramConfig()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_update_id = 0
        self._bot_info: Optional[Dict] = None
        self._stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'messages_replied': 0,
            'errors': 0,
            'started_at': None,
            'last_poll': None
        }
        self._custom_handler: Optional[Callable[[str], str]] = None
    
    def _api_url(self, method: str) -> str:
        """Build Telegram API URL"""
        return f"{self.TELEGRAM_API}{self.config.bot_token}/{method}"
    
    def _call_api(self, method: str, data: dict = None, timeout: int = 30) -> Optional[dict]:
        """Call Telegram Bot API"""
        try:
            url = self._api_url(method)
            if data:
                response = requests.post(url, json=data, timeout=timeout)
            else:
                response = requests.get(url, timeout=timeout)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    return result.get('result')
                else:
                    logger.error(f"Telegram API error: {result.get('description')}")
            else:
                logger.error(f"Telegram API HTTP {response.status_code}: {response.text[:200]}")
            return None
        except requests.exceptions.Timeout:
            # Timeout is expected for long polling
            return None
        except Exception as e:
            logger.error(f"Telegram API error: {e}")
            self._stats['errors'] += 1
            return None
    
    def get_bot_info(self) -> Optional[Dict]:
        """Get bot information and verify token"""
        result = self._call_api('getMe')
        if result:
            self._bot_info = result
            logger.info(f"✅ Bot connected: @{result.get('username')}")
        return result
    
    def send_message(
        self, 
        chat_id: int, 
        text: str, 
        reply_to_message_id: int = None,
        parse_mode: str = 'Markdown'
    ) -> bool:
        """Send message to a chat"""
        # Split long messages (Telegram limit: 4096 chars)
        max_length = 4000
        messages = [text[i:i+max_length] for i in range(0, len(text), max_length)]
        
        success = True
        for i, msg in enumerate(messages):
            data = {
                'chat_id': chat_id,
                'text': msg,
                'parse_mode': parse_mode
            }
            # Only reply to original message for first chunk
            if reply_to_message_id and i == 0:
                data['reply_to_message_id'] = reply_to_message_id
            
            result = self._call_api('sendMessage', data)
            if not result:
                # Try without parse_mode if markdown fails
                data['parse_mode'] = None
                result = self._call_api('sendMessage', data)
                if not result:
                    success = False
        
        return success
    
    def send_typing_action(self, chat_id: int) -> None:
        """Show typing indicator"""
        self._call_api('sendChatAction', {
            'chat_id': chat_id,
            'action': 'typing'
        })
    
    def _is_allowed_chat(self, chat_id: int) -> bool:
        """Check if chat is authorized"""
        allowed = self.config.get_allowed_chats()
        if not allowed:
            return True  # Allow all if not configured
        return chat_id in allowed
    
    def _call_smartxdr_api(self, query: str) -> str:
        """Send query to SmartXDR API"""
        try:
            payload = {"query": query}
            response = requests.post(
                self.config.smartxdr_api_url,
                json=payload,
                verify=False,  # For self-signed certs
                timeout=120  # 2 minutes for complex queries
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    answer = data.get('answer', 'Đã xử lý nhưng không có nội dung.')
                    
                    # Add sources info if available
                    sources = data.get('sources', [])
                    if sources:
                        answer += f"\n\n📚 _Retrieved {len(sources)} sources_"
                    
                    return answer
                else:
                    return f"⚠️ Error: {data.get('message', 'Unknown error')}"
            elif response.status_code == 429:
                return "⏳ Rate limit exceeded. Please try again later."
            else:
                return f"⚠️ API Error: HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            return "⏱️ Request timeout. The query is complex, please try again."
        except requests.exceptions.ConnectionError:
            return "🔌 Cannot connect to SmartXDR API. Is the server running?"
        except Exception as e:
            logger.error(f"SmartXDR API error: {e}")
            return f"❌ Error: {str(e)}"
    
    def _handle_command(self, message: Dict) -> Optional[str]:
        """Handle bot commands"""
        text = message.get('text', '')
        chat_id = message['chat']['id']
        chat_type = message['chat'].get('type', 'private')
        
        if text == '/start':
            bot_name = self._bot_info.get('first_name', 'SmartXDR') if self._bot_info else 'SmartXDR'
            return (
                f"👋 *Welcome to {bot_name}!*\n\n"
                "I'm your AI-powered security assistant.\n\n"
                "*How to use:*\n"
                "Just send me any security question!\n\n"
                "*Examples:*\n"
                "• `What is the IP of Suricata?`\n"
                "• `Show me MITRE ATT&CK for T1059`\n"
                "• `Explain SQL injection attack`\n"
                "• `How to investigate phishing?`\n\n"
                f"💡 Your Chat ID: `{chat_id}`"
            )
        
        elif text == '/help':
            return (
                "🔍 *SmartXDR Bot Help*\n\n"
                "*Commands:*\n"
                "/start - Welcome message\n"
                "/help - This help\n"
                "/status - Bot status\n"
                "/chatid - Get your chat ID\n\n"
                "*Usage:*\n"
                "Send any security question in natural language.\n\n"
                "*Tips:*\n"
                "• Be specific in your questions\n"
                "• Include IPs, IDs, or technique names\n"
                "• Ask about MITRE ATT&CK techniques\n"
                "• Query your SOC infrastructure"
            )
        
        elif text == '/status':
            uptime = "N/A"
            if self._stats['started_at']:
                start = datetime.fromisoformat(self._stats['started_at'])
                uptime = str(datetime.now() - start).split('.')[0]
            
            return (
                "📊 *Bot Status*\n\n"
                f"🤖 Bot: @{self._bot_info.get('username', 'N/A') if self._bot_info else 'N/A'}\n"
                f"⏱️ Uptime: {uptime}\n"
                f"📨 Messages received: {self._stats['messages_received']}\n"
                f"✅ Messages processed: {self._stats['messages_processed']}\n"
                f"📤 Replies sent: {self._stats['messages_replied']}\n"
                f"❌ Errors: {self._stats['errors']}\n\n"
                f"🔗 API: `{self.config.smartxdr_api_url}`"
            )
        
        elif text == '/chatid':
            return f"🆔 Your Chat ID: `{chat_id}`\n\nChat Type: {chat_type}"
        
        return None  # Not a command
    
    def _process_message(self, message: Dict) -> None:
        """Process incoming message"""
        try:
            chat_id = message['chat']['id']
            message_id = message['message_id']
            text = message.get('text', '')
            
            # Get sender info
            user = message.get('from', {})
            username = user.get('username') or user.get('first_name', 'Unknown')
            
            # Skip empty messages
            if not text:
                return
            
            # Check authorization
            if not self._is_allowed_chat(chat_id):
                logger.warning(f"⛔ Unauthorized: {username} (chat: {chat_id})")
                self.send_message(
                    chat_id, 
                    "⛔ *Unauthorized*\n\nYou are not authorized to use this bot.\n"
                    f"Your Chat ID: `{chat_id}`"
                )
                return
            
            # Handle commands first
            command_response = self._handle_command(message)
            if command_response:
                self.send_message(chat_id, command_response, message_id)
                return
            
            # Regular message - process with AI
            self._stats['messages_received'] += 1
            logger.info(f"📩 [{username}]: {text[:80]}{'...' if len(text) > 80 else ''}")
            
            # Show typing indicator
            self.send_typing_action(chat_id)
            
            # Get AI response
            if self._custom_handler:
                response = self._custom_handler(text)
            else:
                response = self._call_smartxdr_api(text)
            
            self._stats['messages_processed'] += 1
            
            # Send reply
            if self.send_message(chat_id, response, message_id):
                self._stats['messages_replied'] += 1
                logger.info(f"✅ Replied to {username}")
            else:
                self._stats['errors'] += 1
                logger.error(f"❌ Failed to reply to {username}")
                
        except Exception as e:
            self._stats['errors'] += 1
            logger.error(f"❌ Error processing message: {e}")
    
    def _poll_updates(self) -> None:
        """Poll for new updates using long polling"""
        try:
            params = {
                'offset': self._last_update_id + 1,
                'timeout': self.config.polling_timeout,
                'allowed_updates': ['message']
            }
            
            response = requests.get(
                self._api_url('getUpdates'),
                params=params,
                timeout=self.config.polling_timeout + 5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    updates = data.get('result', [])
                    for update in updates:
                        self._last_update_id = update['update_id']
                        if 'message' in update:
                            self._process_message(update['message'])
                    
                    self._stats['last_poll'] = datetime.now().isoformat()
                    
        except requests.exceptions.Timeout:
            pass  # Normal for long polling
        except Exception as e:
            logger.error(f"❌ Polling error: {e}")
            self._stats['errors'] += 1
            time.sleep(5)  # Wait before retry
    
    def _run_loop(self) -> None:
        """Main polling loop"""
        logger.info("🔄 Starting polling loop...")
        
        while self._running:
            self._poll_updates()
    
    def start(self, blocking: bool = False) -> bool:
        """
        Start the middleware service
        
        Args:
            blocking: If True, blocks main thread. If False, runs in background.
        """
        # Validate config
        valid, message = self.config.validate()
        if not valid:
            logger.error(f"❌ Config error: {message}")
            return False
        
        # Verify bot token
        if not self.get_bot_info():
            logger.error("❌ Failed to connect to Telegram. Check your bot token.")
            return False
        
        self._running = True
        self._stats['started_at'] = datetime.now().isoformat()
        
        logger.info("=" * 50)
        logger.info(f"🤖 Bot: @{self._bot_info.get('username')}")
        logger.info(f"📍 API: {self.config.smartxdr_api_url}")
        allowed = self.config.get_allowed_chats()
        if allowed:
            logger.info(f"🔒 Allowed chats: {allowed}")
        else:
            logger.info("🔓 All chats allowed (no whitelist)")
        logger.info("=" * 50)
        
        if blocking:
            try:
                self._run_loop()
            except KeyboardInterrupt:
                logger.info("🛑 Interrupted by user")
                self.stop()
        else:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        
        return True
    
    def stop(self) -> None:
        """Stop the middleware service"""
        logger.info("🛑 Stopping Telegram middleware...")
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("✅ Stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get middleware statistics"""
        return {
            **self._stats,
            'running': self._running,
            'bot': self._bot_info.get('username') if self._bot_info else None
        }
    
    def set_custom_handler(self, handler: Callable[[str], str]) -> None:
        """Set custom message handler"""
        self._custom_handler = handler
        logger.info("✅ Custom handler set")


# Singleton
_instance: Optional[TelegramMiddlewareService] = None


def get_telegram_middleware() -> TelegramMiddlewareService:
    """Get or create singleton instance"""
    global _instance
    if _instance is None:
        _instance = TelegramMiddlewareService()
    return _instance
