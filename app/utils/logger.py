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
app_logger = setup_logger("smartxdr")

# Service-specific loggers
llm_logger = setup_logger("LLM Service")
rag_logger = setup_logger("RAG Service")
rag_sync_logger = setup_logger("RAG-Sync")
telegram_logger = setup_logger("Telegram")
iris_logger = setup_logger("IRIS")
enrich_logger = setup_logger("Enrich")
alert_logger = setup_logger("Alert")
cache_logger = setup_logger("Cache")
auth_logger = setup_logger("Auth")
