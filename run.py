"""
Cyberfortress SmartXDR Core - Flask Application Entry Point
This script only runs for local development and testing.
In production, use the Gunicorn server defined in the Dockerfile.
Please refer to the README for more information.
"""
import os
import sys
import warnings

# Suppress deprecation warnings from passlib (uses deprecated pkg_resources)
# MUST be before any other imports that use passlib
warnings.filterwarnings('ignore', category=UserWarning, module='passlib')
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*pkg_resources.*')

import logging

# Setup logger
logger = logging.getLogger('smartxdr.main')

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
        logger.error(f"Error reading cloudflare config: {e}")
        return None


def start_tunnel(port):
    """Start Cloudflare Tunnel in background
    
    If cloudflared config exists in ./cloudflared/, runs named tunnel with custom domain.
    Otherwise, falls back to quick tunnel (free trycloudflare.com domain).
    """
    global _tunnel_process, _tunnel_url
    
    cloudflared = find_cloudflared()
    if not cloudflared:
        logger.warning("cloudflared not found - Telegram webhook disabled")
        logger.warning("Install: winget install --id Cloudflare.cloudflared")
        return None
    
    # Check for existing cloudflare config
    cf_config = get_cloudflare_config()
    
    if cf_config and cf_config.get('tunnel_name'):
        # Run with named tunnel (custom domain)
        # Create temporary config with localhost service for local development
        import yaml
        import tempfile
        
        logger.info("Found cloudflare config, starting named tunnel...")
        logger.info(f"Tunnel: {cf_config['tunnel_name']}")
        if cf_config.get('hostname'):
            logger.info(f"Hostname: {cf_config['hostname']}")
        logger.info(f"Service: http://localhost:{port} (local override)")
        
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
            logger.error(f"Error creating temp config: {e}")
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
            logger.info(f"Tunnel URL: {_tunnel_url}")
            return _tunnel_url
        else:
            logger.warning("No hostname configured in config.yml")
            return None
    else:
        # Fallback to quick tunnel (free domain)
        logger.info(f"No cloudflare config found, using quick tunnel (free domain)...")
        
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
                    logger.info(f"Tunnel URL: {_tunnel_url}")
                    return _tunnel_url
                else:
                    logger.warning("Invalid tunnel URL detected, retrying...")
                    continue
        
        logger.warning("Failed to get tunnel URL")
        return None


def set_telegram_webhook(tunnel_url):
    """Set Telegram webhook with tunnel URL"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set - webhook skipped")
        return False
    
    webhook_url = f"{tunnel_url}/api/telegram/webhook"
    logger.info(f"Setting webhook: {webhook_url}")
    
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
            logger.info("Telegram webhook active!")
            return True
        else:
            logger.warning(f"Webhook failed: {result.get('description')}")
            return False
    except Exception as e:
        logger.warning(f"Webhook error: {e}")
        return False


def cleanup_tunnel():
    """Cleanup tunnel on exit"""
    global _tunnel_process
    if _tunnel_process:
        logger.info("\nStopping Cloudflare Tunnel...")
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
                logger.info("Webhook removed")
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
    logger.info(f"Daily report scheduler started (sends at {os.getenv('DAILY_REPORT_TIME', '07:00')})")
else:
    logger.warning("Daily report scheduler disabled (check email configuration in .env)")

if __name__ == '__main__':
    # Check API key
    if not os.getenv('OPENAI_API_KEY'):
        logger.error("ERROR: OPENAI_API_KEY not found in .env file!")
        logger.error("   Please add your OpenAI API key to .env file")
        exit(1)
    
    # Run data ingestion on startup
    # NOTE: Ingestion now managed through RAG API endpoints
    # Use POST /api/rag/documents to add documents
    logger.info("RAG system ready. Use /api/rag/documents endpoint to manage knowledge base.")
    
    # Run Flask app
    logger.info("="*80)
    logger.info("Cyberfortress SmartXDR Core - API Server")
    logger.info("="*80)
    logger.info("Endpoints:")
    logger.info("  AI/RAG:")
    logger.info("    - POST /api/ai/ask       - Ask LLM a question")
    logger.info("    - GET  /api/ai/stats     - Get usage statistics")
    logger.info("    - POST /api/ai/cache/clear - Clear response cache")
    logger.info("  RAG Knowledge Base:")
    logger.info("    - POST /api/rag/documents - Create document")
    logger.info("    - POST /api/rag/documents/batch - Batch create documents")
    logger.info("    - GET  /api/rag/documents - List documents")
    logger.info("    - GET  /api/rag/documents/<id> - Get document by ID")
    logger.info("    - PUT  /api/rag/documents/<id> - Update document")
    logger.info("    - DELETE /api/rag/documents/<id> - Delete document")
    logger.info("    - POST /api/rag/query    - RAG query (search + LLM answer)")
    logger.info("    - GET  /api/rag/stats    - RAG statistics")
    logger.info("  IOC Enrichment:")
    logger.info("    - POST /api/enrich/explain_intelowl - Explain IntelOwl results with AI (single IOC)")
    logger.info("    - POST /api/enrich/explain_case_iocs - Analyze all IOCs in a case with AI")
    logger.info("    - GET /api/enrich/case_ioc_comments - Get SmartXDR comments for case IOCs")
    logger.info("  Triage & Alerts:")
    logger.info("    - POST /api/triage/summarize-alerts - Summarize ML-classified alerts (supports include_ai_analysis=true)")
    logger.info("    - POST /api/triage/send-report-email - Send alert summary via email")
    logger.info("    - POST /api/triage/daily-report/trigger - Manually trigger daily report")
    logger.info("    - GET  /api/triage/health - Check triage service health")
    logger.info("  Telegram:")
    logger.info("    - POST /api/telegram/webhook - Telegram webhook (auto-configured)")
    logger.info("  Health:")
    logger.info("    - GET  /health           - Health check")
    logger.info("="*80)
    
    # Start Cloudflare Tunnel for Telegram webhook
    logger.info("Telegram Integration:")
    bot_enabled = os.getenv("TELEGRAM_BOT_ENABLED", "true").lower() == "true"
    use_tunnel = os.getenv("TELEGRAM_WEBHOOK_ENABLED", "true").lower() == "true"
    
    if not bot_enabled:
        logger.info("Telegram bot DISABLED (set TELEGRAM_BOT_ENABLED=true to enable)")
    elif bot_enabled and os.getenv("TELEGRAM_BOT_TOKEN") and use_tunnel:
        def setup_tunnel_async():
            time.sleep(2)  # Wait for Flask to start
            tunnel_url = start_tunnel(PORT)
            if tunnel_url:
                set_telegram_webhook(tunnel_url)
        
        tunnel_thread = threading.Thread(target=setup_tunnel_async, daemon=True)
        tunnel_thread.start()
        logger.info("Tunnel starting in background...")
    else:
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            logger.warning("TELEGRAM_BOT_TOKEN not set - Telegram disabled")
        else:
            logger.info("Webhook disabled (set TELEGRAM_WEBHOOK_ENABLED=true to enable)")
    
    logger.info("="*80)
    
    app.run(
        host=HOST,
        port=PORT,
        debug=True,
        use_reloader=False  # Disable reloader to prevent duplicate tunnels
    )
