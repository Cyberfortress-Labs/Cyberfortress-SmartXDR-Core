"""
Shared OpenAI Client Singleton

Tạo một instance duy nhất của OpenAI client để tái sử dụng
thay vì tạo nhiều clients trong các modules khác nhau.

Usage:
    from app.core.openai_client import get_openai_client
    client = get_openai_client()
    response = client.chat.completions.create(...)
"""
import os
import logging
from openai import OpenAI
from dotenv import load_dotenv
from app.config import OPENAI_TIMEOUT, OPENAI_MAX_RETRIES

# Load environment variables
load_dotenv()

logger = logging.getLogger('smartxdr.openai')

# Singleton instance
_openai_client: OpenAI = None


def get_openai_client() -> OpenAI:
    """
    Get or create the shared OpenAI client singleton.
    
    Returns:
        OpenAI: Configured OpenAI client instance
    
    Raises:
        ValueError: If OPENAI_API_KEY is not set
    """
    global _openai_client
    
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        _openai_client = OpenAI(
            api_key=api_key,
            timeout=OPENAI_TIMEOUT,
            max_retries=OPENAI_MAX_RETRIES
        )
        logger.info("OpenAI client initialized")
    
    return _openai_client


def reset_client():
    """Reset the client (useful for testing or config changes)"""
    global _openai_client
    _openai_client = None
    logger.info("OpenAI client reset")
