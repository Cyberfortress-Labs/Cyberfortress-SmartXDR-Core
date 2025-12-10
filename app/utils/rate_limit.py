"""
API Usage Tracking for Rate Limiting and Cost Control
"""
import time
from typing import List, Dict, Any, Callable
from datetime import datetime
from functools import wraps
from flask import request, jsonify


class APIUsageTracker:
    """Track API usage for rate limiting and cost control"""
    
    def __init__(self, max_calls_per_minute: int = 60, max_daily_cost: float = 5.0):
        """
        Initialize API usage tracker
        
        Args:
            max_calls_per_minute: Maximum API calls allowed per minute
            max_daily_cost: Maximum spend per day in USD
        """
        self.max_calls_per_minute = max_calls_per_minute
        self.max_daily_cost = max_daily_cost
        self.call_timestamps: List[float] = []
        self.daily_cost = 0.0
        self.cost_reset_date = datetime.now().date()
    
    def check_rate_limit(self) -> bool:
        """Check if we're within rate limit (calls per minute)"""
        now = time.time()
        # Remove timestamps older than 1 minute
        self.call_timestamps = [ts for ts in self.call_timestamps if now - ts < 60]
        
        if len(self.call_timestamps) >= self.max_calls_per_minute:
            wait_time = 60 - (now - self.call_timestamps[0])
            print(f"\nWARNING: Rate limit reached! Please wait {wait_time:.1f} seconds...")
            return False
        return True
    
    def check_daily_cost(self, estimated_cost: float) -> bool:
        """Check if adding this cost would exceed daily limit"""
        # Reset daily cost if it's a new day
        today = datetime.now().date()
        if today != self.cost_reset_date:
            self.daily_cost = 0.0
            self.cost_reset_date = today
        
        if self.daily_cost + estimated_cost > self.max_daily_cost:
            print(f"\nWARNING: Daily cost limit reached! (${self.daily_cost:.4f}/${self.max_daily_cost})")
            print(f"   This query would cost ~${estimated_cost:.4f}")
            print(f"   Limit will reset tomorrow.")
            return False
        return True
    
    def record_call(self, cost: float):
        """Record a successful API call"""
        self.call_timestamps.append(time.time())
        self.daily_cost += cost
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current usage statistics"""
        return {
            'calls_last_minute': len(self.call_timestamps),
            'daily_cost': self.daily_cost,
            'max_calls_per_minute': self.max_calls_per_minute,
            'max_daily_cost': self.max_daily_cost,
            'cost_reset_date': self.cost_reset_date.isoformat()
        }
    
    def reset_daily_cost(self):
        """Manually reset daily cost (for testing)"""
        self.daily_cost = 0.0
        self.cost_reset_date = datetime.now().date()


# ==================== Rate Limit Decorator ====================

# Global rate limit storage per endpoint
_rate_limit_storage: Dict[str, Dict[str, List[float]]] = {}


def rate_limit(max_calls: int = 60, window: int = 60):
    """
    Rate limiting decorator for Flask routes
    
    Args:
        max_calls: Maximum number of calls allowed within the time window
        window: Time window in seconds (default: 60)
    
    Usage:
        @rate_limit(max_calls=30, window=60)
        def my_endpoint():
            ...
    """
    def rate_limit_decorator(func: Callable) -> Callable:
        @wraps(func)
        def rate_limited_function(*args, **kwargs):
            # Get client identifier (IP address or API key)
            client_id = request.headers.get('X-API-Key', request.remote_addr)
            endpoint = request.endpoint or func.__name__
            
            # Initialize storage for this endpoint if needed
            if endpoint not in _rate_limit_storage:
                _rate_limit_storage[endpoint] = {}
            
            # Initialize storage for this client if needed
            if client_id not in _rate_limit_storage[endpoint]:
                _rate_limit_storage[endpoint][client_id] = []
            
            # Get current timestamp
            now = time.time()
            
            # Clean old timestamps outside the window
            _rate_limit_storage[endpoint][client_id] = [
                ts for ts in _rate_limit_storage[endpoint][client_id]
                if now - ts < window
            ]
            
            # Check if limit exceeded
            call_count = len(_rate_limit_storage[endpoint][client_id])
            if call_count >= max_calls:
                oldest_call = _rate_limit_storage[endpoint][client_id][0]
                wait_time = window - (now - oldest_call)
                
                return jsonify({
                    "status": "error",
                    "error": f"Rate limit exceeded. Maximum {max_calls} requests per {window} seconds.",
                    "retry_after": int(wait_time) + 1,
                    "limit": max_calls,
                    "window": window
                }), 429
            
            # Record this call
            _rate_limit_storage[endpoint][client_id].append(now)
            
            # Execute the function
            return func(*args, **kwargs)
        
        return rate_limited_function
    return rate_limit_decorator
