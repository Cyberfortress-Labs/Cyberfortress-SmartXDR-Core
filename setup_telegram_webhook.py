#!/usr/bin/env python3
"""
Setup Telegram Webhook with Cloudflare Tunnel

This script:
1. Starts Cloudflare Tunnel to expose localhost:8080
2. Automatically sets up Telegram webhook with the tunnel URL
3. Shows status and instructions

Usage:
    python setup_telegram_webhook.py
"""

import os
import sys
import time
import subprocess
import requests
import re
import signal
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()


def find_cloudflared():
    """Find cloudflared executable"""
    # Check if in PATH
    cloudflared = shutil.which("cloudflared")
    if cloudflared:
        return cloudflared
    
    # Common installation paths on Windows
    possible_paths = [
        r"C:\Program Files\cloudflared\cloudflared.exe",
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\cloudflared\cloudflared.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\cloudflared\cloudflared.exe"),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None


def get_bot_token():
    """Get Telegram bot token from environment"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found in .env")
        sys.exit(1)
    return token


def test_local_server(port=8080):
    """Check if local Flask server is running"""
    try:
        response = requests.get(f"http://localhost:{port}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


def start_cloudflare_tunnel(port=8080):
    """Start Cloudflare Tunnel and return the public URL"""
    print(f"\n🚀 Starting Cloudflare Tunnel for localhost:{port}...")
    
    # Find cloudflared executable
    cloudflared_path = find_cloudflared()
    if not cloudflared_path:
        print("❌ cloudflared not found!")
        print("   Install with: winget install --id Cloudflare.cloudflared")
        print("   Or download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")
        sys.exit(1)
    
    print(f"   Using: {cloudflared_path}")
    
    # Start cloudflared in background
    process = subprocess.Popen(
        [cloudflared_path, "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Wait for tunnel URL
    tunnel_url = None
    start_time = time.time()
    timeout = 30  # seconds
    
    print("   Waiting for tunnel URL...")
    
    while time.time() - start_time < timeout:
        line = process.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue
        
        # Look for the tunnel URL in output
        # Pattern: https://xxx.trycloudflare.com
        match = re.search(r'(https://[a-z0-9-]+\.trycloudflare\.com)', line)
        if match:
            tunnel_url = match.group(1)
            print(f"   ✅ Tunnel URL: {tunnel_url}")
            break
        
        # Also check for errors
        if "error" in line.lower():
            print(f"   ⚠️  {line.strip()}")
    
    if not tunnel_url:
        print("❌ Failed to get tunnel URL within timeout")
        process.terminate()
        sys.exit(1)
    
    return process, tunnel_url


def set_webhook(bot_token, tunnel_url):
    """Set Telegram webhook"""
    webhook_url = f"{tunnel_url}/api/telegram/webhook"
    
    print(f"\n📡 Setting Telegram webhook...")
    print(f"   URL: {webhook_url}")
    
    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        json={
            "url": webhook_url,
            "allowed_updates": ["message"],
            "drop_pending_updates": True
        },
        timeout=10
    )
    
    result = response.json()
    
    if result.get("ok"):
        print("   ✅ Webhook set successfully!")
        return True
    else:
        print(f"   ❌ Failed: {result.get('description')}")
        return False


def get_webhook_info(bot_token):
    """Get current webhook status"""
    response = requests.get(
        f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",
        timeout=10
    )
    return response.json().get("result", {})


def delete_webhook(bot_token):
    """Delete webhook (for cleanup)"""
    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/deleteWebhook",
        json={"drop_pending_updates": True},
        timeout=10
    )
    return response.json().get("ok", False)


def main():
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║   🔗 Telegram Webhook Setup with Cloudflare Tunnel                        ║
║                                                                           ║
║   This exposes your local server to the internet securely                 ║
║   No need for domain or SSL certificate!                                  ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Get bot token
    bot_token = get_bot_token()
    masked_token = f"{bot_token.split(':')[0]}:****"
    print(f"🤖 Bot Token: {masked_token}")
    
    # Check local server
    print("\n🔍 Checking local server...")
    if not test_local_server():
        print("   ⚠️  Local server not running on port 8080")
        print("   💡 Start it first: python run.py")
        print("\n   Continue anyway? (y/n): ", end="")
        if input().lower() != 'y':
            sys.exit(0)
    else:
        print("   ✅ Local server is running")
    
    # Start tunnel
    tunnel_process, tunnel_url = start_cloudflare_tunnel()
    
    # Set webhook
    if not set_webhook(bot_token, tunnel_url):
        tunnel_process.terminate()
        sys.exit(1)
    
    # Show status
    print("\n" + "=" * 60)
    print("✅ WEBHOOK SETUP COMPLETE!")
    print("=" * 60)
    print(f"""
📍 Tunnel URL:  {tunnel_url}
📡 Webhook URL: {tunnel_url}/api/telegram/webhook

🔄 Mode: WEBHOOK (real-time, efficient)
   - No polling needed
   - Telegram sends messages directly to your server
   - Much faster response time!

⚠️  IMPORTANT:
   - Keep this terminal running (tunnel is active)
   - Make sure Flask server is running: python run.py
   - Press Ctrl+C to stop tunnel and switch back to polling

📱 Test: Send a message to your bot on Telegram!
    """)
    print("=" * 60)
    
    # Keep tunnel running
    print("\n🔄 Tunnel is running. Press Ctrl+C to stop...\n")
    
    def signal_handler(sig, frame):
        print("\n\n🛑 Stopping tunnel...")
        print("🔄 Deleting webhook...")
        delete_webhook(bot_token)
        tunnel_process.terminate()
        print("✅ Cleanup complete. You can now use polling mode.")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Stream tunnel output
    try:
        while True:
            line = tunnel_process.stdout.readline()
            if line:
                # Filter out noisy logs, show only important ones
                if any(x in line.lower() for x in ['error', 'warn', 'connection', 'request']):
                    print(f"   [tunnel] {line.strip()}")
            else:
                if tunnel_process.poll() is not None:
                    print("⚠️  Tunnel process ended unexpectedly")
                    break
                time.sleep(0.1)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
