#!/usr/bin/env python3
"""
SmartXDR Telegram Bot Middleware Runner

Setup:
    1. Open Telegram, search for @BotFather
    2. Send /newbot and follow instructions
    3. Copy the token to .env: TELEGRAM_BOT_TOKEN=your_token
    4. Run: python run_telegram_middleware.py

Usage:
    python run_telegram_middleware.py [--debug] [--check]
"""

import sys
import argparse
import logging
import urllib3
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.telegram_middleware_service import TelegramMiddlewareService, TelegramConfig


def print_banner():
    """Print startup banner"""
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║   ███████╗███╗   ███╗ █████╗ ██████╗ ████████╗██╗  ██╗██████╗ ██████╗    ║
║   ██╔════╝████╗ ████║██╔══██╗██╔══██╗╚══██╔══╝╚██╗██╔╝██╔══██╗██╔══██╗   ║
║   ███████╗██╔████╔██║███████║██████╔╝   ██║    ╚███╔╝ ██║  ██║██████╔╝   ║
║   ╚════██║██║╚██╔╝██║██╔══██║██╔══██╗   ██║    ██╔██╗ ██║  ██║██╔══██╗   ║
║   ███████║██║ ╚═╝ ██║██║  ██║██║  ██║   ██║   ██╔╝ ██╗██████╔╝██║  ██║   ║
║   ╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝   ║
║                                                                           ║
║                     Telegram Bot Middleware                               ║
║                                                                           ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║   ✅ Simple setup - just need a bot token from @BotFather                 ║
║   ✅ Works with any Telegram account (personal or business)               ║
║   ✅ Outbound-only - no webhooks or open ports required                   ║
║   ✅ Supports private chats and groups                                    ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
    """)


def print_setup_guide():
    """Print setup instructions"""
    print("""
📖 SETUP GUIDE
══════════════════════════════════════════════════════════════════════════════

Step 1: Create a Telegram Bot
─────────────────────────────
  1. Open Telegram app
  2. Search for @BotFather
  3. Send: /newbot
  4. Follow instructions (choose name and username)
  5. Copy the API token (looks like: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)

Step 2: Configure Environment
─────────────────────────────
  Add to your .env file:
  
    TELEGRAM_BOT_TOKEN=your_bot_token_here
    TELEGRAM_ALLOWED_CHATS=           # Empty = allow all, or comma-separated IDs
    SMARTXDR_API_URL=http://localhost:8080/api/ai/ask

Step 3: Run the Bot
─────────────────────────────
    python run_telegram_middleware.py

Step 4: Test
─────────────────────────────
  1. Open Telegram
  2. Search for your bot by username
  3. Send /start
  4. Try asking a question!

══════════════════════════════════════════════════════════════════════════════
    """)


def check_config() -> bool:
    """Check and display configuration"""
    config = TelegramConfig()
    
    print("\n📋 Configuration Check:")
    print("-" * 50)
    
    # Check bot token
    if config.bot_token:
        # Mask token for display
        token = config.bot_token
        if ':' in token:
            parts = token.split(':')
            masked = f"{parts[0]}:{'*' * 10}...{parts[1][-4:]}"
        else:
            masked = f"{token[:8]}...{token[-4:]}"
        print(f"  ✅ Bot Token: {masked}")
    else:
        print("  ❌ Bot Token: NOT SET")
        print("\n     💡 Get a token from @BotFather on Telegram")
        return False
    
    # Check allowed chats
    allowed = config.get_allowed_chats()
    if allowed:
        print(f"  🔒 Allowed Chats: {allowed}")
    else:
        print("  🔓 Allowed Chats: ALL (no whitelist)")
    
    # Check API URL
    print(f"  📍 SmartXDR API: {config.smartxdr_api_url}")
    
    print("-" * 50)
    
    # Validate
    valid, message = config.validate()
    if valid:
        print("  ✅ Configuration valid!")
    else:
        print(f"  ❌ {message}")
    
    return valid


def test_connection() -> bool:
    """Test bot connection"""
    print("\n🔗 Testing Telegram Connection...")
    
    service = TelegramMiddlewareService()
    bot_info = service.get_bot_info()
    
    if bot_info:
        print(f"  ✅ Connected to Telegram!")
        print(f"  🤖 Bot Name: {bot_info.get('first_name')}")
        print(f"  👤 Username: @{bot_info.get('username')}")
        print(f"  🆔 Bot ID: {bot_info.get('id')}")
        return True
    else:
        print("  ❌ Failed to connect!")
        print("  💡 Check your TELEGRAM_BOT_TOKEN in .env")
        return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='SmartXDR Telegram Bot Middleware',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_telegram_middleware.py           # Run the bot
  python run_telegram_middleware.py --check   # Check configuration
  python run_telegram_middleware.py --debug   # Run with debug logging
  python run_telegram_middleware.py --setup   # Show setup guide
        """
    )
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--check', action='store_true', help='Check configuration and test connection')
    parser.add_argument('--setup', action='store_true', help='Show setup guide')
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    
    # Create logs directory if needed
    Path('logs').mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/telegram_middleware.log', mode='a', encoding='utf-8')
        ]
    )
    
    # Suppress SSL warnings
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    print_banner()
    
    # Show setup guide
    if args.setup:
        print_setup_guide()
        return
    
    # Check configuration
    if not check_config():
        print("\n❌ Configuration incomplete!")
        print("   Run with --setup for instructions")
        sys.exit(1)
    
    # Test connection
    if not test_connection():
        sys.exit(1)
    
    if args.check:
        print("\n✅ All checks passed!")
        sys.exit(0)
    
    # Start the bot
    print("\n" + "=" * 60)
    print("🚀 Starting Telegram Bot...")
    print("   Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    middleware = TelegramMiddlewareService()
    
    try:
        success = middleware.start(blocking=True)
        if not success:
            print("\n❌ Failed to start middleware")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n")
        middleware.stop()
        
        # Print final stats
        stats = middleware.get_stats()
        print("\n📊 Session Statistics:")
        print(f"   Messages Received: {stats['messages_received']}")
        print(f"   Messages Processed: {stats['messages_processed']}")
        print(f"   Replies Sent: {stats['messages_replied']}")
        print(f"   Errors: {stats['errors']}")
        
        print("\n👋 Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
