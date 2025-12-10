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
        print("cloudflared not found - Telegram webhook disabled")
        print("     Install: winget install --id Cloudflare.cloudflared")
        return None
    
    print(f"  Starting Cloudflare Tunnel...")
    
    _tunnel_process = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Give tunnel time to initialize
    time.sleep(2)
    
    # Wait for tunnel URL
    start_time = time.time()
    while time.time() - start_time < 30:
        line = _tunnel_process.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue
        
        # Regex: URL must start with letter, then alphanumeric/hyphen, NOT start with hyphen
        match = re.search(r'(https://[a-z][a-z0-9-]*\.trycloudflare\.com)', line)
        if match:
            _tunnel_url = match.group(1)
            # Validate URL doesn't have consecutive hyphens or hyphen at weird places
            if '--' not in _tunnel_url and not _tunnel_url.startswith('https://-'):
                print(f"  Tunnel URL: {_tunnel_url}")
                return _tunnel_url
            else:
                print(f"  Invalid tunnel URL detected, retrying...")
                continue
    
    print("  Failed to get tunnel URL")
    return None


def set_telegram_webhook(tunnel_url):
    """Set Telegram webhook with tunnel URL"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("  TELEGRAM_BOT_TOKEN not set - webhook skipped")
        return False
    
    webhook_url = f"{tunnel_url}/api/telegram/webhook"
    print(f"  Setting webhook: {webhook_url}")
    
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
            print("  Telegram webhook active!")
            return True
        else:
            print(f"  Webhook failed: {result.get('description')}")
            return False
    except Exception as e:
        print(f"  Webhook error: {e}")
        return False


def cleanup_tunnel():
    """Cleanup tunnel on exit"""
    global _tunnel_process
    if _tunnel_process:
        print("\nStopping Cloudflare Tunnel...")
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
                print("  Webhook removed")
            except:
                pass


# Register cleanup
atexit.register(cleanup_tunnel)
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

# Create Flask app (this initializes the collection)
app = create_app()

# Initialize and start daily report scheduler
from app.services.daily_report_scheduler import get_daily_report_scheduler

scheduler = get_daily_report_scheduler()
if scheduler.enabled:
    scheduler.start()
    atexit.register(scheduler.stop)
    print(f"Daily report scheduler started (sends at {os.getenv('DAILY_REPORT_TIME', '07:00')})")
else:
    print("Daily report scheduler disabled (check email configuration in .env)")

if __name__ == '__main__':
    # Check API key
    if not os.getenv('OPENAI_API_KEY'):
        print("ERROR: OPENAI_API_KEY not found in .env file!")
        print("   Please add your OpenAI API key to .env file")
        exit(1)
    
    # Run data ingestion on startup
    # NOTE: Ingestion now managed through RAG API endpoints
    # Use POST /api/rag/documents to add documents
    print("RAG system ready. Use /api/rag/documents endpoint to manage knowledge base.\n")
    
    # Run Flask app
    print("="*80)
    print("Cyberfortress SmartXDR Core - API Server")
    print("="*80)
    print("Endpoints:")
    print("  AI/RAG:")
    print("    - POST /api/ai/ask       - Ask LLM a question")
    print("    - GET  /api/ai/stats     - Get usage statistics")
    print("    - POST /api/ai/cache/clear - Clear response cache")
    print("\n  RAG Knowledge Base:")
    print("    - POST /api/rag/documents - Create document")
    print("    - POST /api/rag/documents/batch - Batch create documents")
    print("    - GET  /api/rag/documents - List documents")
    print("    - GET  /api/rag/documents/<id> - Get document by ID")
    print("    - PUT  /api/rag/documents/<id> - Update document")
    print("    - DELETE /api/rag/documents/<id> - Delete document")
    print("    - POST /api/rag/query    - RAG query (search + LLM answer)")
    print("    - GET  /api/rag/stats    - RAG statistics")
    print("\n  IOC Enrichment:")
    print("    - POST /api/enrich/explain_intelowl - Explain IntelOwl results with AI (single IOC)")
    print("    - POST /api/enrich/explain_case_iocs - Analyze all IOCs in a case with AI")
    print("    - GET /api/enrich/case_ioc_comments - Get SmartXDR comments for case IOCs")
    print("\n  Triage & Alerts:")
    print("    - POST /api/triage/summarize-alerts - Summarize ML-classified alerts (supports include_ai_analysis=true)")
    print("    - POST /api/triage/send-report-email - Send alert summary via email")
    print("    - POST /api/triage/daily-report/trigger - Manually trigger daily report")
    print("    - GET  /api/triage/health - Check triage service health")
    print("\n  Telegram:")
    print("    - POST /api/telegram/webhook - Telegram webhook (auto-configured)")
    print("\n  Health:")
    print("    - GET  /health           - Health check")
    print("="*80)
    
    # Start Cloudflare Tunnel for Telegram webhook
    print("\nTelegram Integration:")
    bot_enabled = os.getenv("TELEGRAM_BOT_ENABLED", "true").lower() == "true"
    use_tunnel = os.getenv("TELEGRAM_WEBHOOK_ENABLED", "true").lower() == "true"
    
    if not bot_enabled:
        print("  Telegram bot DISABLED (set TELEGRAM_BOT_ENABLED=true to enable)")
    elif bot_enabled and os.getenv("TELEGRAM_BOT_TOKEN") and use_tunnel:
        def setup_tunnel_async():
            time.sleep(2)  # Wait for Flask to start
            tunnel_url = start_tunnel(PORT)
            if tunnel_url:
                set_telegram_webhook(tunnel_url)
        
        tunnel_thread = threading.Thread(target=setup_tunnel_async, daemon=True)
        tunnel_thread.start()
        print("  Tunnel starting in background...")
    else:
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            print("  TELEGRAM_BOT_TOKEN not set - Telegram disabled")
        else:
            print("  Webhook disabled (set TELEGRAM_WEBHOOK_ENABLED=true to enable)")
    
    print("="*80 + "\n")
    
    app.run(
        host=HOST,
        port=PORT,
        debug=True,
        use_reloader=False  # Disable reloader to prevent duplicate tunnels
    )
