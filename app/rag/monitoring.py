"""
RAG Monitoring & Logging Utilities

Provides comprehensive logging and metrics tracking for RAG operations.
"""
import time
from app.utils.logger import rag_monitoring_logger as logger
from typing import Dict, Any, Optional
from functools import wraps
from datetime import datetime

class RAGMetricsTracker:
    """Track RAG operation metrics"""
    
    def __init__(self):
        self.metrics = {
            "documents": {
                "added": 0,
                "updated": 0,
                "deleted": 0,
                "errors": 0
            },
            "queries": {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "cached": 0,
                "avg_latency_ms": 0.0,
                "total_latency_ms": 0.0
            },
            "cache": {
                "hits": 0,
                "misses": 0,
                "hit_rate": 0.0
            },
            "errors": {
                "validation": 0,
                "database": 0,
                "llm": 0,
                "other": 0
            }
        }
        self.start_time = datetime.utcnow()
    
    def record_document_added(self, count: int = 1):
        """Record document addition"""
        self.metrics["documents"]["added"] += count
        logger.info(f"Document(s) added: count={count}, total={self.metrics['documents']['added']}")
    
    def record_document_updated(self):
        """Record document update"""
        self.metrics["documents"]["updated"] += 1
        logger.info(f"Document updated: total={self.metrics['documents']['updated']}")
    
    def record_document_deleted(self):
        """Record document deletion"""
        self.metrics["documents"]["deleted"] += 1
        logger.info(f"Document deleted: total={self.metrics['documents']['deleted']}")
    
    def record_query(self, latency_ms: float, success: bool, cached: bool = False):
        """Record query execution"""
        self.metrics["queries"]["total"] += 1
        
        if success:
            self.metrics["queries"]["successful"] += 1
        else:
            self.metrics["queries"]["failed"] += 1
        
        if cached:
            self.metrics["queries"]["cached"] += 1
            self.metrics["cache"]["hits"] += 1
        else:
            self.metrics["cache"]["misses"] += 1
        
        # Update average latency
        total_latency = self.metrics["queries"]["total_latency_ms"] + latency_ms
        self.metrics["queries"]["total_latency_ms"] = total_latency
        self.metrics["queries"]["avg_latency_ms"] = total_latency / self.metrics["queries"]["total"]
        
        # Update cache hit rate
        total_cache_ops = self.metrics["cache"]["hits"] + self.metrics["cache"]["misses"]
        if total_cache_ops > 0:
            self.metrics["cache"]["hit_rate"] = self.metrics["cache"]["hits"] / total_cache_ops
        
        logger.info(f"Query recorded: latency={latency_ms:.2f}ms, success={success}, cached={cached}")
    
    def record_error(self, error_type: str):
        """Record error occurrence"""
        if error_type in self.metrics["errors"]:
            self.metrics["errors"][error_type] += 1
        else:
            self.metrics["errors"]["other"] += 1
        
        logger.warning(f"Error recorded: type={error_type}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        return {
            **self.metrics,
            "uptime_seconds": uptime,
            "start_time": self.start_time.isoformat()
        }
    
    def reset(self):
        """Reset all metrics"""
        self.__init__()
        logger.warning("Metrics reset")

# Global metrics tracker instance
_metrics_tracker = RAGMetricsTracker()

def get_metrics_tracker() -> RAGMetricsTracker:
    """Get global metrics tracker instance"""
    return _metrics_tracker

def log_operation(operation_name: str):
    """
    Decorator to log RAG operations with timing
    
    Usage:
        @log_operation("add_document")
        def add_document(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            logger.info(f"[{operation_name}] Starting operation")
            
            try:
                result = func(*args, **kwargs)
                
                elapsed_ms = (time.time() - start_time) * 1000
                logger.info(f"[{operation_name}] Completed in {elapsed_ms:.2f}ms")
                
                return result
                
            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                logger.error(f"[{operation_name}] Failed after {elapsed_ms:.2f}ms: {str(e)}", exc_info=True)
                raise
        
        return wrapper
    return decorator

def log_query(func):
    """
    Decorator specifically for query operations
    Tracks detailed query metrics
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        
        # Extract query text if available
        query_text = kwargs.get('query', args[1] if len(args) > 1 else 'unknown')
        query_preview = query_text[:100] if isinstance(query_text, str) else str(query_text)[:100]
        
        logger.info(f"[QUERY] Starting: '{query_preview}...'")
        
        try:
            result = func(*args, **kwargs)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Check if cached
            cached = result.get('cached', False) if isinstance(result, dict) else False
            success = result.get('status', 'error') == 'success' if isinstance(result, dict) else True
            
            # Record metrics
            get_metrics_tracker().record_query(elapsed_ms, success, cached)
            
            logger.info(
                f"[QUERY] Completed: '{query_preview}...' | "
                f"time={elapsed_ms:.2f}ms | cached={cached} | success={success}"
            )
            
            return result
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            
            get_metrics_tracker().record_query(elapsed_ms, success=False)
            get_metrics_tracker().record_error("query_error")
            
            logger.error(
                f"[QUERY] Failed: '{query_preview}...' | "
                f"time={elapsed_ms:.2f}ms | error={str(e)}",
                exc_info=True
            )
            raise
    
    return wrapper

def setup_rag_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """
    Setup comprehensive RAG logging
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
    """
    # Create logger
    rag_logger = logging.getLogger('smartxdr.rag')
    rag_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Format
    formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    rag_logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        rag_logger.addHandler(file_handler)
    
    rag_logger.info(f"RAG logging initialized: level={log_level}, file={log_file}")
