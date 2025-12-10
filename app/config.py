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


# Database settings
DB_PATH = str(PROJECT_ROOT / "chroma_db")
COLLECTION_NAME = "soc_ecosystem"
CHROMA_DB_PATH = DB_PATH  # Alias for RAG module

# OpenAI model settings
EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-5-mini"  # OpenAI's efficient small model
# Note: gpt-4o-mini supports temperature 0-2

# OpenAI client configuration (following best practices)
# https://platform.openai.com/docs/api-reference
OPENAI_TIMEOUT = 600.0  # 10 minutes default timeout
OPENAI_MAX_RETRIES = 2  # Default retry count for failed requests

# Query settings
DEFAULT_RESULTS = 10  # Increased for better MITRE ATT&CK technique retrieval

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

# Risk Score Formula: risk_score = (alert_count * COUNT_WEIGHT) + (avg_probability * PROBABILITY_WEIGHT) + (severity_level * SEVERITY_WEIGHT) + (escalation_level * ESCALATION_WEIGHT)
# Where severity_level: INFO=1, WARNING=2, ERROR=3
# And escalation_level: 0=none, 1=single pattern, 2=sequence (scan→brute-force→lateral movement)
RISK_SCORE_COUNT_WEIGHT = 0.3  # Weight for alert count
RISK_SCORE_PROBABILITY_WEIGHT = 0.35  # Weight for ML prediction probability
RISK_SCORE_SEVERITY_WEIGHT = 0.25  # Weight for severity level
RISK_SCORE_ESCALATION_WEIGHT = 0.1  # Weight for attack pattern escalation

# Elasticsearch settings for alert summarization
ALERT_MIN_PROBABILITY = 0.7  # Minimum ML prediction probability threshold
ALERT_MIN_SEVERITY = "WARNING"  # Minimum severity level (INFO, WARNING, ERROR)
ALERT_SOURCE_TYPES = ["suricata", "zeek", "pfsense", "modsecurity", "apache", "nginx", "mysql", "windows", "wazuh"]
