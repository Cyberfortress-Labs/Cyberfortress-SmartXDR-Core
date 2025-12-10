"""
API Authentication Middleware for SmartXDR
Supports: API Key, IP Whitelist, Rate Limiting, Permission System
"""
import os
import json
import functools
import hashlib
import secrets
from flask import request, jsonify, g
from typing import Optional, Callable
from datetime import datetime
import logging

logger = logging.getLogger('smartxdr.auth')


class APIKeyManager:
    """Manage API keys for SmartXDR"""
    
    def __init__(self):
        # Check if auth is enabled
        self.auth_enabled = os.getenv('API_AUTH_ENABLED', 'true').lower() == 'true'
        
        # Load from environment
        self.master_key = os.getenv('SMARTXDR_MASTER_API_KEY', '')
        
        # Additional keys can be added here or loaded from DB
        self._valid_keys = self._load_keys()
        
        # Rate limiting tracker
        self._request_counts = {}
        
        # IP Whitelist (optional)
        whitelist_str = os.getenv('API_IP_WHITELIST', '')
        self.ip_whitelist = [ip.strip() for ip in whitelist_str.split(',') if ip.strip()]
        
        # Public endpoints (no auth required)
        public_str = os.getenv('API_PUBLIC_ENDPOINTS', '/api/health,/api/telegram/webhook,/api/triage/health')
        self.public_endpoints = [ep.strip() for ep in public_str.split(',') if ep.strip()]
        
        if not self.auth_enabled:
            logger.warning("⚠️  API Authentication is DISABLED! All endpoints are public.")
        else:
            logger.info(f"🔐 API Authentication enabled with {len(self._valid_keys)} keys")
        
    def _load_keys(self) -> dict:
        """Load valid API keys with their permissions"""
        keys = {}
        
        # Master key - full access
        if self.master_key and self.master_key != 'sxdr_CHANGE_THIS_MASTER_KEY':
            keys[self._hash_key(self.master_key)] = {
                'name': 'master',
                'permissions': ['*'],  # All permissions
                'rate_limit': 1000  # requests per minute
            }
            logger.info("✓ Master API key loaded")
        
        # Load API keys from JSON config in env
        api_keys_json = os.getenv('API_KEYS', '{}')
        try:
            api_keys_config = json.loads(api_keys_json)
            for key, config in api_keys_config.items():
                if key and not key.endswith('CHANGE_THIS'):
                    keys[self._hash_key(key)] = {
                        'name': config.get('name', 'unnamed'),
                        'permissions': config.get('permissions', ['ai:ask']),
                        'rate_limit': config.get('rate_limit', 60)
                    }
            logger.info(f"✓ Loaded {len(api_keys_config)} API keys from config")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse API_KEYS JSON: {e}")
        
        return keys
    
    def _hash_key(self, key: str) -> str:
        """Hash API key for secure storage/comparison"""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def validate_key(self, api_key: str) -> Optional[dict]:
        """Validate API key and return key info if valid"""
        if not api_key:
            return None
        
        key_hash = self._hash_key(api_key)
        return self._valid_keys.get(key_hash)
    
    def check_permission(self, key_info: dict, required_permission: str) -> bool:
        """Check if key has required permission"""
        permissions = key_info.get('permissions', [])
        
        # Wildcard - full access
        if '*' in permissions:
            return True
        
        # Exact match
        if required_permission in permissions:
            return True
        
        # Prefix match (e.g., 'enrich:*' matches 'enrich:explain')
        for perm in permissions:
            if perm.endswith(':*'):
                prefix = perm[:-1]  # Remove '*'
                if required_permission.startswith(prefix):
                    return True
        
        return False
    
    def check_ip_whitelist(self, client_ip: str) -> bool:
        """Check if client IP is in whitelist"""
        if not self.ip_whitelist:
            return True  # No whitelist = allow all
        
        # Check exact match or wildcard
        for allowed_ip in self.ip_whitelist:
            if allowed_ip == client_ip:
                return True
            # Simple subnet check (e.g., 10.10.21.*)
            if allowed_ip.endswith('.*'):
                prefix = allowed_ip[:-1]
                if client_ip.startswith(prefix):
                    return True
        
        return False
    
    def is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public (no auth required)"""
        for endpoint in self.public_endpoints:
            if path.startswith(endpoint):
                return True
        return False
    
    def check_rate_limit(self, key_name: str, limit: int) -> bool:
        """Simple rate limiting per minute"""
        now = datetime.now()
        minute_key = f"{key_name}:{now.strftime('%Y%m%d%H%M')}"
        
        count = self._request_counts.get(minute_key, 0)
        if count >= limit:
            return False
        
        self._request_counts[minute_key] = count + 1
        
        # Cleanup old entries (keep only last 5 minutes)
        current_minute = now.strftime('%Y%m%d%H%M')
        old_keys = [k for k in list(self._request_counts.keys()) 
                    if not k.endswith(current_minute)]
        for k in old_keys[:max(0, len(old_keys) - 5)]:
            del self._request_counts[k]
        
        return True
    
    def reload_keys(self):
        """Reload API keys from environment"""
        self.master_key = os.getenv('SMARTXDR_API_KEY', '')
        self.iris_key = os.getenv('IRIS_API_KEY_FOR_SMARTXDR', '')
        self._valid_keys = self._load_keys()
        logger.info("API keys reloaded")
    
    @staticmethod
    def generate_key(prefix: str = "sxdr") -> str:
        """Generate a new API key"""
        return f"{prefix}_{secrets.token_urlsafe(32)}"


# Singleton instance
_api_key_manager = None

def get_api_key_manager() -> APIKeyManager:
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
    return _api_key_manager


def require_api_key(permission_or_func=None):
    """
    Decorator to require API key authentication
    
    Usage:
        @require_api_key  # Just require valid key (no parentheses)
        @require_api_key()  # Just require valid key (with parentheses)
        @require_api_key('ai:ask')  # Require specific permission
        @require_api_key('enrich:*')  # Require enrich permission
    
    Headers accepted:
        X-API-Key: your_api_key
        Authorization: Bearer your_api_key
    """
    # Handle both @require_api_key and @require_api_key()
    if callable(permission_or_func):
        # Called without parentheses: @require_api_key
        func = permission_or_func
        permission = None
        
        @functools.wraps(func)
        def api_key_protected_function(*args, **kwargs):
            manager = get_api_key_manager()
            
            # If auth is disabled, allow all requests
            if not manager.auth_enabled:
                g.api_key_info = {'name': 'auth_disabled', 'permissions': ['*']}
                g.api_key_name = 'auth_disabled'
                return func(*args, **kwargs)
            
            # Check if public endpoint
            if manager.is_public_endpoint(request.path):
                return func(*args, **kwargs)
            
            # Get client IP
            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr) or '0.0.0.0'
            if ',' in client_ip:
                client_ip = client_ip.split(',')[0].strip()
            
            # Check IP whitelist first (if configured)
            if not manager.check_ip_whitelist(client_ip):
                logger.warning(f"IP not in whitelist: {client_ip}")
                return jsonify({
                    'status': 'error',
                    'message': 'Access denied: IP not allowed',
                    'code': 'IP_BLOCKED'
                }), 403
            
            # Get API key from header
            api_key = (
                request.headers.get('X-API-Key') or 
                request.headers.get('Authorization', '').replace('Bearer ', '')
            )
            
            # Validate key
            key_info = manager.validate_key(api_key)
            if not key_info:
                logger.warning(f"Invalid API key attempt from {client_ip}")
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid or missing API key',
                    'code': 'INVALID_API_KEY',
                    'hint': 'Include header: X-API-Key: your_api_key'
                }), 401
            
            # Check permission
            if permission and not manager.check_permission(key_info, permission):
                logger.warning(f"Permission denied for {key_info['name']}: {permission}")
                return jsonify({
                    'status': 'error',
                    'message': f"Permission denied: {permission}",
                    'code': 'PERMISSION_DENIED'
                }), 403
            
            # Check rate limit
            if not manager.check_rate_limit(key_info['name'], key_info.get('rate_limit', 60)):
                logger.warning(f"Rate limit exceeded for {key_info['name']}")
                return jsonify({
                    'status': 'error',
                    'message': 'Rate limit exceeded. Please slow down.',
                    'code': 'RATE_LIMIT_EXCEEDED'
                }), 429
            
            # Store key info in request context
            g.api_key_info = key_info
            g.api_key_name = key_info['name']
            
            return func(*args, **kwargs)
        return api_key_protected_function
    
    else:
        # Called with parentheses: @require_api_key() or @require_api_key('permission')
        permission = permission_or_func
        
        def api_key_decorator(f: Callable):
            @functools.wraps(f)
            def api_key_protected_function(*args, **kwargs):
                manager = get_api_key_manager()
                
                # If auth is disabled, allow all requests
                if not manager.auth_enabled:
                    g.api_key_info = {'name': 'auth_disabled', 'permissions': ['*']}
                    g.api_key_name = 'auth_disabled'
                    return f(*args, **kwargs)
                
                # Check if public endpoint
                if manager.is_public_endpoint(request.path):
                    return f(*args, **kwargs)
                
                # Get client IP
                client_ip = request.headers.get('X-Forwarded-For', request.remote_addr) or '0.0.0.0'
                if ',' in client_ip:
                    client_ip = client_ip.split(',')[0].strip()
                
                # Check IP whitelist first (if configured)
                if not manager.check_ip_whitelist(client_ip):
                    logger.warning(f"IP not in whitelist: {client_ip}")
                    return jsonify({
                        'status': 'error',
                        'message': 'Access denied: IP not allowed',
                        'code': 'IP_BLOCKED'
                    }), 403
                
                # Get API key from header
                api_key = (
                    request.headers.get('X-API-Key') or 
                    request.headers.get('Authorization', '').replace('Bearer ', '')
                )
                
                # Validate key
                key_info = manager.validate_key(api_key)
                if not key_info:
                    logger.warning(f"Invalid API key attempt from {client_ip}")
                    return jsonify({
                        'status': 'error',
                        'message': 'Invalid or missing API key',
                        'code': 'INVALID_API_KEY',
                        'hint': 'Include header: X-API-Key: your_api_key'
                    }), 401
                
                # Check permission
                if permission and not manager.check_permission(key_info, permission):
                    logger.warning(f"Permission denied for {key_info['name']}: {permission}")
                    return jsonify({
                        'status': 'error',
                        'message': f"Permission denied: {permission}",
                        'code': 'PERMISSION_DENIED'
                    }), 403
                
                # Check rate limit
                if not manager.check_rate_limit(key_info['name'], key_info.get('rate_limit', 60)):
                    logger.warning(f"Rate limit exceeded for {key_info['name']}")
                    return jsonify({
                        'status': 'error',
                        'message': 'Rate limit exceeded. Please slow down.',
                        'code': 'RATE_LIMIT_EXCEEDED'
                    }), 429
                
                # Store key info in request context
                g.api_key_info = key_info
                g.api_key_name = key_info['name']
                
                return f(*args, **kwargs)
            return api_key_protected_function
        return api_key_decorator


def optional_api_key():
    """
    Decorator for endpoints that work with or without API key
    If key provided, validates it. If not, allows anonymous access.
    """
    def decorator(f: Callable):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            manager = get_api_key_manager()
            
            api_key = (
                request.headers.get('X-API-Key') or 
                request.headers.get('Authorization', '').replace('Bearer ', '')
            )
            
            if api_key:
                key_info = manager.validate_key(api_key)
                if key_info:
                    g.api_key_info = key_info
                    g.api_key_name = key_info['name']
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Invalid API key',
                        'code': 'INVALID_API_KEY'
                    }), 401
            else:
                g.api_key_info = None
                g.api_key_name = 'anonymous'
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
