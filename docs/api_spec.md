# SmartXDR API Specification

## Base URL
```
http://localhost:5000/api
```

---

## AI/LLM Endpoints

### POST /api/ai/ask
Query the LLM using RAG (Retrieval-Augmented Generation).

**Request Body:**
```json
{
    "query": "What is Suricata's management IP?",
    "n_results": 10,
    "filter": {}
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| query | string | Yes | - | Question to ask |
| n_results | int | No | 10 | Number of context chunks (1-50) |
| filter | object | No | null | Metadata filter |

**Response:**
```json
{
    "status": "success",
    "query": "What is Suricata's management IP?",
    "answer": "Suricata's management IP is 10.10.21.11...",
    "cached": false,
    "sources": ["mitre_attack", "network"],
    "n_results": 10
}
```

### GET /api/ai/stats
Get API usage statistics.

**Response:**
```json
{
    "status": "success",
    "stats": {
        "rate_limit": {...},
        "cost": {...},
        "cache": {...}
    }
}
```

### POST /api/ai/cache/clear
Clear response cache.

**Response:**
```json
{
    "status": "success",
    "message": "Cache cleared successfully"
}
```

---

## IOC Analysis Endpoints

### POST /api/ioc/analyze
Analyze an Indicator of Compromise using IntelOwl.

**Request Body:**
```json
{
    "value": "8.8.8.8",
    "type": "ip"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| value | string | Yes | IOC value to analyze |
| type | string | Yes | One of: ip, domain, hash, url |

**Response:**
```json
{
    "status": "success",
    "ioc": "8.8.8.8",
    "type": "ip",
    "analysis": {
        "summary": "AI-generated summary...",
        "severity": "LOW/MEDIUM/HIGH/CRITICAL",
        "recommendations": [...]
    },
    "raw_results": {...}
}
```

---

## Security Triage Endpoints

### GET/POST /api/triage/alerts/summary
Summarize security alerts from ElastAlert2 and Kibana Security using AI.

**Query Params (GET) / Request Body (POST):**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| hours | int | No | 24 | Time range (1-168 hours) |

**GET Example:**
```
GET /api/triage/alerts/summary?hours=24
```

**POST Example:**
```json
{
    "hours": 48
}
```

**Response:**
```json
{
    "status": "success",
    "summary": "# Tóm tắt cảnh báo bảo mật 24h qua\n\n## Tổng quan\n...",
    "severity_level": "HIGH",
    "key_findings": [
        "Phát hiện 15 cuộc tấn công brute-force từ IP 192.168.1.100",
        "..."
    ],
    "recommended_actions": [
        "Block IP 192.168.1.100 at firewall",
        "..."
    ],
    "metadata": {
        "time_range_hours": 24,
        "total_alerts": 150,
        "elastalert_count": 30,
        "kibana_count": 120,
        "generated_at": "2024-01-15T10:30:00Z"
    }
}
```

### GET /api/triage/alerts/raw
Get raw alert data without AI summarization.

**Query Params:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| hours | int | 24 | Time range (1-168 hours) |
| source | string | all | "elastalert", "kibana", or "all" |

**Example:**
```
GET /api/triage/alerts/raw?hours=24&source=elastalert
```

**Response:**
```json
{
    "status": "success",
    "source": "elastalert",
    "hours": 24,
    "data": {
        "total": 30,
        "alerts": [...],
        "summary": {...}
    }
}
```

### GET /api/triage/alerts/statistics
Get aggregated statistics from Elasticsearch logs.

**Query Params:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| hours | int | 24 | Time range (1-168 hours) |

**Response:**
```json
{
    "status": "success",
    "hours": 24,
    "statistics": {
        "top_attacked_ips": [
            {"ip": "192.168.1.10", "hits": 500},
            ...
        ],
        "top_attacker_ips": [
            {"ip": "203.0.113.50", "hits": 200},
            ...
        ],
        "event_distribution": {
            "firewall": 1000,
            "ids": 500,
            "authentication": 300
        }
    }
}
```

### GET /api/triage/ml/predictions
Get ML log classification predictions.

The ML pipeline classifies logs into severity levels:
- **EROR**: Critical logs requiring immediate attention (likely incident/attack)
- **WARN**: Logs that need review (potential issue or anomaly)  
- **INFO**: Normal activity logs

**Query Params:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| hours | int | 24 | Time range (1-168 hours) |
| min_probability | float | 0.5 | Minimum prediction confidence (0-1) |

**Example:**
```
GET /api/triage/ml/predictions?hours=24&min_probability=0.7
```

**Response:**
```json
{
    "status": "success",
    "hours": 24,
    "min_probability": 0.5,
    "total": 1500,
    "by_severity": {
        "EROR": {
            "count": 50,
            "avg_probability": 0.85,
            "samples": [
                {
                    "timestamp": "2024-01-15T10:30:00Z",
                    "message": "Failed login attempt from unknown IP...",
                    "predicted_severity": "EROR",
                    "probability": 0.92,
                    "source_ip": "203.0.113.50",
                    "host": "web-server-01"
                }
            ]
        },
        "WARN": {
            "count": 200,
            "avg_probability": 0.72,
            "samples": [...]
        },
        "INFO": {
            "count": 1250,
            "avg_probability": 0.68,
            "samples": [...]
        }
    },
    "summary": {
        "time_range": "...",
        "high_confidence_count": 800,
        "severity_distribution": {
            "EROR": 50,
            "WARN": 200,
            "INFO": 1250
        },
        "probability_ranges": {
            "low": 300,
            "medium": 700,
            "high": 500
        }
    }
}
```

### GET /api/triage/health
Health check for triage service.

**Response:**
```json
{
    "status": "healthy",
    "services": {
        "elasticsearch": true,
        "llm_service": true
    }
}
```

---

## Health Check

### GET /health
Global health check endpoint.

**Response:**
```json
{
    "status": "healthy",
    "service": "Cyberfortress SmartXDR Core"
}
```

---

## Error Responses

All endpoints return consistent error responses:

```json
{
    "status": "error",
    "message": "Error description"
}
```

**HTTP Status Codes:**
- `200` - Success
- `400` - Bad Request (invalid parameters)
- `429` - Rate Limited
- `500` - Internal Server Error
- `503` - Service Unavailable

---

## Rate Limiting

AI endpoints are rate-limited:
- **Requests per minute:** 10
- **Requests per hour:** 100

When rate limited, response includes:
```json
{
    "status": "error",
    "message": "Rate limit exceeded",
    "retry_after": 60
}
```
