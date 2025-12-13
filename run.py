"""
Cyberfortress SmartXDR Core - Flask Application Entry Point
"""
import os
import sys

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
if sys.platform == 'linux':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

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
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='passlib')
warnings.filterwarnings('ignore', category=DeprecationWarning)
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
    windows_paths = [
        r"C:\Program Files\cloudflared\cloudflared.exe",
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\cloudflared\cloudflared.exe"),
    ]
    
    # Common paths on Linux
    linux_paths = [
        "/usr/local/bin/cloudflared",
        "/usr/bin/cloudflared",
        "/opt/cloudflared/cloudflared",
        os.path.expanduser("~/.local/bin/cloudflared"),
    ]
    
    # Try all paths based on OS
    all_paths = windows_paths if os.name == 'nt' else linux_paths
    for path in all_paths:
        if os.path.exists(path):
            return path
    return None


def get_cloudflare_config():
    """Check if cloudflare config exists and return config info"""
    import glob
    import yaml
    
    # Config directory relative to run.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(base_dir, "cloudflared")
    config_file = os.path.join(config_dir, "config.yml")
    
    # Check if config directory and config file exist
    if not os.path.exists(config_dir) or not os.path.exists(config_file):
        return None
    
    # Check for credential files (*.json)
    cred_files = glob.glob(os.path.join(config_dir, "*.json"))
    if not cred_files:
        return None
    
    # Read config file to get tunnel name/hostname
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        tunnel_name = config.get('tunnel')
        hostname = None
        
        # Extract hostname from ingress rules
        ingress = config.get('ingress', [])
        for rule in ingress:
            if isinstance(rule, dict) and 'hostname' in rule:
                hostname = rule.get('hostname')
                break
        
        return {
            'config_file': config_file,
            'config_dir': config_dir,
            'credential_file': cred_files[0],
            'tunnel_name': tunnel_name,
            'hostname': hostname
        }
    except Exception as e:
        print(f"  Error reading cloudflare config: {e}")
        return None


def start_tunnel(port):
    """Start Cloudflare Tunnel in background
    
    If cloudflared config exists in ./cloudflared/, runs named tunnel with custom domain.
    Otherwise, falls back to quick tunnel (free trycloudflare.com domain).
    """
    global _tunnel_process, _tunnel_url
    
    cloudflared = find_cloudflared()
    if not cloudflared:
        print("cloudflared not found - Telegram webhook disabled")
        print("     Install: winget install --id Cloudflare.cloudflared")
        return None
    
    # Check for existing cloudflare config
    cf_config = get_cloudflare_config()
    
    if cf_config and cf_config.get('tunnel_name'):
        # Run with named tunnel (custom domain)
        # Create temporary config with localhost service for local development
        import yaml
        import tempfile
        
        print(f"  Found cloudflare config, starting named tunnel...")
        print(f"    Tunnel: {cf_config['tunnel_name']}")
        if cf_config.get('hostname'):
            print(f"    Hostname: {cf_config['hostname']}")
        print(f"    Service: http://localhost:{port} (local override)")
        
        # Read original config and modify service to localhost
        try:
            with open(cf_config['config_file'], 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Override ingress service to localhost
            if 'ingress' in config:
                for rule in config['ingress']:
                    if isinstance(rule, dict) and 'service' in rule:
                        rule['service'] = f"http://localhost:{port}"
            
            # Override credentials-file to use local path
            config['credentials-file'] = cf_config['credential_file']
            
            # Write temporary config
            temp_config_path = os.path.join(cf_config['config_dir'], "config_local.yml")
            with open(temp_config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, default_flow_style=False)
            
            # Store temp config path for cleanup
            cf_config['temp_config'] = temp_config_path
            
        except Exception as e:
            print(f"  Error creating temp config: {e}")
            temp_config_path = cf_config['config_file']
        
        _tunnel_process = subprocess.Popen(
            [
                cloudflared, "tunnel",
                "--config", temp_config_path,
                "run", cf_config['tunnel_name']
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Give tunnel time to initialize
        time.sleep(3)
        
        # For named tunnels, URL is the configured hostname
        if cf_config.get('hostname'):
            _tunnel_url = f"https://{cf_config['hostname']}"
            print(f"  Tunnel URL: {_tunnel_url}")
            return _tunnel_url
        else:
            print("  Warning: No hostname configured in config.yml")
            return None
    else:
        # Fallback to quick tunnel (free domain)
        print(f"  No cloudflare config found, using quick tunnel (free domain)...")
        
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
