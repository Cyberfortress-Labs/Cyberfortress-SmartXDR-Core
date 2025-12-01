"""
Cyberfortress SmartXDR Core - Flask Application Entry Point
"""
import os
import sys
import time
import signal
import atexit
import shutil
import subprocess
import threading
import re
import requests
from dotenv import load_dotenv
from app import create_app, get_collection
from app.config import PORT, HOST
from app.core.ingestion import ingest_data

# Load environment variables
load_dotenv()

# Global tunnel process
_tunnel_process = None
_tunnel_url = None


def find_cloudflared():
    """Find cloudflared executable"""
    cloudflared = shutil.which("cloudflared")
    if cloudflared:
        return cloudflared
    
    # Common paths on Windows
    paths = [
        r"C:\Program Files\cloudflared\cloudflared.exe",
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\cloudflared\cloudflared.exe"),
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def start_tunnel(port):
    """Start Cloudflare Tunnel in background"""
    global _tunnel_process, _tunnel_url
    
    cloudflared = find_cloudflared()
    if not cloudflared:
        print("  ⚠️  cloudflared not found - Telegram webhook disabled")
        print("     Install: winget install --id Cloudflare.cloudflared")
        return None
    
    print(f"  🚀 Starting Cloudflare Tunnel...")
    
    _tunnel_process = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Wait for tunnel URL
    start_time = time.time()
    while time.time() - start_time < 30:
        line = _tunnel_process.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue
        
        match = re.search(r'(https://[a-z0-9-]+\.trycloudflare\.com)', line)
        if match:
            _tunnel_url = match.group(1)
            print(f"  ✅ Tunnel URL: {_tunnel_url}")
            return _tunnel_url
    
    print("  ❌ Failed to get tunnel URL")
    return None


def set_telegram_webhook(tunnel_url):
    """Set Telegram webhook with tunnel URL"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("  ⚠️  TELEGRAM_BOT_TOKEN not set - webhook skipped")
        return False
    
    webhook_url = f"{tunnel_url}/api/telegram/webhook"
    print(f"  📡 Setting webhook: {webhook_url}")
    
    # Wait for DNS propagation
    time.sleep(5)
    
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={
                "url": webhook_url,
                "allowed_updates": ["message"],
                "drop_pending_updates": True
            },
            timeout=15
        )
        result = response.json()
        
        if result.get("ok"):
            print("  ✅ Telegram webhook active!")
            return True
        else:
            print(f"  ❌ Webhook failed: {result.get('description')}")
            return False
    except Exception as e:
        print(f"  ❌ Webhook error: {e}")
        return False


def cleanup_tunnel():
    """Cleanup tunnel on exit"""
    global _tunnel_process
    if _tunnel_process:
        print("\n🛑 Stopping Cloudflare Tunnel...")
        _tunnel_process.terminate()
        _tunnel_process = None
        
        # Delete webhook
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if bot_token:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/deleteWebhook",
                    json={"drop_pending_updates": True},
                    timeout=5
                )
                print("  ✅ Webhook removed")
            except:
                pass


# Register cleanup
atexit.register(cleanup_tunnel)
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

# Create Flask app (this initializes the collection)
app = create_app()

if __name__ == '__main__':
    # Check API key
    if not os.getenv('OPENAI_API_KEY'):
        print("ERROR: OPENAI_API_KEY not found in .env file!")
        print("   Please add your OpenAI API key to .env file")
        exit(1)
    
    # Run data ingestion on startup
    print("Initializing data ingestion...")
    collection = get_collection()
    ingest_data(collection)
    print("Data ingestion completed.\n")
    
    # Run Flask app
    print("="*80)
    print("Cyberfortress SmartXDR Core - API Server")
    print("="*80)
    print("Endpoints:")
    print("  AI/RAG:")
    print("    - POST /api/ai/ask       - Ask LLM a question")
    print("    - GET  /api/ai/stats     - Get usage statistics")
    print("    - POST /api/ai/cache/clear - Clear response cache")
    print("  IOC Enrichment:")
    print("    - POST /api/enrich/explain_intelowl - Explain IntelOwl results with AI (single IOC)")
    print("    - POST /api/enrich/explain_case_iocs - Analyze all IOCs in a case with AI")
    print("  Telegram:")
    print("    - POST /api/telegram/webhook - Telegram webhook (auto-configured)")
    print("  Health:")
    print("    - GET  /health           - Health check")
    print("="*80)
    
    # Start Cloudflare Tunnel for Telegram webhook
    print("\n🔗 Telegram Integration:")
    use_tunnel = os.getenv("TELEGRAM_WEBHOOK_ENABLED", "true").lower() == "true"
    
    if use_tunnel and os.getenv("TELEGRAM_BOT_TOKEN"):
        def setup_tunnel_async():
            time.sleep(2)  # Wait for Flask to start
            tunnel_url = start_tunnel(PORT)
            if tunnel_url:
                set_telegram_webhook(tunnel_url)
        
        tunnel_thread = threading.Thread(target=setup_tunnel_async, daemon=True)
        tunnel_thread.start()
        print("  ⏳ Tunnel starting in background...")
    else:
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            print("  ⚠️  TELEGRAM_BOT_TOKEN not set - Telegram disabled")
        else:
            print("  ⚠️  Webhook disabled (set TELEGRAM_WEBHOOK_ENABLED=true to enable)")
    
    print("="*80 + "\n")
    
    app.run(
        host=HOST,
        port=PORT,
        debug=True,
        use_reloader=False  # Disable reloader to prevent duplicate tunnels
    )
