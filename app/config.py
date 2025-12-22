"""
Configuration file for RAG system constants
Following OpenAI Python SDK best practices
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Debug Mode - Configurable via .env
DEBUG_MODE = os.environ.get('DEBUG', 'false').lower() in ('true', '1', 'yes')
DEBUG_LLM = os.environ.get('DEBUG_LLM', 'false').lower() in ('true', '1', 'yes')


# Get project root directory (assumes this file is in app/config.py)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Network settings
PORT = 8080
HOST = '0.0.0.0'

# Directory paths (now absolute)
ASSETS_DIR = str(PROJECT_ROOT / "assets")
ECOSYSTEM_DIR = os.path.join(ASSETS_DIR, "ecosystem")
NETWORK_DIR = os.path.join(ASSETS_DIR, "network")
ARCH_DIR = os.path.join(ASSETS_DIR, "architecture")
MITRE_DIR = os.path.join(ASSETS_DIR, "mitre-attck")

# New RAG data source directories
PLAYBOOKS_DIR = os.path.join(ASSETS_DIR, "playbooks")
KNOWLEDGE_BASE_DIR = os.path.join(ASSETS_DIR, "knowledge_base")
POLICIES_DIR = os.path.join(ASSETS_DIR, "policies")


# Database settings (all in db/ directory)
DB_DIR = str(PROJECT_ROOT / "db")
DB_PATH = str(PROJECT_ROOT / "db" / "chroma_db")  # RAG knowledge base
CONV_DB_PATH = str(PROJECT_ROOT / "db" / "chroma_conv")  # Conversation history
APP_DATA_PATH = str(PROJECT_ROOT / "db" / "app_data")  # SQLite and other data

COLLECTION_NAME = "soc_ecosystem"
CONVERSATION_COLLECTION_NAME = "conversation_history"  # For conversation memory
CHROMA_DB_PATH = DB_PATH  # Alias for RAG module (local mode)

# ChromaDB HTTP Client settings (Docker mode)
CHROMA_HOST = os.environ.get('CHROMA_HOST', None)  # Set to 'chromadb' in Docker
CHROMA_PORT = int(os.environ.get('CHROMA_PORT', '8000'))

# Time to send daily report (24-hour format, HH:MM)
DAILY_REPORT_TIME = os.environ.get('DAILY_REPORT_TIME', '07:00')

# Timezone Offset (default to 0 if not set)
TIMEZONE_OFFSET = int(os.environ.get('TIMEZONE_OFFSET', '0'))

# OpenAI model settings (from .env with defaults)
EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')
CHAT_MODEL = os.environ.get('CHAT_MODEL', 'gpt-5-mini')
SUMMARY_MODEL = os.environ.get('SUMMARY_MODEL', 'gpt-5-mini')
# OpenAI client configuration (following best practices)
# https://platform.openai.com/docs/api-reference
OPENAI_TIMEOUT = 600.0  # 10 minutes default timeout
OPENAI_MAX_RETRIES = 2  # Default retry count for failed requests
TELEGRAM_API_TIMEOUT = int(os.environ.get('TELEGRAM_API_TIMEOUT', '300'))  # Telegram middleware timeout (5 min default)

# Query settings
DEFAULT_RESULTS = 25  # topK: Increased for better context coverage (was 10)

# RAG Chunking settings
MIN_CHUNK_SIZE = 100  # Minimum chars per chunk (avoid too short chunks)
MAX_CHUNK_SIZE = 2000  # Maximum chars per chunk
MIN_BATCH_SIZE = 50  # Minimum batch size for embedding
BATCH_SIZE = 100  # Maximum batch size for embedding (reduced for OpenAI token limits)
MAX_CONTEXT_CHARS = 3000 
DEBUG_TEXT_LENGTH=1000

# Token pricing (per 1M tokens)
INPUT_PRICE_PER_1M = 0.25
OUTPUT_PRICE_PER_1M = 1

# API Safety & Cost Control
MAX_CALLS_PER_MINUTE = 20  # Rate limit: max API calls per minute
MAX_DAILY_COST = 1.0  # Maximum spend per day in USD
CACHE_ENABLED = True  # Enable response caching to reduce duplicate calls
CACHE_TTL = 3600  # Cache time-to-live in seconds (1 hour)
SEMANTIC_CACHE_ENABLED = True  # Enable embedding-based semantic similarity for cache lookup

# ===== Smart Alert Summarization Settings =====
# Time window for alert grouping (in minutes)
# Default: 10080 minutes = 7 days, configurable via environment variable
# Supports: plain number (10080) or with suffix (7d, 10h, 60m)
def _parse_time_window(value_str: str) -> int:
    """Parse time window with optional suffix (d=days, h=hours, m=minutes)"""
    value_str = value_str.strip().lower()
    
    # Handle suffixes
    if value_str.endswith('d'):
        return int(value_str[:-1]) * 1440  # days to minutes
    elif value_str.endswith('h'):
        return int(value_str[:-1]) * 60    # hours to minutes
    elif value_str.endswith('m'):
        return int(value_str[:-1])          # already in minutes
    else:
        return int(value_str)               # assume minutes

ALERT_TIME_WINDOW = _parse_time_window(os.environ.get('ALERT_TIME_WINDOW', '7d'))

# Risk Score Formula (Optimized - Nov 2024):
# base_score = 0.5 (always starts here)
# volume_score = log10(total_alerts + 1) * 15  (logarithmic scaling)
# severity_score = (ERROR% * 30) + (WARNING% * 15) + (INFO% * 5)
# confidence_score = avg_ML_probability * 25
# escalation_score = escalation_level * 15  (0=none, 1=single, 2=sequence)
# Final: min(base + volume + severity + confidence + escalation, 100)
#
# This prevents easy 100 scores from high WARNING counts
# Examples:
#   100 INFO (70% conf) → ~20 score
#   100 WARNING (90% conf) → ~50 score  
#   50 ERROR (95% conf) + escalation → ~85 score
RISK_SCORE_COUNT_WEIGHT = 0.3  # [DEPRECATED] Kept for backward compatibility
RISK_SCORE_PROBABILITY_WEIGHT = 0.35  # [DEPRECATED]
RISK_SCORE_SEVERITY_WEIGHT = 0.25  # [DEPRECATED]
RISK_SCORE_ESCALATION_WEIGHT = 0.1  # [DEPRECATED]

# Elasticsearch settings for alert summarization
ALERT_MIN_PROBABILITY = 0.5  # Minimum ML prediction probability threshold (lowered to include INFO alerts)
ALERT_MIN_SEVERITY = "INFO"  # Minimum severity level (INFO, WARNING, ERROR)
ALERT_SOURCE_TYPES = ["suricata", "zeek", "pfsense", "modsecurity", "apache", "nginx", "mysql", "windows", "wazuh"]

# IP Whitelist for triage queries - these IPs will be excluded from /summary, /sumlogs results
# Use comma-separated list in .env: WHITELIST_IP_QUERY=192.168.1.1,192.168.1.2,10.0.0.1
_whitelist_str = os.environ.get('WHITELIST_IP_QUERY', '')
WHITELIST_IP_QUERY = set(ip.strip() for ip in _whitelist_str.split(',') if ip.strip())
