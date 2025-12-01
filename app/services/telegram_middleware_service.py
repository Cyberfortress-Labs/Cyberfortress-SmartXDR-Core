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

logger = setup_logger("telegram_middleware")


class TelegramMiddlewareService:
    """
    Telegram Bot middleware service that:
    - Uses long polling to receive messages
    - Forwards queries to SmartXDR /api/ai/ask endpoint
    - Returns AI responses back to Telegram
    - Supports whitelist, rate limiting, and auto-block for spam protection
    """
    
    def __init__(self, bot_token: str = None, smartxdr_api_url: str = None):
        """
        Initialize Telegram middleware service
        
        Args:
            bot_token: Telegram Bot token from BotFather
            smartxdr_api_url: SmartXDR API base URL
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.smartxdr_api_url = smartxdr_api_url or os.getenv("SMARTXDR_API_URL", "http://localhost:8080")
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"
        
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
            response = requests.get(
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
            response = requests.post(
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
                response = requests.post(
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
            requests.post(
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
            response = requests.get(
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
        
        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        text = message.get("text", "")
        message_id = message.get("message_id")
        
        if not chat_id or not text:
            return
        
        # Get user info for logging
        user = message.get("from", {})
        username = user.get("username", "unknown")
        first_name = user.get("first_name", "unknown")
        
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
        
        # Check rate limit
        if self.is_rate_limited(user_id):
            logger.warning(f"Rate limited user {user_id} (@{username})")
            self._stats["messages_blocked"] += 1
            rate_info = self.get_rate_limit_info(user_id)
            
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
                "• Generate threat intelligence reports\n\n"
                "<b>Example queries:</b>\n"
                "• <i>Analyze this Suricata alert: ET MALWARE Win32/Emotet...</i>\n"
                "• <i>What is the MITRE technique for credential dumping?</i>\n"
                "• <i>How to respond to a ransomware incident?</i>\n\n"
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
        # Send typing indicator
        self.send_typing_action(chat_id)
        
        try:
            # Call SmartXDR API
            logger.info(f"Sending query to SmartXDR: {query[:100]}...")
            
            response = requests.post(
                f"{self.smartxdr_api_url}/api/ai/ask",
                json={"query": query},
                timeout=120  # AI can take time
            )
            
            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", data.get("response", "No response received."))
                
                # Format response for Telegram
                formatted_response = self._format_response(answer)
                
                self.send_message(
                    chat_id,
                    f"🤖 <b>SmartXDR Analysis</b>\n\n{formatted_response}",
                    reply_to_message_id=message_id
                )
                
                self._stats["messages_processed"] += 1
                logger.info(f"Successfully processed query for @{user.get('username')}")
                
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
            self.send_message(
                chat_id,
                "⏱️ <b>Timeout</b>\n\nThe request took too long. Please try again.",
                reply_to_message_id=message_id
            )
            self._stats["errors"] += 1
            logger.error("SmartXDR API timeout")
            
        except requests.exceptions.ConnectionError:
            self.send_message(
                chat_id,
                "🔌 <b>Connection Error</b>\n\n"
                "Cannot connect to SmartXDR API. Please ensure the server is running.",
                reply_to_message_id=message_id
            )
            self._stats["errors"] += 1
            logger.error("SmartXDR API connection error")
            
        except Exception as e:
            self.send_message(
                chat_id,
                f"❌ <b>Error</b>\n\nAn unexpected error occurred: {html.escape(str(e))}",
                reply_to_message_id=message_id
            )
            self._stats["errors"] += 1
            logger.error(f"Unexpected error: {e}")
    
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
