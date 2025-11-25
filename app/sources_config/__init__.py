"""
Sources Configuration package for Cyberfortress SmartXDR Core

Provides externalized configuration for:
- Source definitions (Elasticsearch indices)
- Log source mappings
"""

from .source_config import SourceConfig, get_source_config, reload_source_config

__all__ = ['SourceConfig', 'get_source_config', 'reload_source_config']
