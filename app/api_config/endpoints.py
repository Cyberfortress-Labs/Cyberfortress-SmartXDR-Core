"""
SmartXDR API Endpoints Configuration
=====================================

This file defines all API endpoints and their access control settings.
Modify the PUBLIC_ENDPOINTS list to change which endpoints require authentication.

Usage:
- PUBLIC_ENDPOINTS: List of endpoints that don't require API key
- PROTECTED_ENDPOINTS: All endpoints with their permissions

Note: Changes here require server restart to take effect.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS (No API Key Required)
# ═══════════════════════════════════════════════════════════════════════════════
# These endpoints can be accessed without authentication.
# Add endpoint paths here to make them public.

PUBLIC_ENDPOINTS = [
    # Health checks
    "/health",
    "/api/rag/health",
    "/api/triage/health",
    
    # Telegram webhook (needs to be public for Telegram servers)
    "/api/telegram/webhook",
]


# ═══════════════════════════════════════════════════════════════════════════════
# PROTECTED ENDPOINTS (API Key Required)
# ═══════════════════════════════════════════════════════════════════════════════
# All other endpoints require API key with appropriate permissions.

ENDPOINT_REGISTRY = {
    # ─────────────────────────────────────────────────────────────────────────
    # AI / LLM Endpoints
    # ─────────────────────────────────────────────────────────────────────────
    "/api/ai/ask": {
        "method": "POST",
        "permission": "ai:ask",
        "description": "Ask LLM a question using RAG",
        "rate_limit": 30,  # requests per minute
    },
    "/api/ai/stats": {
        "method": "GET",
        "permission": "ai:stats",
        "description": "Get usage statistics",
        "rate_limit": 60,
    },
    "/api/ai/cache/clear": {
        "method": "POST",
        "permission": "ai:admin",
        "description": "Clear response cache",
        "rate_limit": 10,
    },
    
    # ─────────────────────────────────────────────────────────────────────────
    # RAG Knowledge Base Endpoints
    # ─────────────────────────────────────────────────────────────────────────
    "/api/rag/documents": {
        "method": ["POST", "GET"],
        "permission": "rag:write",
        "description": "Create/List documents",
        "rate_limit": 60,
    },
    "/api/rag/documents/batch": {
        "method": "POST",
        "permission": "rag:write",
        "description": "Batch create documents",
        "rate_limit": 10,
    },
    "/api/rag/documents/<id>": {
        "method": ["GET", "PUT", "DELETE"],
        "permission": "rag:write",
        "description": "Get/Update/Delete document",
        "rate_limit": 60,
    },
    "/api/rag/query": {
        "method": "POST",
        "permission": "rag:query",
        "description": "RAG query (search + LLM)",
        "rate_limit": 30,
    },
    "/api/rag/stats": {
        "method": "GET",
        "permission": "rag:read",
        "description": "RAG statistics",
        "rate_limit": 60,
    },
    
    # ─────────────────────────────────────────────────────────────────────────
    # IOC Enrichment Endpoints
    # ─────────────────────────────────────────────────────────────────────────
    "/api/enrich/explain_intelowl": {
        "method": "POST",
        "permission": "enrich:explain",
        "description": "Explain IntelOwl results with AI",
        "rate_limit": 20,
    },
    "/api/enrich/explain_case_iocs": {
        "method": "POST",
        "permission": "enrich:explain",
        "description": "Analyze all IOCs in a case",
        "rate_limit": 5,
    },
    "/api/enrich/case_ioc_comments": {
        "method": "GET",
        "permission": "enrich:read",
        "description": "Get SmartXDR comments for IOCs",
        "rate_limit": 60,
    },
    
    # ─────────────────────────────────────────────────────────────────────────
    # Triage & Alert Endpoints
    # ─────────────────────────────────────────────────────────────────────────
    "/api/triage/summarize-alerts": {
        "method": "POST",
        "permission": "triage:summarize",
        "description": "Summarize ML-classified alerts",
        "rate_limit": 10,
    },
    "/api/triage/alerts": {
        "method": ["GET", "POST"],
        "permission": "triage:read",
        "description": "Get alert summary",
        "rate_limit": 30,
    },
    "/api/triage/alerts/raw": {
        "method": "GET",
        "permission": "triage:read",
        "description": "Get raw alert data",
        "rate_limit": 30,
    },
    "/api/triage/sources": {
        "method": "GET",
        "permission": "triage:read",
        "description": "List available log sources",
        "rate_limit": 60,
    },
    "/api/triage/statistics": {
        "method": "GET",
        "permission": "triage:read",
        "description": "Get alert statistics",
        "rate_limit": 30,
    },
    "/api/triage/ml-predictions": {
        "method": "GET",
        "permission": "triage:read",
        "description": "Get ML predictions",
        "rate_limit": 30,
    },
    "/api/triage/send-report-email": {
        "method": "POST",
        "permission": "triage:email",
        "description": "Send alert report via email",
        "rate_limit": 5,
    },
    "/api/triage/daily-report/trigger": {
        "method": "POST",
        "permission": "triage:admin",
        "description": "Manually trigger daily report",
        "rate_limit": 3,
    },
    
    # ─────────────────────────────────────────────────────────────────────────
    # Telegram Endpoints
    # ─────────────────────────────────────────────────────────────────────────
    "/api/telegram/webhook/set": {
        "method": "POST",
        "permission": "telegram:admin",
        "description": "Set Telegram webhook URL",
        "rate_limit": 5,
    },
    "/api/telegram/webhook/delete": {
        "method": "POST",
        "permission": "telegram:admin",
        "description": "Delete Telegram webhook",
        "rate_limit": 5,
    },
    "/api/telegram/webhook/info": {
        "method": "GET",
        "permission": "telegram:read",
        "description": "Get webhook info",
        "rate_limit": 30,
    },
    "/api/telegram/status": {
        "method": "GET",
        "permission": "telegram:read",
        "description": "Get middleware status",
        "rate_limit": 60,
    },
    "/api/telegram/start": {
        "method": "POST",
        "permission": "telegram:admin",
        "description": "Start Telegram middleware",
        "rate_limit": 5,
    },
    "/api/telegram/stop": {
        "method": "POST",
        "permission": "telegram:admin",
        "description": "Stop Telegram middleware",
        "rate_limit": 5,
    },
    "/api/telegram/config": {
        "method": "GET",
        "permission": "telegram:read",
        "description": "Get Telegram config",
        "rate_limit": 30,
    },
    "/api/telegram/test": {
        "method": "GET",
        "permission": "telegram:read",
        "description": "Test Telegram connection",
        "rate_limit": 10,
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# PERMISSION GROUPS
# ═══════════════════════════════════════════════════════════════════════════════
# Predefined permission sets for common use cases

PERMISSION_PRESETS = {
    "full_access": ["*"],
    
    "read_only": [
        "ai:stats",
        "rag:read",
        "rag:query",
        "enrich:read",
        "triage:read",
        "telegram:read",
    ],
    
    "analyst": [
        "ai:ask",
        "ai:stats",
        "rag:query",
        "rag:read",
        "enrich:*",
        "triage:*",
    ],
    
    "automation": [
        "ai:ask",
        "rag:query",
        "enrich:explain",
        "triage:summarize",
        "triage:read",
    ],
    
    "admin": [
        "*",  # Full access
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def is_public_endpoint(path: str) -> bool:
    """Check if an endpoint is public"""
    for public_ep in PUBLIC_ENDPOINTS:
        if path.startswith(public_ep):
            return True
    return False


def get_endpoint_permission(path: str) -> str:
    """Get required permission for an endpoint"""
    for ep, config in ENDPOINT_REGISTRY.items():
        # Handle path parameters like /api/rag/documents/<id>
        if "<" in ep:
            pattern = ep.split("<")[0]
            if path.startswith(pattern):
                return config.get("permission", "*")
        elif path == ep or path.startswith(ep + "/"):
            return config.get("permission", "*")
    return "*"


def list_all_endpoints() -> dict:
    """Get summary of all endpoints"""
    return {
        "public": PUBLIC_ENDPOINTS,
        "protected_count": len(ENDPOINT_REGISTRY),
        "endpoints": ENDPOINT_REGISTRY,
    }
