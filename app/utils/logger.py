"""
Logger utility for SmartXDR
Provides standardized logging across all services
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


class FlushStreamHandler(logging.StreamHandler):
    """StreamHandler that flushes after each emit for Docker compatibility"""
    def emit(self, record):
        super().emit(record)
        self.flush()


def setup_logger(name: str, log_level: str = None, log_file: str = None) -> logging.Logger:
    """
    Set up a logger with console and optional file handlers
    
    Args:
        name: Logger name (will be shown in logs as [name])
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        
    Returns:
        Configured logger instance
    """
    # Get log level from environment or parameter
    level_str = log_level or os.getenv("LOG_LEVEL", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    # Prevent propagation to root logger (avoid duplicate logs)
    logger.propagate = False
    
    # Create formatter - standardized format for all services
    formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler with flush for Docker
    console_handler = FlushStreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not create file handler: {e}")
    
    return logger


def get_logger(name: str = "smartxdr") -> logging.Logger:
    """Get or create a logger with default settings"""
    return setup_logger(name)


# ============================================================================
# Pre-configured loggers for main services
# Import directly: from app.utils.logger import llm_logger, rag_logger, etc.
# ============================================================================

# Main application logger
app_logger = setup_logger("smartxdr.app")

# Services
llm_logger = setup_logger("smartxdr.llm")
rag_service_logger = setup_logger("smartxdr.rag.service")
rag_sync_logger = setup_logger("smartxdr.rag.sync")
telegram_logger = setup_logger("smartxdr.telegram")
iris_logger = setup_logger("smartxdr.iris")
enrich_logger = setup_logger("smartxdr.enrich")
alert_logger = setup_logger("smartxdr.alert")

# RAG module
rag_repository_logger = setup_logger("smartxdr.rag.repository")
rag_monitoring_logger = setup_logger("smartxdr.rag.monitoring")

# Core module  
database_logger = setup_logger("smartxdr.database")
chunking_logger = setup_logger("smartxdr.chunking")
ingestion_logger = setup_logger("smartxdr.ingestion")
query_logger = setup_logger("smartxdr.query")
pdf_logger = setup_logger("smartxdr.pdf")
openai_logger = setup_logger("smartxdr.openai")

# Routes
ai_route_logger = setup_logger("smartxdr.routes.ai")
rag_route_logger = setup_logger("smartxdr.routes.rag")
telegram_route_logger = setup_logger("smartxdr.routes.telegram")
ioc_route_logger = setup_logger("smartxdr.routes.ioc")
triage_route_logger = setup_logger("smartxdr.routes.triage")

# Middleware & Utils
auth_logger = setup_logger("smartxdr.auth")
cache_logger = setup_logger("smartxdr.cache")
redis_logger = setup_logger("smartxdr.redis")

# Conversation & Memory
conversation_logger = setup_logger("smartxdr.conversation")

# Elasticsearch
es_logger = setup_logger("smartxdr.elasticsearch")

# Email
email_logger = setup_logger("smartxdr.email")

# Daily report
scheduler_logger = setup_logger("smartxdr.scheduler")

# Prompt builder
prompt_logger = setup_logger("smartxdr.prompt")

# Telegram service
telegram_service_logger = setup_logger("smartxdr.telegram.service")
