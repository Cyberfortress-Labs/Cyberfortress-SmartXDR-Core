# Cyberfortress SmartXDR Core

**AI-Powered Extended Detection and Response Platform**

SmartXDR Core is an intelligent security operations platform that leverages Large Language Models (LLM) and Retrieval-Augmented Generation (RAG) to enhance threat detection, analysis, and response capabilities.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Management CLI](#management-cli)
- [Security](#security)
- [License](#license)

## Features

### AI/LLM Integration

- RAG-based question answering with knowledge base
- Semantic caching for improved response times
- Support for OpenAI and Gemini models
- Customizable prompts for different use cases

### IOC Enrichment

- Integration with IRIS (Incident Response Information Sharing)
- IntelOwl report analysis with AI explanations
- Automated case IOC processing
- Risk assessment and recommendations

### Triage and Alert Management

- Elasticsearch integration for alert aggregation
- ML-based log classification (ERROR/WARN/INFO)
- Automated alert summarization
- Daily report scheduling with email notifications

### Telegram Bot

- Real-time security notifications
- Interactive threat queries
- Webhook and polling mode support
- Cloudflare Tunnel auto-configuration

### Security

- API Key authentication with Argon2id hashing
- Role-based access control (RBAC)
- Rate limiting per API key
- IP whitelisting support
- Permission-based endpoint protection

## Architecture

```
SmartXDR Core
├── app/
│   ├── routes/           # API endpoints (ai, ioc, rag, telegram, triage)
│   ├── services/         # Business logic services
│   ├── models/           # SQLAlchemy database models
│   ├── middleware/       # Authentication and authorization
│   ├── api_config/       # Endpoint configuration
│   └── utils/            # Cryptography and utilities
├── scripts/              # Management CLI tools
├── prompts/              # LLM prompt templates
├── data/                 # SQLite database
├── chroma_db/            # Vector database storage
├── nginx/                # Reverse proxy configuration
└── tests/                # Unit and integration tests
```

## Requirements

- Docker and Docker Compose
- OpenAI API Key or Gemini API Key
- Elasticsearch 8.x (optional, for triage features)
- IRIS instance (optional, for IOC enrichment)

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/cyberfortress/smartxdr-core.git
cd smartxdr-core
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

Required environment variables:

| Variable         | Description            |
| ---------------- | ---------------------- |
| `OPENAI_API_KEY` | OpenAI API key for LLM |
| `SECRET_KEY`     | Flask secret key       |

### 3. Start Services

```bash
# Development (builds from source)
docker compose up -d

# Production (pulls from DockerHub)
docker compose -f docker-compose.prod.yml up -d
```

### 4. Initialize Admin Account

```bash
docker exec -it smartxdr-core python scripts/smartxdr_manager.py
# Follow prompts to create first admin user and API key
```

### 5. Test API

```bash
curl -X POST http://localhost:8080/api/ai/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"query": "What is XDR?"}'
```

## Configuration

### Environment Variables

| Variable                 | Description                        | Required |
| ------------------------ | ---------------------------------- | -------- |
| `OPENAI_API_KEY`         | OpenAI API key for LLM             | Yes      |
| `GEMINI_API_KEY`         | Alternative: Google Gemini API key | No       |
| `SECRET_KEY`             | Flask secret key for sessions      | Yes      |
| `SECURITY_PASSWORD_SALT` | Salt for password hashing          | Yes      |
| `ELASTICSEARCH_HOSTS`    | Elasticsearch URL                  | No       |
| `ELASTICSEARCH_USERNAME` | Elasticsearch username             | No       |
| `ELASTICSEARCH_PASSWORD` | Elasticsearch password             | No       |
| `IRIS_API_URL`           | IRIS instance URL                  | No       |
| `IRIS_API_KEY`           | IRIS API key                       | No       |
| `TELEGRAM_BOT_TOKEN`     | Telegram bot token                 | No       |
| `API_AUTH_ENABLED`       | Enable API authentication          | No       |

### Endpoint Configuration

Edit `app/api_config/endpoints.py` to configure:

- Public endpoints (no authentication required)
- Protected endpoints with permission requirements
- Rate limits per endpoint

### Docker Compose Override

Create `docker-compose.override.yml` for local customizations:

```yaml
services:
  api:
    environment:
      - DEBUG=true
    volumes:
      - ./app:/app/app:ro
```

## API Reference

### AI Endpoints

| Method | Endpoint              | Permission | Description          |
| ------ | --------------------- | ---------- | -------------------- |
| POST   | `/api/ai/ask`         | ai:ask     | Query LLM with RAG   |
| GET    | `/api/ai/stats`       | ai:stats   | Get usage statistics |
| POST   | `/api/ai/cache/clear` | ai:admin   | Clear response cache |

### RAG Knowledge Base

| Method | Endpoint             | Permission | Description     |
| ------ | -------------------- | ---------- | --------------- |
| POST   | `/api/rag/documents` | rag:write  | Create document |
| GET    | `/api/rag/documents` | rag:read   | List documents  |
| POST   | `/api/rag/query`     | rag:query  | RAG query       |
| GET    | `/api/rag/stats`     | rag:read   | Get statistics  |

### IOC Enrichment

| Method | Endpoint                        | Permission     | Description           |
| ------ | ------------------------------- | -------------- | --------------------- |
| POST   | `/api/enrich/explain_intelowl`  | enrich:explain | Analyze single IOC    |
| POST   | `/api/enrich/explain_case_iocs` | enrich:explain | Analyze all case IOCs |
| GET    | `/api/enrich/case_ioc_comments` | enrich:read    | Get IOC comments      |

### Triage and Alerts

| Method | Endpoint                        | Permission       | Description           |
| ------ | ------------------------------- | ---------------- | --------------------- |
| POST   | `/api/triage/summarize-alerts`  | triage:summarize | Summarize ML alerts   |
| POST   | `/api/triage/send-report-email` | triage:email     | Send report via email |
| GET    | `/api/triage/health`            | public           | Health check          |

### Authentication

Include API key in request headers:

```
X-API-Key: sxdr_your_api_key_here
```

Or use Bearer token:

```
Authorization: Bearer sxdr_your_api_key_here
```

## Management CLI

SmartXDR includes a CLI tool for user and API key management.

```bash
# Local development
docker exec -it smartxdr-core python scripts/smartxdr_manager.py
```

### Features

- **User Management**: Create, list, delete users; reset passwords
- **API Key Management**: Create, list, delete, enable/disable keys
- **System Status**: View overall system statistics

### First Run

On first run with empty database, the CLI will prompt you to create an initial admin account.

### Authentication

CLI requires admin login before accessing management functions.

## Security

### API Authentication

- All endpoints require API key by default
- Keys are hashed using Argon2id algorithm
- Rate limiting prevents abuse
- IP whitelisting available

### Permission System

Permissions follow the format `resource:action`:

- `ai:ask` - Query AI endpoints
- `rag:write` - Modify knowledge base
- `enrich:*` - All enrichment operations
- `*` - Full access

### Best Practices

1. Use strong, unique SECRET_KEY in production
2. Enable SSL/TLS with reverse proxy (included via nginx)
3. Restrict IP whitelist in production
4. Rotate API keys periodically
5. Monitor usage logs for anomalies

## Maintenance

### View Logs

```bash
docker compose logs -f api
docker compose logs -f nginx
```

### Backup Data

```bash
# Backup volumes
docker run --rm -v smartxdr-core-data:/data -v $(pwd):/backup alpine tar czf /backup/smartxdr-backup.tar.gz /data
```

### Update

```bash
# Pull latest images
docker compose -f docker-compose.prod.yml pull

# Restart services
docker compose -f docker-compose.prod.yml up -d
```

## License

This project is licensed under the Open Software License 3.0 (OSL-3.0).

See [LICENSE](LICENSE) for details.

---

**Cyberfortress SmartXDR Core** - Intelligent Security Operations Platform
