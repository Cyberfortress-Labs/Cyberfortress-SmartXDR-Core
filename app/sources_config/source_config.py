"""
Source Configuration Loader

Loads log source definitions from sources.json config file.
Allows users to easily add new Elasticsearch index patterns without modifying code.
"""
import json
import os
import logging
from typing import Dict, List, Optional, Any
from functools import lru_cache

logger = logging.getLogger(__name__)

# Config file path
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_CONFIG_PATH = os.path.join(CONFIG_DIR, 'sources.json')


class SourceConfig:
    """Manager for log source configurations"""
    
    _instance = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self) -> None:
        """Load configuration from JSON file"""
        try:
            if os.path.exists(SOURCES_CONFIG_PATH):
                with open(SOURCES_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                logger.info(f"Loaded source config from {SOURCES_CONFIG_PATH}")
            else:
                logger.warning(f"Source config not found at {SOURCES_CONFIG_PATH}, using defaults")
                self._config = self._get_default_config()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in sources.json: {e}")
            self._config = self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading source config: {e}")
            self._config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration if file not found"""
        return {
            "aggregated_sources": {
                "all": {"method": "get_combined_alerts_for_daily_report"},
                "elastalert": {"method": "get_elastalert_alerts"},
                "kibana": {"method": "get_kibana_security_alerts"},
                "ml": {"method": "get_ml_predictions"}
            },
            "log_sources": {
                "pfsense": {"index_pattern": "*pfsense*"},
                "suricata": {"index_pattern": "*suricata*"},
                "zeek": {"index_pattern": "*zeek*"},
                "windows": {"index_pattern": "*winlogbeat*"},
                "wazuh": {"index_pattern": "wazuh-alerts-*"},
                "filebeat": {"index_pattern": "filebeat-*"}
            },
            "default_settings": {
                "max_results": 500,
                "default_hours": 24,
                "max_hours": 240
            }
        }
    
    def reload(self) -> None:
        """Reload configuration from file"""
        self._load_config()
        logger.info("Source configuration reloaded")
    
    @property
    def aggregated_sources(self) -> Dict[str, Any]:
        """Get aggregated source definitions"""
        return self._config.get('aggregated_sources', {})
    
    @property
    def log_sources(self) -> Dict[str, Any]:
        """Get log source definitions"""
        return self._config.get('log_sources', {})
    
    @property
    def categories(self) -> Dict[str, str]:
        """Get category definitions"""
        return self._config.get('categories', {})
    
    @property
    def default_settings(self) -> Dict[str, Any]:
        """Get default settings"""
        return self._config.get('default_settings', {})
    
    def get_index_pattern(self, source_name: str) -> Optional[str]:
        """
        Get Elasticsearch index pattern for a source
        
        Args:
            source_name: Name of the log source
            
        Returns:
            Index pattern string or None if not found
        """
        source_name = source_name.lower()
        
        # Check if it's a log source
        if source_name in self.log_sources:
            return self.log_sources[source_name].get('index_pattern')
        
        return None
    
    def is_aggregated_source(self, source_name: str) -> bool:
        """Check if source is an aggregated source (needs special handling)"""
        return source_name.lower() in self.aggregated_sources
    
    def get_aggregated_method(self, source_name: str) -> Optional[str]:
        """Get the method name for an aggregated source"""
        source_name = source_name.lower()
        if source_name in self.aggregated_sources:
            return self.aggregated_sources[source_name].get('method')
        return None
    
    def get_all_source_names(self) -> List[str]:
        """Get list of all available source names"""
        aggregated = [k for k in self.aggregated_sources.keys() if not k.startswith('_')]
        log_sources = [k for k in self.log_sources.keys() if not k.startswith('_')]
        return aggregated + log_sources
    
    def get_sources_by_category(self, category: str) -> List[str]:
        """Get all sources in a specific category"""
        return [
            name for name, config in self.log_sources.items()
            if not name.startswith('_') and config.get('category') == category
        ]
    
    def get_source_info(self, source_name: str) -> Optional[Dict[str, Any]]:
        """Get full info about a source"""
        source_name = source_name.lower()
        
        if source_name in self.aggregated_sources:
            return {
                'type': 'aggregated',
                **self.aggregated_sources[source_name]
            }
        
        if source_name in self.log_sources:
            return {
                'type': 'log_source',
                **self.log_sources[source_name]
            }
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary"""
        return {
            'aggregated': list(self.aggregated_sources.keys()),
            'log_sources': {
                name: config.get('index_pattern')
                for name, config in self.log_sources.items()
                if not name.startswith('_')
            },
            'categories': self.categories
        }


# Singleton instance
source_config = SourceConfig()


def get_source_config() -> SourceConfig:
    """Get the singleton SourceConfig instance"""
    return source_config


def reload_source_config() -> None:
    """Reload source configuration from file"""
    source_config.reload()
