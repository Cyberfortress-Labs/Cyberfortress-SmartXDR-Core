"""
Configuration file for RAG system constants
Following OpenAI Python SDK best practices
"""
import os
from pathlib import Path

# Debug Mode
DEBUG_MODE = True  # Set to False in production to reduce console output


# Get project root directory (assumes this file is in app/config.py)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Network settings
PORT=8080
HOST='0.0.0.0'

# Directory paths (now absolute)
ASSETS_DIR = str(PROJECT_ROOT / "assets")
ECOSYSTEM_DIR = os.path.join(ASSETS_DIR, "ecosystem")
NETWORK_DIR = os.path.join(ASSETS_DIR, "network")
ARCH_DIR = os.path.join(ASSETS_DIR, "architecture")
MITRE_DIR = os.path.join(ASSETS_DIR, "mitre-attck")


# Database settings
DB_PATH = str(PROJECT_ROOT / "chroma_db")
COLLECTION_NAME = "soc_ecosystem"

# OpenAI model settings
EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-5-mini"
# Note: gpt-5-mini only supports temperature=1 (default), custom values not allowed

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
