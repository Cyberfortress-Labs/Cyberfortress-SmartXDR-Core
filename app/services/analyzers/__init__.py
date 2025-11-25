"""
Analyzer Handlers - Extensible system for IntelOwl analyzer processing

Để thêm analyzer mới, tạo file mới trong folder này và implement BaseAnalyzerHandler.
Analyzer sẽ tự động được register khi import.

Example:
    # app/services/analyzers/shodan_handler.py
    from . import BaseAnalyzerHandler, register_analyzer
    
    @register_analyzer('shodan')
    class ShodanHandler(BaseAnalyzerHandler):
        def extract_stats(self, report: dict) -> dict:
            return {"open_ports": report.get('ports', [])}
        
        def summarize(self, analyzer: dict) -> dict:
            return {"analyzer": "Shodan", "ports": ...}
        
        def get_risk_score(self, report: dict) -> int:
            return 50 if report.get('ports') else 0
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class BaseAnalyzerHandler(ABC):
    """
    Base class cho tất cả analyzer handlers.
    
    Implement class này để thêm support cho analyzer mới.
    """
    
    # Tên hiển thị của analyzer
    display_name: str = "Unknown Analyzer"
    
    # Priority cho sorting (cao hơn = quan trọng hơn)
    priority: int = 50
    
    @abstractmethod
    def extract_stats(self, report: dict) -> dict:
        """
        Extract key statistics từ raw report.
        
        Args:
            report: Raw report data từ analyzer
            
        Returns:
            dict với các stats quan trọng (keep minimal for token optimization)
        """
        pass
    
    @abstractmethod
    def summarize(self, analyzer: dict) -> dict:
        """
        Tóm tắt analyzer report thành format ngắn gọn cho LLM.
        
        Args:
            analyzer: Full analyzer object với 'name', 'report', 'status'
            
        Returns:
            dict với summary (target: 50-100 tokens)
        """
        pass
    
    @abstractmethod
    def get_risk_score(self, report: dict) -> int:
        """
        Tính risk score từ report (0-100).
        
        Args:
            report: Raw report data
            
        Returns:
            int: 0 (clean) -> 100 (critical)
        """
        pass
    
    def is_malicious(self, report: dict) -> bool:
        """
        Quick check xem report có malicious không.
        Default: risk_score > 50
        """
        return self.get_risk_score(report) > 50


# Registry để lưu tất cả analyzer handlers
_analyzer_registry: Dict[str, BaseAnalyzerHandler] = {}


def register_analyzer(name: str):
    """
    Decorator để register analyzer handler.
    
    Usage:
        @register_analyzer('virustotal')
        class VirusTotalHandler(BaseAnalyzerHandler):
            ...
    """
    def decorator(cls):
        if not issubclass(cls, BaseAnalyzerHandler):
            raise TypeError(f"{cls.__name__} must inherit from BaseAnalyzerHandler")
        
        _analyzer_registry[name.lower()] = cls()
        return cls
    
    return decorator


def get_handler(analyzer_name: str) -> Optional[BaseAnalyzerHandler]:
    """
    Lấy handler cho analyzer dựa trên tên.
    
    Args:
        analyzer_name: Tên analyzer (case-insensitive, partial match)
        
    Returns:
        Handler instance hoặc None nếu không tìm thấy
    """
    name_lower = analyzer_name.lower()
    
    # Exact match first
    if name_lower in _analyzer_registry:
        return _analyzer_registry[name_lower]
    
    # Partial match
    for key, handler in _analyzer_registry.items():
        if key in name_lower:
            return handler
    
    return None


def get_all_handlers() -> Dict[str, BaseAnalyzerHandler]:
    """
    Lấy tất cả registered handlers.
    """
    return _analyzer_registry.copy()


def get_registered_analyzer_names() -> List[str]:
    """
    Lấy danh sách tên các analyzers đã register.
    """
    return list(_analyzer_registry.keys())


# Auto-import all handlers trong folder này
from . import virustotal_handler
from . import misp_handler
# Thêm import mới ở đây khi có analyzer mới
# from . import shodan_handler
# from . import abuseipdb_handler
