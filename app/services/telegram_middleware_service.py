"""
Telegram Middleware Service for SmartXDR Integration
Uses long polling to receive messages and forwards to SmartXDR API
"""

import os
import time
import threading
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from collections import defaultdict
import html
import re

from app.utils.logger import setup_logger
from app.config import ALERT_TIME_WINDOW

logger = setup_logger("telegram_middleware")


class TelegramMiddlewareService:
    """
    Telegram Bot middleware service that:
    - Uses long polling to receive messages
    - Forwards queries to SmartXDR /api/ai/ask endpoint
    - Returns AI responses back to Telegram
    - Supports whitelist, rate limiting, and auto-block for spam protection
    """
    
    def __init__(self, bot_token: str = None, smartxdr_api_url: str = None, smartxdr_api_key: str = None):
        """
        Initialize Telegram middleware service
        
        Args:
            bot_token: Telegram Bot token from BotFather
            smartxdr_api_url: SmartXDR API base URL
            smartxdr_api_key: SmartXDR API key for authentication
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.smartxdr_api_url = smartxdr_api_url or os.getenv("SMARTXDR_API_URL", "http://localhost:8080")
        self.smartxdr_api_key = smartxdr_api_key or os.getenv("SMARTXDR_MASTER_API_KEY", "")
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"
        
        # HTTP Session for connection reuse (performance optimization)
        self._session = requests.Session()
        if self.smartxdr_api_key:
            self._session.headers.update({"X-API-Key": self.smartxdr_api_key})
        
        # Telegram session for faster API calls
        self._tg_session = requests.Session()
        
        # Polling settings
        self.polling_timeout = int(os.getenv("TELEGRAM_POLLING_TIMEOUT", "30"))
        self.last_update_id = 0
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        
        # Whitelist - comma-separated chat IDs (positive for users, negative for groups)
        allowed_chats = os.getenv("TELEGRAM_ALLOWED_CHATS", "")
        self.allowed_chats: set = set()
        if allowed_chats:
            for chat_id in allowed_chats.split(","):
                chat_id = chat_id.strip()
                if chat_id:
                    try:
                        self.allowed_chats.add(int(chat_id))
                    except ValueError:
                        logger.warning(f"Invalid chat ID in whitelist: {chat_id}")
        
        # Rate limiting settings
        self.rate_limit_messages = int(os.getenv("TELEGRAM_RATE_LIMIT_MESSAGES", "10"))
        self.rate_limit_window = int(os.getenv("TELEGRAM_RATE_LIMIT_WINDOW", "60"))  # seconds
        self.auto_block_threshold = int(os.getenv("TELEGRAM_AUTO_BLOCK_THRESHOLD", "20"))
        self.auto_block_duration = int(os.getenv("TELEGRAM_AUTO_BLOCK_DURATION", "300"))  # 5 minutes
        
        # Rate limiting tracking
        self._message_timestamps: Dict[int, List[datetime]] = defaultdict(list)
        self._blocked_users: Dict[int, datetime] = {}  # user_id -> unblock_time
        
        # Stats tracking
        self._stats = {
            "messages_received": 0,
            "messages_processed": 0,
            "messages_blocked": 0,
            "errors": 0,
            "start_time": None
        }
        
        # Bot info cache
        self._bot_info: Optional[Dict[str, Any]] = None
        
        # Custom message handler (optional)
        self._custom_handler: Optional[Callable] = None
                
        logger.info(f"TelegramMiddlewareService initialized")
        logger.info(f"SmartXDR API URL: {self.smartxdr_api_url}")
        logger.info(f"SmartXDR API Key: {'Configured ✓' if self.smartxdr_api_key else 'NOT SET ⚠️'}")
        logger.info(f"Allowed chats: {self.allowed_chats if self.allowed_chats else 'ALL (no whitelist)'}")
        logger.info(f"Rate limit: {self.rate_limit_messages} messages per {self.rate_limit_window}s")
    
    # ========== Bot Info Methods ==========
    
    def get_bot_info(self) -> Optional[Dict[str, Any]]:
        """
        Get bot information from Telegram API (getMe)
        Caches result for efficiency
        
        Returns:
            Dict with bot info (id, first_name, username, etc.) or None on error
        """
        if self._bot_info:
            return self._bot_info
        
        try:
            response = self._tg_session.get(
                f"{self.api_base}/getMe",
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("ok"):
                self._bot_info = data.get("result")
                logger.info(f"Bot info retrieved: @{self._bot_info.get('username')}")
                return self._bot_info
            else:
                logger.error(f"Failed to get bot info: {data.get('description')}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting bot info: {e}")
            return None
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to both Telegram and SmartXDR APIs
        
        Returns:
            Dict with connection test results
        """
        result = {
            "telegram": {"connected": False, "bot_info": None},
            "smartxdr": {"connected": False, "url": self.smartxdr_api_url}
        }
        
        # Test Telegram connection
        bot_info = self.get_bot_info()
        if bot_info:
            result["telegram"]["connected"] = True
            result["telegram"]["bot_info"] = {
                "id": bot_info.get("id"),
                "username": bot_info.get("username"),
                "first_name": bot_info.get("first_name")
            }
        
        # Test SmartXDR connection
        try:
            response = requests.get(
                f"{self.smartxdr_api_url}/health",
                timeout=5
            )
            if response.status_code == 200:
                result["smartxdr"]["connected"] = True
        except Exception as e:
            # Try the AI endpoint directly
            try:
                response = requests.post(
                    f"{self.smartxdr_api_url}/api/ai/ask",
                    json={"query": "ping"},
                    timeout=10
                )
                if response.status_code in [200, 400, 422]:  # Any response means API is up
                    result["smartxdr"]["connected"] = True
            except Exception as e2:
                logger.warning(f"SmartXDR API not reachable: {e2}")
        
        return result
    
    # ========== Whitelist & Rate Limiting ==========
    
    def is_chat_allowed(self, chat_id: int) -> bool:
        """Check if chat is in whitelist (if whitelist is enabled)"""
        if not self.allowed_chats:
            return True  # No whitelist = allow all
        return chat_id in self.allowed_chats
    
    def add_to_whitelist(self, chat_id: int) -> bool:
        """Add a chat ID to the whitelist"""
        self.allowed_chats.add(chat_id)
        logger.info(f"Added chat {chat_id} to whitelist")
        return True
    
    def remove_from_whitelist(self, chat_id: int) -> bool:
        """Remove a chat ID from the whitelist"""
        if chat_id in self.allowed_chats:
            self.allowed_chats.remove(chat_id)
            logger.info(f"Removed chat {chat_id} from whitelist")
            return True
        return False
    
    def is_rate_limited(self, user_id: int) -> bool:
        """
        Check if user is rate limited
        Also handles auto-blocking for spam
        
        Returns:
            True if user should be blocked, False if allowed
        """
        now = datetime.now()
        
        # Check if user is auto-blocked
        if user_id in self._blocked_users:
            if now < self._blocked_users[user_id]:
                return True  # Still blocked
            else:
                # Unblock expired
                del self._blocked_users[user_id]
                logger.info(f"User {user_id} auto-block expired")
        
        # Clean old timestamps
        window_start = now - timedelta(seconds=self.rate_limit_window)
        self._message_timestamps[user_id] = [
            ts for ts in self._message_timestamps[user_id] 
            if ts > window_start
        ]
        
        # Check rate limit
        msg_count = len(self._message_timestamps[user_id])
        
        # Auto-block if exceeds threshold (severe spam)
        if msg_count >= self.auto_block_threshold:
            self._blocked_users[user_id] = now + timedelta(seconds=self.auto_block_duration)
            logger.warning(f"User {user_id} auto-blocked for {self.auto_block_duration}s (spam: {msg_count} msgs)")
            return True
        
        # Normal rate limit check
        if msg_count >= self.rate_limit_messages:
            return True
        
        # Record this message
        self._message_timestamps[user_id].append(now)
        return False
    
    def get_rate_limit_info(self, user_id: int) -> Dict[str, Any]:
        """Get rate limit info for a user"""
        now = datetime.now()
        window_start = now - timedelta(seconds=self.rate_limit_window)
        
        recent_msgs = [
            ts for ts in self._message_timestamps.get(user_id, [])
            if ts > window_start
        ]
        
        blocked_until = self._blocked_users.get(user_id)
        
        return {
            "user_id": user_id,
            "messages_in_window": len(recent_msgs),
            "rate_limit": self.rate_limit_messages,
            "window_seconds": self.rate_limit_window,
            "is_blocked": blocked_until is not None and now < blocked_until,
            "blocked_until": blocked_until.isoformat() if blocked_until and now < blocked_until else None
        }
    
    # ========== Telegram API Methods ==========
    
    def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML", 
                     reply_to_message_id: int = None) -> Optional[Dict]:
        """
        Send a message to a Telegram chat
        
        Args:
            chat_id: Target chat ID
            text: Message text
            parse_mode: HTML or Markdown
            reply_to_message_id: Optional message ID to reply to
            
        Returns:
            API response dict or None on error
        """
        try:
            # Telegram has a 4096 character limit
            if len(text) > 4096:
                # Split into multiple messages
                chunks = self._split_message(text, 4096)
                result = None
                for chunk in chunks:
                    result = self._send_single_message(chat_id, chunk, parse_mode, reply_to_message_id)
                    reply_to_message_id = None  # Only reply to first message
                return result
            else:
                return self._send_single_message(chat_id, text, parse_mode, reply_to_message_id)
                
        except Exception as e:
            logger.error(f"Error sending message to {chat_id}: {e}")
            return None
    
    def send_document(self, chat_id: int, file_path: str, caption: Optional[str] = None,
                     reply_to_message_id: Optional[int] = None) -> Optional[Dict]:
        """Send a document/file to a chat"""
        try:
            url = f"{self.api_base}/sendDocument"
            
            with open(file_path, 'rb') as f:
                files = {'document': f}
                data: Dict[str, Any] = {'chat_id': chat_id}
                
                if caption:
                    data['caption'] = caption
                    data['parse_mode'] = 'HTML'
                
                if reply_to_message_id:
                    data['reply_to_message_id'] = reply_to_message_id
                
                response = self._tg_session.post(url, files=files, data=data, timeout=60)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error sending document to {chat_id}: {e}")
            return None
    
    def _send_single_message(self, chat_id: int, text: str, parse_mode: str = "HTML",
                             reply_to_message_id: int = None) -> Optional[Dict]:
        """Send a single message (internal)"""
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        
        try:
            response = self._tg_session.post(
                f"{self.api_base}/sendMessage",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # If HTML parsing fails, try without parse_mode
            if "can't parse" in str(e).lower() or response.status_code == 400:
                payload["parse_mode"] = None
                payload["text"] = self._strip_html(text)
                response = self._tg_session.post(
                    f"{self.api_base}/sendMessage",
                    json=payload,
                    timeout=30
                )
                return response.json()
            raise
    
    def _split_message(self, text: str, max_length: int) -> List[str]:
        """Split long message into chunks"""
        chunks = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break
            
            # Find a good split point
            split_point = text.rfind('\n', 0, max_length)
            if split_point == -1:
                split_point = text.rfind(' ', 0, max_length)
            if split_point == -1:
                split_point = max_length
            
            chunks.append(text[:split_point])
            text = text[split_point:].lstrip()
        
        return chunks
    
    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text"""
        return re.sub(r'<[^>]+>', '', text)
    
    def send_typing_action(self, chat_id: int) -> bool:
        """Send typing indicator to chat"""
        try:
            self._tg_session.post(
                f"{self.api_base}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
                timeout=5
            )
            return True
        except:
            return False
    
    # ========== Polling & Message Handling ==========
    
    def get_updates(self, offset: int = None, timeout: int = None) -> List[Dict]:
        """
        Get updates from Telegram (long polling)
        
        Args:
            offset: Identifier of the first update to be returned
            timeout: Timeout in seconds for long polling
            
        Returns:
            List of update objects
        """
        params = {
            "timeout": timeout or self.polling_timeout,
            "allowed_updates": ["message"]
        }
        
        if offset:
            params["offset"] = offset
        
        try:
            response = self._tg_session.get(
                f"{self.api_base}/getUpdates",
                params=params,
                timeout=params["timeout"] + 10  # Add buffer for network
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("ok"):
                return data.get("result", [])
            else:
                logger.error(f"getUpdates error: {data.get('description')}")
                return []
                
        except requests.exceptions.Timeout:
            return []  # Normal for long polling
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
            return []
    
    def process_update(self, update: Dict) -> None:
        """
        Process a single update from Telegram
        
        Args:
            update: Update object from Telegram API
        """
        self._stats["messages_received"] += 1
        
        message = update.get("message")
        if not message:
            return
        
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        chat_type = chat.get("type")  # 'private', 'group', 'supergroup', 'channel'
        user_id = message.get("from", {}).get("id")
        text = message.get("text", "")
        message_id = message.get("message_id")
        
        if not chat_id or not text:
            return
        
        # Get user info for logging
        user = message.get("from", {})
        username = user.get("username", "unknown")
        first_name = user.get("first_name", "unknown")
        
        # For groups: only respond if bot is mentioned or replied to
        is_group = chat_type in ("group", "supergroup")
        if is_group:
            # Get bot username - fetch if not cached
            if not self._bot_info:
                self.get_bot_info()
            bot_username = self._bot_info.get("username", "smartxdr_bot") if self._bot_info else "smartxdr_bot"
            bot_id = self._bot_info.get("id") if self._bot_info else None
            
            is_mentioned = f"@{bot_username}" in text.lower() if bot_username else False
            is_reply_to_bot = False
            
            # Check if this is a reply to bot's message
            reply_to = message.get("reply_to_message", {})
            if reply_to and bot_id:
                reply_from = reply_to.get("from", {})
                if reply_from.get("id") == bot_id:
                    is_reply_to_bot = True
            
            # Skip if not mentioned and not replied to (except commands)
            if not is_mentioned and not is_reply_to_bot and not text.startswith("/"):
                logger.debug(f"Skipping group message (not mentioned): {text[:30]}...")
                return
            
            # Remove bot mention from text for cleaner processing
            if is_mentioned and bot_username:
                import re
                text = re.sub(rf'@{bot_username}\s*', '', text, flags=re.IGNORECASE).strip()
                
            logger.info(f"Group message (mentioned={is_mentioned}, reply={is_reply_to_bot}): {text[:50]}...")
        
        logger.info(f"Message from @{username} ({first_name}) in chat {chat_id}: {text[:50]}...")
        
        # Check whitelist
        if not self.is_chat_allowed(chat_id):
            logger.warning(f"Message from non-whitelisted chat {chat_id} (user: @{username})")
            self._stats["messages_blocked"] += 1
            # Optionally notify user they're not authorized
            self.send_message(
                chat_id,
                "⛔ <b>Access Denied</b>\n\n"
                "You are not authorized to use this bot.\n"
                f"Your Chat ID: <code>{chat_id}</code>\n\n"
                "Please contact the administrator.",
                reply_to_message_id=message_id
            )
            return
        
        # Check rate limit (use chat_id for groups to allow multiple users)
        rate_limit_id = chat_id if is_group else user_id
        if self.is_rate_limited(rate_limit_id):
            logger.warning(f"Rate limited {'chat' if is_group else 'user'} {rate_limit_id}")
            self._stats["messages_blocked"] += 1
            rate_info = self.get_rate_limit_info(rate_limit_id)
            
            if rate_info.get("is_blocked"):
                self.send_message(
                    chat_id,
                    "🚫 <b>Temporarily Blocked</b>\n\n"
                    "You have been temporarily blocked due to excessive requests.\n"
                    f"Try again after: {rate_info.get('blocked_until', 'a few minutes')}",
                    reply_to_message_id=message_id
                )
            else:
                self.send_message(
                    chat_id,
                    "⏳ <b>Rate Limited</b>\n\n"
                    f"You have sent too many messages. Please wait a moment.\n"
                    f"Limit: {self.rate_limit_messages} messages per {self.rate_limit_window} seconds.",
                    reply_to_message_id=message_id
                )
            return
        
        # Handle commands
        if text.startswith("/"):
            self._handle_command(text, chat_id, message_id, user)
            return
        
        # Process query through SmartXDR
        self._process_smartxdr_query(text, chat_id, message_id, user)
    
    def _handle_command(self, text: str, chat_id: int, message_id: int, user: Dict) -> None:
        """Handle bot commands"""
        command = text.split()[0].lower()
        
        if command == "/start":
            self.send_message(
                chat_id,
                "🛡️ <b>Welcome to SmartXDR Bot!</b>\n\n"
                "I can help you analyze security threats and get AI-powered insights.\n\n"
                "<b>How to use:</b>\n"
                "Simply send me your security-related question and I'll analyze it using SmartXDR AI.\n\n"
                "<b>Commands:</b>\n"
                "/help - Show this help message\n"
                "/status - Check bot and API status\n"
                "/stats - Show usage statistics\n"
                "/summary - Summarize recent ML-classified alerts\n"
                "/sumlogs - Analyze ML logs with AI\n"
                "/id - Show your chat ID\n\n"
                "🔒 This bot is protected by whitelist and rate limiting.",
                reply_to_message_id=message_id
            )
        
        elif command == "/help":
            self.send_message(
                chat_id,
                "📖 <b>SmartXDR Bot Help</b>\n\n"
                "<b>What I can do:</b>\n"
                "• Analyze security alerts and logs\n"
                "• Map threats to MITRE ATT&CK framework\n"
                "• Provide incident response recommendations\n"
                "• Generate threat intelligence reports\n"
                "• Summarize recent ML-classified alerts\n\n"
                "<b>Example queries:</b>\n"
                "• <i>Analyze this Suricata alert: ET MALWARE Win32/Emotet...</i>\n"
                "• <i>What is the MITRE technique for credential dumping?</i>\n"
                "• <i>How to respond to a ransomware incident?</i>\n\n"
                "<b>Alert Summary Command:</b>\n"
                "• <code>/summary</code> - Last 7 days, all indices\n"
                "• <code>/summary --time 24h</code> - Last 24 hours\n"
                "• <code>/summary --time 3d</code> - Last 3 days\n"
                "• <code>/summary --time 7d --ai</code> - Include AI analysis\n"
                "• <code>/summary --time 7d --index suricata,zeek</code> - Custom filter\n\n"
                "<b>ML Logs Analysis:</b>\n"
                "• <code>/sumlogs trong 24h gần đây, logs nào có dấu hiệu tấn công? --index *suricata*</code>\n"
                "• <code>/sumlogs liệt kê logs nguy hiểm --time 24h --index all</code>\n"
                "• <code>/sumlogs phân tích logs ERROR --time 7d --severity ERROR,WARNING</code>\n\n"
                "<b>Tips:</b>\n"
                "• Be specific in your questions\n"
                "• Include relevant log data for analysis\n"
                "• Mention the security tool or data source",
                reply_to_message_id=message_id
            )
        
        elif command == "/status":
            connection = self.test_connection()
            telegram_status = "✅ Connected" if connection["telegram"]["connected"] else "❌ Disconnected"
            smartxdr_status = "✅ Connected" if connection["smartxdr"]["connected"] else "❌ Disconnected"
            
            self.send_message(
                chat_id,
                f"📊 <b>Bot Status</b>\n\n"
                f"<b>Telegram API:</b> {telegram_status}\n"
                f"<b>SmartXDR API:</b> {smartxdr_status}\n"
                f"<b>API URL:</b> <code>{self.smartxdr_api_url}</code>\n\n"
                f"<b>Settings:</b>\n"
                f"• Rate Limit: {self.rate_limit_messages} msgs/{self.rate_limit_window}s\n"
                f"• Whitelist: {'Enabled' if self.allowed_chats else 'Disabled'}\n"
                f"• Polling Timeout: {self.polling_timeout}s",
                reply_to_message_id=message_id
            )
        
        elif command == "/summary":
            # Parse command arguments: /summary --time 7d --index suricata,zeek --ai
            args = text.split()[1:]  # Skip /summary
            time_arg = None
            index_arg = None
            include_ai = False
            
            i = 0
            while i < len(args):
                if args[i] == "--time" and i + 1 < len(args):
                    time_arg = args[i + 1]
                    i += 2
                elif args[i] == "--index" and i + 1 < len(args):
                    index_arg = args[i + 1]
                    i += 2
                elif args[i] == "--ai":
                    include_ai = True
                    i += 1
                else:
                    i += 1
            
            # Handle alert summarization (async via threading)
            threading.Thread(
                target=self._handle_alert_summary,
                args=(chat_id, message_id, time_arg, index_arg, include_ai),
                daemon=True
            ).start()
        
        elif command == "/sumlogs":
            # Parse /sumlogs command with natural language + options
            # Format: /sumlogs <question> --time 14d --index *suricata* --severity ERROR,WARNING
            
            # Extract question and options using split
            parts = text.split('--')
            question = parts[0].replace('/sumlogs', '').strip()
            
            # Parse options
            time_arg = "24h"  # Default
            index_arg = "all"  # Default to all indices
            severity_arg = None
            
            for part in parts[1:]:
                part = part.strip()
                if part.startswith('time '):
                    # Extract time value (everything after 'time ')
                    time_arg = part[5:].strip().split()[0]  # Take first token after 'time '
                elif part.startswith('index '):
                    # Extract index pattern (everything after 'index ')
                    index_arg = part[6:].strip().split()[0]  # Take first token after 'index '
                elif part.startswith('severity '):
                    # Extract severity list (everything after 'severity ')
                    severity_arg = part[9:].strip().split()[0]  # Take first token after 'severity '
            
            # Handle async processing
            threading.Thread(
                target=self._handle_sumlogs_analysis,
                args=(chat_id, message_id, question, time_arg, index_arg, severity_arg),
                daemon=True
            ).start()
        
        elif command == "/stats":
            uptime = ""
            if self._stats["start_time"]:
                delta = datetime.now() - self._stats["start_time"]
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime = f"{hours}h {minutes}m {seconds}s"
            
            self.send_message(
                chat_id,
                f"📈 <b>Usage Statistics</b>\n\n"
                f"<b>Messages:</b>\n"
                f"• Received: {self._stats['messages_received']}\n"
                f"• Processed: {self._stats['messages_processed']}\n"
                f"• Blocked: {self._stats['messages_blocked']}\n"
                f"• Errors: {self._stats['errors']}\n\n"
                f"<b>Uptime:</b> {uptime if uptime else 'N/A'}",
                reply_to_message_id=message_id
            )
        
        elif command == "/id":
            chat = {"id": chat_id}
            self.send_message(
                chat_id,
                f"🆔 <b>Your Information</b>\n\n"
                f"<b>User ID:</b> <code>{user.get('id')}</code>\n"
                f"<b>Username:</b> @{user.get('username', 'N/A')}\n"
                f"<b>Chat ID:</b> <code>{chat_id}</code>\n"
                f"<b>Name:</b> {user.get('first_name', '')} {user.get('last_name', '')}",
                reply_to_message_id=message_id
            )
        
        else:
            # Unknown command
            self.send_message(
                chat_id,
                "❓ Unknown command. Use /help to see available commands.",
                reply_to_message_id=message_id
            )
    
    def _process_smartxdr_query(self, query: str, chat_id: int, message_id: int, user: Dict) -> None:
        """
        Send query to SmartXDR API and return response
        
        Args:
            query: User's question/query
            chat_id: Telegram chat ID
            message_id: Original message ID for reply
            user: User info dict
        """
        # Send typing indicator in background (non-blocking)
        threading.Thread(target=self.send_typing_action, args=(chat_id,), daemon=True).start()
        
        start_time = time.time()
        
        try:
            # Send query directly to API
            query_to_send = query
            
            # Call SmartXDR API with original query
            logger.info(f"Sending query to SmartXDR: {query_to_send[:50]}...")
            
            response = self._session.post(
                f"{self.smartxdr_api_url}/api/ai/ask",
                json={"query": query_to_send},
                timeout=60
            )
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", data.get("response", "No response received."))
                
                # Format response for Telegram
                formatted_response = self._format_response(answer)
                
                self.send_message(
                    chat_id,
                    f"🤖 <b>SmartXDR Analysis</b> ({elapsed:.1f}s)\n\n{formatted_response}",
                    reply_to_message_id=message_id
                )
                
                self._stats["messages_processed"] += 1
                logger.info(f"Successfully processed query for @{user.get('username')} in {elapsed:.2f}s")
                
            else:
                error_msg = f"API returned status {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", error_msg)
                except:
                    pass
                
                self.send_message(
                    chat_id,
                    f"⚠️ <b>Error</b>\n\n{html.escape(error_msg)}",
                    reply_to_message_id=message_id
                )
                self._stats["errors"] += 1
                logger.error(f"SmartXDR API error: {error_msg}")
                
        except requests.exceptions.Timeout:
            elapsed = time.time() - start_time
            self.send_message(
                chat_id,
                f"⏱️ <b>Timeout</b>\n\nThe request took too long ({elapsed:.1f}s). Please try again.",
                reply_to_message_id=message_id
            )
            self._stats["errors"] += 1
            logger.error("SmartXDR API timeout")
            
        except requests.exceptions.ConnectionError:
            elapsed = time.time() - start_time
            self.send_message(
                chat_id,
                "🔌 <b>Connection Error</b>\n\n"
                "Cannot connect to SmartXDR API. Please ensure the server is running.",
                reply_to_message_id=message_id
            )
            self._stats["errors"] += 1
            logger.error("SmartXDR API connection error")
            
        except Exception as e:
            elapsed = time.time() - start_time
            self.send_message(
                chat_id,
                f"❌ <b>Error</b>\n\nAn unexpected error occurred: {html.escape(str(e))}",
                reply_to_message_id=message_id
            )
            self._stats["errors"] += 1
            logger.error(f"Unexpected error: {e}")
    
    def _handle_alert_summary(self, chat_id: int, message_id: int, time_arg: str = None, index_arg: str = None, include_ai: bool = False) -> None:
        """
        Handle /summary command - fetch and summarize ML-classified alerts
        Runs asynchronously in background thread
        
        Args:
            chat_id: Telegram chat ID
            message_id: Message ID to reply to
            time_arg: Time window (e.g., "7d", "24h", "60m")
            index_arg: Comma-separated index patterns (e.g., "suricata,zeek")
            include_ai: Include AI analysis (default: False)
        """
        try:
            # Send typing indicator
            self.send_typing_action(chat_id)
            
            # Parse time argument
            time_window_minutes = ALERT_TIME_WINDOW  # Default from config
            if time_arg:
                try:
                    # Parse time format: 7d, 24h, 60m
                    time_str = time_arg.strip().lower()
                    if time_str.endswith('d'):
                        time_window_minutes = int(time_str[:-1]) * 1440
                    elif time_str.endswith('h'):
                        time_window_minutes = int(time_str[:-1]) * 60
                    elif time_str.endswith('m'):
                        time_window_minutes = int(time_str[:-1])
                    else:
                        time_window_minutes = int(time_str)  # Assume minutes
                except ValueError:
                    self.send_message(
                        chat_id,
                        f"⚠️ Invalid time format: {time_arg}\nUse: 7d, 24h, 60m",
                        reply_to_message_id=message_id
                    )
                    return
            
            # Show processing message
            time_display = f"{time_window_minutes // 1440}d" if time_window_minutes >= 1440 else f"{time_window_minutes // 60}h" if time_window_minutes >= 60 else f"{time_window_minutes}m"
            index_display = index_arg if index_arg else "all indices"
            ai_indicator = "🤖 AI Analysis Enabled" if include_ai else ""
            
            processing_msg = self.send_message(
                chat_id,
                f"⏳ <b>Processing Alert Summary...</b>\n\n"
                f"Time: {time_display}\n"
                f"Indices: {index_display}\n"
                f"{ai_indicator}\n\n" if ai_indicator else "\n"
                "Querying Elasticsearch for ML-classified alerts...",
                reply_to_message_id=message_id
            )
            
            # Call SmartXDR API for alert summarization
            # Use parsed time or ALERT_TIME_WINDOW from config (supports 7d/14d/28d format)
            response = self._session.post(
                f"{self.smartxdr_api_url}/api/triage/summarize-alerts",
                json={
                    "time_window_minutes": time_window_minutes,
                    "include_ai_analysis": include_ai
                },
                timeout=60 if include_ai else 30  # Longer timeout for AI analysis
            )
            
            result = response.json()
            
            if not result.get('success'):
                error_msg = result.get('error', 'Unknown error')
                self.send_message(
                    chat_id,
                    f"❌ <b>Alert Summary Failed</b>\n\n{html.escape(error_msg)}",
                    reply_to_message_id=message_id
                )
                return
            
            # Check if there are alerts to summarize
            if result.get('status') == 'no_alerts':
                time_window_mins = result.get('time_window_minutes', 10)
                time_display = f"{time_window_mins // 1440} days" if time_window_mins >= 1440 else f"{time_window_mins} minutes"
                self.send_message(
                    chat_id,
                    "ℹ️ <b>No Alerts Found</b>\n\n"
                    f"No ML-classified alerts detected in the last {time_display}.",
                    reply_to_message_id=message_id
                )
                return
            
            # Prepare formatted response
            alerts_count = result.get('count', 0)
            risk_score = result.get('risk_score', 0)
            summary = result.get('summary', 'No summary available')
            grouped = result.get('grouped_alerts', [])
            
            # Send summary card
            summary_text = (
                f"🚨 <b>ML Alert Summary</b>\n\n"
                f"<b>Risk Score:</b> {risk_score}/100 "
            )
            
            # Color-code risk score
            if risk_score >= 70:
                summary_text += "🔴 CRITICAL\n"
            elif risk_score >= 50:
                summary_text += "🟠 HIGH\n"
            elif risk_score >= 30:
                summary_text += "🟡 MEDIUM\n"
            else:
                summary_text += "🟢 LOW\n"
            
            summary_text += (
                f"<b>Total Alerts:</b> {alerts_count}\n"
                f"<b>Time Window:</b> {result.get('time_window_minutes', 10)} minutes\n"
                f"<b>Timestamp:</b> {result.get('timestamp', 'N/A')}\n\n"
            )
            
            summary_text += f"<b>Summary:</b>\n{self._format_response(summary)}\n\n"
            
            # Add grouped alerts summary
            if grouped:
                summary_text += "<b>Top Alert Groups:</b>\n"
                for i, group in enumerate(grouped[:3], 1):
                    summary_text += (
                        f"\n{i}. <b>{group['pattern'].upper()}</b>\n"
                        f"   • Source IP: <code>{group['source_ip']}</code>\n"
                        f"   • Severity: {group['severity']}\n"
                        f"   • Count: {group['alert_count']}\n"
                        f"   • Probability: {group['avg_probability']}\n"
                    )
            
            # Send main summary
            self.send_message(chat_id, summary_text, reply_to_message_id=message_id)
            
            # Send AI analysis if available
            if include_ai and 'ai_analysis' in result and result['ai_analysis']:
                ai_text = (
                    f"🤖 <b>AI Analysis & Recommendations</b>\n\n"
                    f"{self._format_response(result['ai_analysis'])}"
                )
                self.send_message(chat_id, ai_text, reply_to_message_id=message_id)
            
            # Send visualization if available
            if 'visualization' in result and result['visualization']:
                try:
                    import base64
                    import io
                    
                    # Decode base64 image
                    img_data = base64.b64decode(result['visualization'])
                    
                    # Send photo to Telegram
                    photo_url = f"{self.api_base}/sendPhoto"
                    files = {
                        'photo': ('alert_summary.png', io.BytesIO(img_data), 'image/png')
                    }
                    params = {
                        'chat_id': chat_id,
                        'caption': '📊 Alert Statistics Visualization'
                    }
                    
                    photo_response = self._tg_session.post(photo_url, params=params, files=files, timeout=10)
                    if not photo_response.ok:
                        logger.warning(f"⚠️ Failed to send visualization: {photo_response.text}")
                except Exception as e:
                    logger.error(f"❌ Error sending visualization: {e}")
            
            logger.info(f"✓ Alert summary sent to chat {chat_id} ({alerts_count} alerts, risk: {risk_score})")
            
        except requests.exceptions.Timeout:
            self.send_message(
                chat_id,
                "⏱️ <b>Timeout</b>\n\n"
                "Alert summary request timed out. The server might be busy.",
                reply_to_message_id=message_id
            )
            logger.error("Alert summary API timeout")
            
        except requests.exceptions.ConnectionError:
            self.send_message(
                chat_id,
                "🔌 <b>Connection Error</b>\n\n"
                "Cannot connect to SmartXDR API. Please ensure the server is running.",
                reply_to_message_id=message_id
            )
            logger.error("Alert summary API connection error")
            
        except Exception as e:
            self.send_message(
                chat_id,
                f"❌ <b>Error Generating Summary</b>\n\n{html.escape(str(e))}",
                reply_to_message_id=message_id
            )
            logger.error(f"Alert summary error: {e}")
    
    def _handle_sumlogs_analysis(
        self,
        chat_id: int,
        message_id: int,
        question: str,
        time_arg: Optional[str] = None,
        index_arg: str = "all",
        severity_arg: Optional[str] = None
    ) -> None:
        """
        Handle /sumlogs command - query ML logs and analyze with AI
        
        Args:
            chat_id: Telegram chat ID
            message_id: Message ID to reply to
            question: User's question about the logs
            time_arg: Time window (e.g., "24h", "7d")
            index_arg: Index pattern (e.g., "*suricata*", "all")
            severity_arg: Severity filter (e.g., "ERROR,WARNING")
        """
        try:
            from app.services.elasticsearch_service import ElasticsearchService
            from app.services.llm_service import LLMService
            
            # Send typing indicator
            self.send_typing_action(chat_id)
            
            # Parse time argument (default: 24h)
            hours = 24
            if time_arg:
                try:
                    time_str = time_arg.strip().lower()
                    if time_str.endswith('d'):
                        hours = int(time_str[:-1]) * 24
                    elif time_str.endswith('h'):
                        hours = int(time_str[:-1])
                    else:
                        hours = int(time_str)
                except ValueError:
                    self.send_message(
                        chat_id,
                        f"⚠️ Invalid time format: {time_arg}\nUsing default: 24h",
                        reply_to_message_id=message_id
                    )
            
            # Parse index pattern
            if index_arg == "all":
                index_pattern = "*"
            else:
                index_pattern = index_arg.strip()
            
            # Parse severity filter
            severity_filter = None
            if severity_arg:
                severity_filter = [s.strip().upper() for s in severity_arg.split(',')]
            
            # Show processing message
            processing_msg = self.send_message(
                chat_id,
                f"⏳ <b>Analyzing ML Logs...</b>\n\n"
                f"<b>Question:</b> {html.escape(question or 'Tìm logs nguy hiểm')}\n"
                f"<b>Time:</b> {hours}h\n"
                f"<b>Index:</b> {index_pattern}\n"
                f"<b>Severity:</b> {', '.join(severity_filter) if severity_filter else 'All'}\n\n"
                "🔍 Querying Elasticsearch...",
                reply_to_message_id=message_id
            )
            
            # Query Elasticsearch for ML logs
            es_service = ElasticsearchService()
            result = es_service.query_ml_logs(
                index_pattern=index_pattern,
                hours=hours,
                min_probability=0.5,
                severity_filter=severity_filter,
                max_results=50
            )
            
            if result.get('status') != 'success':
                self.send_message(
                    chat_id,
                    f"❌ <b>Query Failed</b>\n\n{html.escape(result.get('error', 'Unknown error'))}",
                    reply_to_message_id=message_id
                )
                return
            
            logs = result.get('logs', [])
            total = result.get('total', 0)
            
            if not logs:
                self.send_message(
                    chat_id,
                    "ℹ️ <b>No ML Logs Found</b>\n\n"
                    f"No logs with ML predictions found in the last {hours}h matching your criteria.",
                    reply_to_message_id=message_id
                )
                return
            
            # Load prompt template
            prompt_path = "prompts/instructions/sumlogs_analysis.json"
            system_prompt = ""
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    system_prompt = f.read()
            except:
                system_prompt = "Bạn là chuyên gia phân tích bảo mật mạng. Phân tích logs và đưa ra khuyến nghị."
            
            # Build context from logs - 2 versions: AI (truncated) and Full (for markdown)
            logs_context_header = f"Tổng số logs: {total}, Trả về: {len(logs)}\n\n"
            logs_context_header += "Danh sách logs (sắp xếp theo probability):\n\n"
            
            # Version 1: For AI (truncated ml_input, top 20 only)
            logs_context_ai = logs_context_header
            for i, log in enumerate(logs[:20], 1):  # Limit to top 20 for token optimization
                logs_context_ai += (
                    f"{i}. [{log['timestamp']}]\n"
                    f"   - ID: {log.get('_id', 'N/A')}\n"
                    f"   - ML Prediction: {log['ml_prediction']} (prob: {log['ml_probability']})\n"
                    f"   - Event: {log['ml_input']}\n"  # Already truncated to 200 chars
                    f"   - Source IP: {log['source_ip']} → Dest IP: {log['dest_ip']}\n"
                    f"   - Type: {log['event_type']}\n"
                    f"   - Index: {log['index']}\n\n"
                )
            
            # Version 2: For markdown file (full event_original, all logs)
            logs_context_full = logs_context_header
            for i, log in enumerate(logs, 1):  # All logs
                # Use event_original if available, else ml_input
                event_detail = log.get('event_original', log['ml_input'])
                logs_context_full += (
                    f"{i}. [{log['timestamp']}]\n"
                    f"   - ID: {log.get('_id', 'N/A')}\n"
                    f"   - ML Prediction: {log['ml_prediction']} (prob: {log['ml_probability']})\n"
                    f"   - Event: {event_detail}\n"  # Full event data
                    f"   - Source IP: {log['source_ip']} → Dest IP: {log['dest_ip']}\n"
                    f"   - Type: {log['event_type']}\n"
                    f"   - Index: {log['index']}\n\n"
                )
            
            # Build query for AI (include system prompt in query) - Use truncated version
            user_query = f"{system_prompt}\n\nCÂU HỎI: {question}\n\nDỮ LIỆU LOGS:\n{logs_context_ai}"
            
            # Call LLM with RAG (disable cache - index/time-specific queries)
            llm_service = LLMService()
            ai_response = llm_service.ask_rag(query=user_query, use_cache=False)
            
            if ai_response.get('status') != 'success':
                self.send_message(
                    chat_id,
                    f"❌ <b>AI Analysis Failed</b>\n\n{html.escape(ai_response.get('error', 'Unknown error'))}",
                    reply_to_message_id=message_id
                )
                return
            
            # Send summary statistics with logs preview
            severity_breakdown = result.get('summary', {}).get('severity_breakdown', {})
            stats_text = (
                f"📊 <b>ML Logs Summary</b>\n\n"
                f"<b>Total Logs:</b> {total}\n"
                f"<b>Analyzed:</b> {len(logs)}\n"
                f"<b>Time Range:</b> {hours}h\n"
                f"<b>Index:</b> {index_pattern}\n\n"
                f"<b>Severity Breakdown:</b>\n"
            )
            
            for severity, count in severity_breakdown.items():
                emoji = "🔴" if severity == "ERROR" else "🟠" if severity == "WARNING" else "🟢"
                stats_text += f"  {emoji} {severity}: {count}\n"
            
            # Add preview of logs data (truncated version for display)
            # stats_text += f"\n<b>Preview:</b>\n<pre>{logs_context_ai[:500]}...</pre>"
            
            self.send_message(chat_id, stats_text, reply_to_message_id=message_id)
            
            # Save AI analysis to markdown file
            analysis = ai_response.get('answer', 'No analysis available')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ml_logs_analysis_{timestamp}.md"
            filepath = os.path.join("logs", filename)
            
            # Ensure logs directory exists
            os.makedirs("logs", exist_ok=True)
            
            # Write analysis to markdown (use full logs data)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# ML Logs Analysis - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"**Question:** {question}\n\n")
                f.write(f"**Time Range:** {hours}h | **Index:** {index_pattern}\n\n")
                f.write(f"**Total Logs:** {total} | **Analyzed:** {len(logs)}\n\n")
                f.write("---\n\n")
                f.write("## Logs Data\n\n")
                f.write(logs_context_full)  # Full version with event_original
                f.write("\n\n---\n\n")
                f.write("## AI Analysis\n\n")
                f.write(analysis)
            
            # Send file with short caption
            caption = f"🤖 <b>AI Analysis Complete</b>\n\nQuestion: {question}\nTime: {hours}h | Logs: {len(logs)}"
            self.send_document(chat_id, filepath, caption=caption, reply_to_message_id=message_id)
            
        except Exception as e:
            self.send_message(
                chat_id,
                f"❌ <b>Error Analyzing Logs</b>\n\n{html.escape(str(e))}",
                reply_to_message_id=message_id
            )
            logger.error(f"Sumlogs analysis error: {e}")
    
    def _format_response(self, text: str) -> str:
        """
        Format AI response for Telegram display
        Converts markdown-like formatting to HTML
        """
        if not text:
            return text
        
        # Escape HTML entities first
        text = html.escape(text)
        
        # Convert code blocks
        text = re.sub(r'```(\w+)?\n?(.*?)```', r'<pre>\2</pre>', text, flags=re.DOTALL)
        
        # Convert inline code
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
        # Convert bold
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        
        # Convert italic
        text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)
        
        # Convert bullet points
        text = re.sub(r'^[-•] ', '• ', text, flags=re.MULTILINE)
        
        return text
    
    # ========== Polling Loop ==========
    
    def start_polling(self, threaded: bool = True) -> None:
        """
        Start the polling loop to receive messages
        
        Args:
            threaded: If True, run in a separate thread
        """
        if self._running:
            logger.warning("Polling is already running")
            return
        
        self._running = True
        self._stats["start_time"] = datetime.now()
        
        # Clear any pending updates
        self._clear_pending_updates()
        
        if threaded:
            self._poll_thread = threading.Thread(target=self._polling_loop, daemon=True)
            self._poll_thread.start()
            logger.info("Started polling in background thread")
        else:
            logger.info("Starting polling in main thread (blocking)")
            self._polling_loop()
    
    def stop_polling(self) -> None:
        """Stop the polling loop"""
        self._running = False
        logger.info("Stopping polling...")
        
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=5)
    
    def _polling_loop(self) -> None:
        """Main polling loop"""
        logger.info("Polling loop started")
        
        while self._running:
            try:
                updates = self.get_updates(offset=self.last_update_id + 1 if self.last_update_id else None)
                
                for update in updates:
                    update_id = update.get("update_id", 0)
                    if update_id > self.last_update_id:
                        self.last_update_id = update_id
                    
                    try:
                        self.process_update(update)
                    except Exception as e:
                        logger.error(f"Error processing update {update_id}: {e}")
                        self._stats["errors"] += 1
                        
            except Exception as e:
                logger.error(f"Polling loop error: {e}")
                time.sleep(5)  # Wait before retry
        
        logger.info("Polling loop stopped")
    
    def _clear_pending_updates(self) -> None:
        """Clear any pending updates to avoid processing old messages"""
        try:
            updates = self.get_updates(timeout=1)
            if updates:
                self.last_update_id = max(u.get("update_id", 0) for u in updates)
                logger.info(f"Cleared {len(updates)} pending updates")
        except Exception as e:
            logger.warning(f"Failed to clear pending updates: {e}")
    
    def is_running(self) -> bool:
        """Check if polling is currently running"""
        return self._running
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        stats = self._stats.copy()
        if stats["start_time"]:
            stats["uptime_seconds"] = (datetime.now() - stats["start_time"]).total_seconds()
        return stats
    
    # ========== Custom Handler ==========
    
    def set_custom_handler(self, handler: Callable[[str, int, int, Dict], Optional[str]]) -> None:
        """
        Set a custom message handler
        
        Args:
            handler: Function that takes (query, chat_id, message_id, user) 
                     and returns response string or None to use default handler
        """
        self._custom_handler = handler
        logger.info("Custom message handler registered")
    
    def clear_custom_handler(self) -> None:
        """Remove custom message handler"""
        self._custom_handler = None
        logger.info("Custom message handler cleared")
