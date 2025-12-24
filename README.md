# Cyberfortress SmartXDR Core

![Version](https://img.shields.io/badge/version-1.0.0--RC-blue)
![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Docker](https://img.shields.io/badge/docker-ready-blue)

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
- Support for OpenAI models
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
│   ├── core/             # Core functionality (RAG, embeddings, query)
│   └── utils/            # Utilities (crypto, cache, logger, rate limit)
├── scripts/              # Management CLI tools
├── prompts/              # LLM prompt templates
├── db/app_data/          # SQLite database storage
├── db/chroma_db/         # Vector database (RAG knowledge base)
├── db/chroma_conv/       # Vector database (conversation history)
├── nginx/                # Reverse proxy with SSL/TLS
├── cloudflared/          # Cloudflare Tunnel configuration
├── data/                 # RAG auto-sync directory
└── tests/                # Unit and integration tests

Services:
├── nginx          - HTTPS reverse proxy (ports 8080, 8443)
├── api            - SmartXDR Core API (Flask + Gunicorn)
├── chromadb-data  - Vector database for RAG (port 8000)
├── chromadb-conv  - Vector database for conversations (port 8001)
├── redis          - Cache for conversation memory (port 6379)
└── cloudflared    - Cloudflare Tunnel (optional)
```

## Requirements

- Docker and Docker Compose
- OpenAI API Key (required)
- Elasticsearch 8.x (optional, for log triage features)
- IRIS instance (optional, for IOC enrichment)
- Telegram Bot Token (optional, for Telegram integration)
- Cloudflare Tunnel (optional, for external webhook access)

> **Note**: On Windows, the `./start` script must be executed in Git Bash or MinGW64. It will not run in Command Prompt or PowerShell.


## Deployment Modes

SmartXDR supports two deployment modes with distinct image sourcing strategies:

### Development Mode (Local Build)

**Image Source**: Built locally from source code

```bash
./start --dev build    # Build images from local source
./start --dev start    # Start services
```

Or simply (development is default):
```bash
./start build
./start up
```

**Characteristics:**
- Images are **compiled from source code** on your machine
- Full control over code modifications and debugging
- Requires build time (~5-10 minutes initial build)
- Uses `docker-compose.yml` configuration
- Ideal for: Development, testing, code contributions
- **No Docker Hub account required**

### Production Mode (Registry Pull)

**Image Source**: Pre-built images from Docker Hub

```bash
./start --prod pull    # Pull pre-built images from registry
./start --prod start   # Start services
```

**Characteristics:**
- Images are **pulled from Docker Hub** (`wanthinnn/smartxdr-core:latest`, `smartxdr-nginx:latest`)
- Zero build time - instant deployment
- Optimized images with production settings
- Uses `docker-compose.prod.yml` configuration
- Higher resource limits (4GB RAM vs 2GB)
- Ideal for: Production deployments, quick setups, stable releases

> **Key Difference**: Dev mode builds images locally using Dockerfile, while Prod mode downloads pre-built images from container registry.

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/cyberfortress/smartxdr-core.git
cd smartxdr-core
```

### 2. Initial Setup

```bash
# Setup directories and create .env file
./start setup

# Edit .env with your API keys
nano .env
```

Required environment variables:

| Variable                 | Description                   | Required |
| ------------------------ | ----------------------------- | -------- |
| `OPENAI_API_KEY`         | OpenAI API key for LLM        | Yes      |
| `SECRET_KEY`             | Flask secret key              | Yes      |
| `SECURITY_PASSWORD_SALT` | Salt for password hashing     | Yes      |
| `TELEGRAM_BOT_TOKEN`     | Telegram bot token            | No       |
| `ELASTICSEARCH_HOSTS`    | Elasticsearch URL             | No       |
| `IRIS_API_URL`           | IRIS instance URL             | No       |

### 3. Build and Start Services

**Development Mode (build from source):**

```bash
# Build Docker images from source
./start --dev build

# Start all services
./start --dev start
```

**Production Mode (use pre-built images):**

```bash
# Pull latest images from Docker Hub
./start --prod pull

# Start all services
./start --prod up
```

### 4. Initialize Admin Account

```bash
# Open SmartXDR Manager CLI
./start manage

# Follow prompts to:
# 1. Create first admin user
# 2. Create API key with permissions
```

### 5. Test API

```bash
# Check health
curl http://localhost:8080/health

# Test AI endpoint
curl -X POST https://localhost:8443/api/ai/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"query": "What is XDR?", "session_id": "test"}' \
  -k
```

## Configuration

### Environment Variables

| Variable                 | Description                        | Required | Default |
| ------------------------ | ---------------------------------- | -------- | ------- |
| `OPENAI_API_KEY`         | OpenAI API key for LLM             | Yes      | -       |
| `SECRET_KEY`             | Flask secret key for sessions      | Yes      | -       |
| `SECURITY_PASSWORD_SALT` | Salt for password hashing          | Yes      | -       |
| `DEBUG`                  | Enable debug mode                  | No       | false   |
| `DEBUG_LLM`              | Enable LLM debug logs              | No       | false   |
| `DEBUG_ANONYMIZATION`    | Show anonymization process         | No       | false   |
| `ELASTICSEARCH_HOSTS`    | Elasticsearch URL                  | No       | -       |
| `ELASTICSEARCH_USERNAME` | Elasticsearch username             | No       | -       |
| `ELASTICSEARCH_PASSWORD` | Elasticsearch password             | No       | -       |
| `ELASTICSEARCH_CA_CERT`  | Path to CA certificate             | No       | -       |
| `IRIS_API_URL`           | IRIS instance URL                  | No       | -       |
| `IRIS_API_KEY`           | IRIS API key                       | No       | -       |
| `IRIS_VERIFY_SSL`        | Verify IRIS SSL certificate        | No       | false   |
| `TELEGRAM_BOT_TOKEN`     | Telegram bot token                 | No       | -       |
| `TELEGRAM_BOT_ENABLED`   | Enable Telegram bot                | No       | true    |
| `TELEGRAM_WEBHOOK_ENABLED` | Use webhook mode (vs polling)    | No       | true    |
| `API_AUTH_ENABLED`       | Enable API authentication          | No       | true    |
| `NGINX_HTTPS_PORT`       | HTTPS port                         | No       | 8443    |
| `NGINX_HTTP_PORT`        | HTTP port                          | No       | 8080    |
| `CHROMA_PORT`            | ChromaDB port                      | No       | 8000    |
| `REDIS_PORT`             | Redis port                         | No       | 6379    |
| `SMARTXDR_URL`           | External display URL               | No       | -       |
| `CROSS_ENCODER_MODEL`    | Re-ranking model name              | No       | ms-marco-MiniLM-L-6-v2 |
| `RERANKING_ENABLED`      | Enable re-ranking                  | No       | true    |
| `RAG_SYNC_ENABLED`       | Enable auto RAG sync               | No       | true    |
| `RAG_SYNC_INTERVAL`      | Sync interval (minutes)            | No       | 60      |
| `RAG_SYNC_SKIP_FILES`    | Files to skip during sync          | No       | README.md |

### Endpoint Configuration

Edit `app/api_config/endpoints.py` to configure:

- Public endpoints (no authentication required)
- Protected endpoints with permission requirements
- Rate limits per endpoint

### Development Mode

For development with live code reloading, create `docker-compose.override.yml`:

```yaml
services:
  api:
    environment:
      - DEBUG=true
      - FLASK_DEBUG=true
    volumes:
      - ./app:/app/app:ro  # Mount source code read-only
    command: flask run --host=0.0.0.0 --port=8080 --reload
```

Then restart services:

```bash
./start restart
```

## API Reference

### AI / LLM Endpoints

| Method | Endpoint                        | Permission | Description                  |
| ------ | ------------------------------- | ---------- | ---------------------------- |
| POST   | `/api/ai/ask`                   | ai:ask     | Query LLM with RAG           |
| GET    | `/api/ai/sessions/<id>/history` | ai:ask     | Get conversation history     |
| DELETE | `/api/ai/sessions/<id>`         | ai:ask     | Delete conversation session  |
| GET    | `/api/ai/sessions/stats`        | ai:stats   | Get session statistics       |
| GET    | `/api/ai/stats`                 | ai:stats   | Get usage statistics         |
| POST   | `/api/ai/cache/clear`           | ai:admin   | Clear response cache         |

### RAG Knowledge Base

| Method | Endpoint                  | Permission | Description           |
| ------ | ------------------------- | ---------- | --------------------- |
| POST   | `/api/rag/documents`      | rag:write  | Create document       |
| POST   | `/api/rag/documents/batch`| rag:write  | Batch create documents|
| GET    | `/api/rag/documents`      | rag:read   | List documents        |
| GET    | `/api/rag/documents/<id>` | rag:write  | Get document          |
| PUT    | `/api/rag/documents/<id>` | rag:write  | Update document       |
| DELETE | `/api/rag/documents/<id>` | rag:write  | Delete document       |
| POST   | `/api/rag/query`          | rag:query  | RAG query             |
| GET    | `/api/rag/stats`          | rag:read   | Get statistics        |
| GET    | `/api/rag/health`         | public     | Health check          |

### IOC Enrichment

| Method | Endpoint                        | Permission     | Description           |
| ------ | ------------------------------- | -------------- | --------------------- |
| POST   | `/api/enrich/explain_intelowl`  | enrich:explain | Analyze single IOC    |
| POST   | `/api/enrich/explain_case_iocs` | enrich:explain | Analyze all case IOCs |
| GET    | `/api/enrich/case_ioc_comments` | enrich:read    | Get IOC comments      |

### Triage and Alerts

| Method | Endpoint                        | Permission       | Description                |
| ------ | ------------------------------- | ---------------- | -------------------------- |
| POST   | `/api/triage/summarize-alerts`  | triage:summarize | Summarize ML alerts        |
| GET/POST| `/api/triage/alerts/summary`   | triage:read      | Get alert summary          |
| GET    | `/api/triage/alerts/raw`        | triage:read      | Get raw alert data         |
| GET    | `/api/triage/sources`           | triage:read      | List available log sources |
| GET    | `/api/triage/alerts/statistics` | triage:read      | Get alert statistics       |
| GET    | `/api/triage/ml/predictions`    | triage:read      | Get ML predictions         |
| POST   | `/api/triage/send-report-email` | triage:email     | Send report via email      |
| POST   | `/api/triage/daily-report/trigger`| triage:admin   | Manually trigger report    |
| GET    | `/api/triage/health`            | public           | Health check               |

### Telegram Bot

| Method | Endpoint                   | Permission      | Description              |
| ------ | -------------------------- | --------------- | ------------------------ |
| POST   | `/api/telegram/webhook`    | public          | Telegram webhook         |
| POST   | `/api/telegram/webhook/set`| telegram:admin  | Set webhook URL          |
| POST   | `/api/telegram/webhook/delete`| telegram:admin | Delete webhook        |
| GET    | `/api/telegram/webhook/info`| telegram:read  | Get webhook info         |
| GET    | `/api/telegram/status`     | telegram:read   | Get bot status           |
| POST   | `/api/telegram/start`      | telegram:admin  | Start bot (polling)      |
| POST   | `/api/telegram/stop`       | telegram:admin  | Stop bot                 |
| GET    | `/api/telegram/config`     | telegram:read   | Get bot config           |
| GET    | `/api/telegram/test`       | telegram:read   | Test bot connection      |

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

SmartXDR includes a comprehensive CLI tool for user and API key management.

```bash
# Using the start script (recommended)
./start manage

# Or directly via docker exec
docker exec -it smartxdr-core python scripts/smartxdr_manager.py
```

### Features

- **User Management**: Create, list, delete users; reset passwords
- **API Key Management**: Create, list, delete, enable/disable keys; manage permissions
- **Role Management**: Assign roles and permissions to users
- **System Status**: View overall system statistics and usage
- **Permission Presets**: Quick setup with predefined permission sets:
  - `full_access` - All permissions (*)
  - `read_only` - View-only access
  - `analyst` - Full analyst capabilities
  - `automation` - API access for automation
  - `admin` - Full administrative access

### First Run

On first run with empty database, the CLI will automatically prompt you to create an initial admin account with API key.

### Authentication

CLI requires admin login before accessing management functions. API keys are prefixed with `sxdr_`.

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

### Common Commands

```bash
# View logs (all services)
./start logs

# View logs for specific service
./start logs api
./start logs nginx

# Check service status
./start status

# Check API health
./start health

# Open shell in API container
./start shell

# Restart services
./start restart
```

### RAG Management

```bash
# Ingest documents to RAG knowledge base
./start quick_rag assets/knowledge_base

# View RAG sync options
./start sync_rag
```

### Backup and Restore

```bash
# Create backup (data + chroma_db)
./start backup

# Backups are saved to: backups/YYYYMMDD_HHMMSS/
# Contains:
#   - data.tar.gz (SQLite database)
#   - chroma.tar.gz (vector embeddings)

# Restore from backup
tar xzf backups/20241220_120000/data.tar.gz -C db/app_data
tar xzf backups/20241220_120000/chroma.tar.gz -C db/chroma_db
./start restart
```

### Update to Latest Version

**Development Mode:**

```bash
# Rebuild from latest source code
./start rebuild

# Or manually:
./start build
./start restart
```

**Production Mode:**

```bash
# Pull latest images from Docker Hub and restart
./start --prod update

# Or manually:
./start --prod pull
./start --prod restart
```

### Clean Installation

```bash
# WARNING: This will delete all data!
./start clean

# Rebuild from scratch
./start rebuild
```

## Start Script Reference

The `./start` script provides a convenient interface for all operations:

```bash
# ============================================================
# DEPLOYMENT MODES
# ============================================================
# Development - Build from source code
./start --dev <command>
./start <command>              # Same as --dev (default)

# Production - Use pre-built Docker Hub images  
./start --prod <command>

# ============================================================
# SETUP & BUILD
# ============================================================
./start setup                 # Initial setup (create directories, .env)
./start build                 # Build images from source (dev mode)
./start --prod pull           # Pull pre-built images (prod mode)

# Service Control
./start up                    # Start all services
./start down                  # Stop all services
./start restart               # Restart services
./start status                # Show service status

# Logs & Debugging
./start logs [service]        # View logs (all or specific service)
./start health                # Check API health
./start shell                 # Open shell in API container

# Management
./start manage                # Open SmartXDR Manager CLI

# RAG & Data
./start quick_rag [path]      # Ingest documents to RAG
./start sync_rag              # Show RAG sync instructions
./start backup                # Backup data and embeddings

# Updates
./start pull                  # Pull latest Docker images
./start update                # Pull and restart services
./start rebuild               # Rebuild from scratch (no cache)

# Cleanup
./start clean                 # Remove containers and volumes

# Help
./start help                  # Show all commands
```

### Deployment Mode Comparison

| Feature | Development Mode | Production Mode |
|---------|-----------------|------------------|
| **Command** | `./start --dev <cmd>` or `./start <cmd>` | `./start --prod <cmd>` |
| **Docker Compose** | `docker-compose.yml` | `docker-compose.prod.yml` |
| **Images** | Built from source | Pulled from Docker Hub |
| **Build Time** | ~5-10 minutes | None (pre-built) |
| **Startup Time** | Slower | Faster |
| **Code Changes** | Applied immediately | Requires new image release |
| **Resource Limits** | Lower (2GB RAM) | Higher (4GB RAM) |
| **Use Case** | Development, testing | Production deployments |

**Examples:**

```bash
# Development workflow
./start --dev build        # Build from source
./start --dev start        # Start services
./start --dev logs api     # Check logs
./start --dev shell        # Debug in container

# Production workflow  
./start --prod pull        # Pull latest images
./start --prod start       # Start services
./start --prod update      # Update to newest version
```

### Access URLs

- **HTTP**: http://localhost:8080
- **HTTPS**: https://localhost:8443 (self-signed cert)
- **ChromaDB Data**: http://localhost:8000 (RAG knowledge base)
- **ChromaDB Conv**: http://localhost:8001 (conversation history)
- **Redis**: localhost:6379

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

See [LICENSE](LICENSE) for details.
