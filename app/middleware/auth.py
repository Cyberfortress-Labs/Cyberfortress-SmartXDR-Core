"""
API Authentication Middleware for SmartXDR
Supports: API Key (DB-backed), IP Whitelist, Rate Limiting, Permission System
"""
import os
import functools
import json
from flask import request, jsonify, g
from typing import Optional, Callable
from datetime import datetime

from app.models.db_models import db, APIKeyModel
from app.utils.cryptography import verify_api_key
from app.utils.logger import auth_logger as logger


class APIKeyManager:
    """Manage API keys for SmartXDR (SQLAlchemy-backed)"""
    
    def __init__(self):
        # Check if auth is enabled
        self.auth_enabled = os.getenv('API_AUTH_ENABLED', 'true').lower() == 'true'
        
        # Rate limiting tracker (in-memory for now - TODO: move to Redis)
        self._request_counts = {}
        
        # Initialize Redis for API key caching
        self._redis = None
        self._init_redis()
        
        # IP Whitelist (optional)
        whitelist_str = os.getenv('API_IP_WHITELIST', '')
        self.ip_whitelist = [ip.strip() for ip in whitelist_str.split(',') if ip.strip()]
        
        # Load public endpoints from config (with fallback to env var)
        try:
            from app.api_config.endpoints import PUBLIC_ENDPOINTS
            self.public_endpoints = PUBLIC_ENDPOINTS
        except ImportError:
            # Fallback to env var if config not found
            public_str = os.getenv('API_PUBLIC_ENDPOINTS', '/health,/api/telegram/webhook,/api/triage/health,/api/rag/health')
            self.public_endpoints = [ep.strip() for ep in public_str.split(',') if ep.strip()]
        
        if not self.auth_enabled:
            logger.warning("API Authentication is DISABLED! All endpoints are public.")
        else:
            logger.info("API Authentication enabled (SQLAlchemy + Redis Cache)")

    def _init_redis(self):
        """Initialize Redis using shared client"""
        try:
            from app.utils.redis_client import get_redis_client
            redis_wrapper = get_redis_client()
            self._redis = redis_wrapper.client
            if self._redis:
                logger.info("Auth Manager connected to Redis")
        except Exception as e:
            logger.warning(f"Auth Manager failed to connect to Redis: {e}")
    
    def validate_key(self, api_key: str) -> Optional[dict]:
        """
        Validate API key using Redis Cache (Fast) + SQLAlchemy (Secure Fallback)
        
        Strategy:
        1. Compute SHA256(raw_key) -> 'Fast Hash'
        2. Check Redis for 'Fast Hash' (O(1))
        3. If miss: Scan DB and verify Argon2 (O(N))
        4. If valid: Cache result in Redis for 10 mins
        """
        if not api_key:
            return None
            
        import hashlib
        import json
        
        # 1. Compute Fast Hash for Cache Lookup
        # We don't store raw key in Redis, but a fast hash of it
        # This is safe because Redis TTL is short and it's internal
        fast_hash = hashlib.sha256(api_key.encode()).hexdigest()
        cache_key = f"api_key:{fast_hash}"
        
        # 2. Check Redis Cache
        if self._redis:
            try:
                cached_data = self._redis.get(cache_key)
                if cached_data:
                    # Update usage stats async or periodically? 
                    # For now we skip DB usage update on cache hit for speed
                    # Or we could fire-and-forget an update task
                    return json.loads(cached_data)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        
        # 3. DB Fallback (Slow path)
        # Get all active keys
        active_keys = APIKeyModel.query.filter_by(enabled=True).all()
        
        # Verify against each hash
        for key_model in active_keys:
            if verify_api_key(api_key, key_model.key_hash):
                # Check expiration
                if key_model.is_expired:
                    logger.warning(f"API key expired: {key_model.name}")
                    return None
                
                # Update usage stats (DB write is slow, but necessary on first check/refresh)
                try:
                    key_model.last_used_at = datetime.utcnow()
                    key_model.usage_count += 1
                    db.session.commit()
                except Exception as e:
                    logger.error(f"Failed to update key usage stats: {e}")
                    db.session.rollback()
                
                # Parse permissions
                permissions = json.loads(key_model.permissions)
                
                result = {
                    'id': key_model.id,
                    'name': key_model.name,
                    'description': key_model.description,
                    'permissions': permissions,
                    'rate_limit': key_model.rate_limit,
                    'enabled': key_model.enabled
                }
                
                # 4. Cache Success in Redis
                if self._redis:
                    try:
                        # Cache for 10 minutes (600s)
                        # Enough to save DB calls, short enough for permission revocation
                        self._redis.setex(
                            cache_key,
                            600,
                            json.dumps(result)
                        )
                    except Exception as e:
                        logger.warning(f"Redis set error: {e}")
                
                return result
        
        return None
    
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
        """Reload API keys from database"""
        logger.info("API keys reloaded from database")
    
    @staticmethod
    def generate_key(prefix: str = "sxdr") -> str:
        """Generate a new API key (delegates to model)"""
        from app.models.api_key import APIKey
        return APIKey().generate_key(prefix)


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
                logger.warning(
                    f"Invalid API key attempt from {client_ip} "
                    f"(endpoint: {request.path}, method: {request.method}, "
                    f"key_present: {'Yes' if api_key else 'No'})"
                )
                return jsonify({
                    'status': 'error',
                    'message': 'Invalid or missing API key',
                    'code': 'INVALID_API_KEY',
                    'hint': 'Include header: X-API-Key: your_api_key',
                    'debug': {
                        'client_ip': client_ip,
                        'endpoint': request.path,
                        'has_api_key': bool(api_key)
                    }
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
            g.api_key_raw = api_key  # For logging usage
            g.request_start_time = datetime.now()
            
            # Execute request
            response = func(*args, **kwargs)
            
            # Log usage to database
            try:
                from app.models.db_models import APIKeyUsage
                
                response_time_ms = int((datetime.now() - g.request_start_time).total_seconds() * 1000)
                status_code = response[1] if isinstance(response, tuple) else 200
                
                # Find key by name
                key_model = APIKeyModel.query.filter_by(name=key_info['name']).first()
                if key_model:
                    usage_log = APIKeyUsage(
                        key_hash=key_model.key_hash,
                        endpoint=request.path,
                        method=request.method,
                        client_ip=client_ip,
                        user_agent=request.headers.get('User-Agent', ''),
                        status_code=status_code,
                        response_time_ms=response_time_ms
                    )
                    db.session.add(usage_log)
                    db.session.commit()
                else:
                    logger.debug(f"API key model not found for logging: {key_info['name']}")
            except Exception as e:
                logger.warning(f"Failed to log API usage: {e}", exc_info=True)
            
            return response
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
                g.api_key_raw = api_key
                g.request_start_time = datetime.now()
                
                # Execute request
                response = f(*args, **kwargs)
                
                # Log usage
                try:
                    response_time_ms = int((datetime.now() - g.request_start_time).total_seconds() * 1000)
                    status_code = response[1] if isinstance(response, tuple) else 200
                    
                    from app.models.db_models import APIKeyUsage
                    
                    # Find key by name
                    key_model = APIKeyModel.query.filter_by(name=key_info['name']).first()
                    if key_model:
                        usage_log = APIKeyUsage(
                            key_hash=key_model.key_hash,
                            endpoint=request.path,
                            method=request.method,
                            client_ip=client_ip,
                            user_agent=request.headers.get('User-Agent', ''),
                            status_code=status_code,
                            response_time_ms=response_time_ms
                        )
                        db.session.add(usage_log)
                        db.session.commit()
                        logger.info(f"Logged API usage for {key_info['name']}")
                    else:
                        logger.debug(f"API key model not found for logging: {key_info['name']}")
                except Exception as e:
                    logger.warning(f"Failed to log API usage: {e}", exc_info=True)
                
                return response
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
