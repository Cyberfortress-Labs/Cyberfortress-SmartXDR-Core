# SmartXDR Docker Deployment Guide

## Quick Start

### 1. Setup Environment
```bash
# Clone repository
git clone https://github.com/WanThinnn/Cyberfortress-SmartXDR-Core.git
cd Cyberfortress-SmartXDR-Core

# Create .env file (copy from example or create manually)
cp .env.example .env
# Edit .env with your configurations

# Initial setup
chmod +x start
./start setup
```

### 2. Build and Start Services
```bash
# Build Docker images
./start build

# Start all services
./start start
```

Services will be available at:
- **HTTPS API**: https://localhost:8443
- **HTTP API**: http://localhost:8080

### 3. Create API Key
```bash
# Create master API key
./start api-key create --name "master" --permissions "*" --rate-limit 1000

# Use the generated key in your requests
curl -k -X POST https://localhost:8443/api/ai/ask \
  -H "X-API-Key: sxdr_xxxxx..." \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Suricata?"}'
```

## Architecture

### Services
- **nginx**: Reverse proxy (HTTPS 8443, HTTP 8080)
- **api**: SmartXDR Flask API (internal port 8080)

### Volumes
- **api-data**: API keys database, cache
- **chroma-db**: Vector embeddings database
- **api-logs**: Application logs
- **nginx-logs**: Nginx access/error logs

## Management Commands

### Service Control
```bash
./start start       # Start all services
./start stop        # Stop all services
./start restart     # Restart all services
./start status      # Show service status
./start logs        # View logs (follow mode)
```

### API Key Management
```bash
# Create key
./start api-key create --name "client1" --permissions "ai:*,enrich:read"

# List all keys
./start api-key list

# Show usage statistics
./start api-key stats master --days 7

# Revoke key
./start api-key revoke old_key

# Delete key permanently
./start api-key delete old_key --confirm
```

### Maintenance
```bash
./start shell       # Open bash shell in API container
./start backup      # Backup data and embeddings
./start rebuild     # Rebuild from scratch
./start clean       # Remove all containers and volumes
```

## SSL Certificates

Place your SSL certificates in the `certs/` directory:
- `_.cyberfortress.local.crt` - Certificate file
- `_.cyberfortress.local.key` - Private key file

For development, you can use self-signed certificates:
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout certs/_.cyberfortress.local.key \
  -out certs/_.cyberfortress.local.crt \
  -subj "/CN=*.cyberfortress.local"
```

## Environment Variables

Required in `.env` file:
```bash
# API Authentication
API_AUTH_ENABLED=true

# AI Services
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...

# Elasticsearch
ELASTICSEARCH_ENABLED=true
ELASTICSEARCH_HOSTS=https://cyberfortress.local:9201
ELASTICSEARCH_USERNAME=...
ELASTICSEARCH_PASSWORD=...

# IRIS SOAR
IRIS_URL=https://iris.cyberfortress.local
IRIS_API_KEY=...

# Telegram Bot (optional)
TELEGRAM_BOT_ENABLED=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHATS=...

# Email Reports (optional)
FROM_EMAIL=...
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_PASSWORD=...
TO_EMAILS=...
```

## CI/CD with GitHub Actions

The repository includes automated CI/CD pipeline:

### Setup
1. Create DockerHub account
2. Add secrets to GitHub repository:
   - `DOCKERHUB_USERNAME`: Your DockerHub username
   - `DOCKERHUB_TOKEN`: DockerHub access token

### Workflow
- **Push to main**: Builds and pushes image with `latest` tag
- **Tag push (v*)**: Builds and pushes versioned image
- **Pull request**: Builds image (no push)
- **Security scan**: Runs Trivy vulnerability scanner

### Manual Trigger
```bash
# Via GitHub UI: Actions → Build and Push → Run workflow
```

## Production Deployment

### 1. Pull Pre-built Image
```bash
# Pull latest image from DockerHub
docker pull wanthinnn/smartxdr-core:latest

# Or specific version
docker pull wanthinnn/smartxdr-core:v1.0.0

# Start with docker-compose
./start start
```

### 2. Update to Latest Version
```bash
./start pull      # Pull latest images
./start restart   # Restart services
```

### 3. Resource Limits
Configured in `docker-compose.yml`:
- Memory limit: 2GB
- Memory reservation: 512MB

Adjust as needed for your environment.

## Troubleshooting

### Check Service Status
```bash
./start status
./start logs
```

### Check API Health
```bash
# HTTP
curl http://localhost:8080/api/health

# HTTPS (with self-signed cert)
curl -k https://localhost:8443/api/health
```

### Access Container Shell
```bash
./start shell

# Inside container
python scripts/manage_api_keys.py list
cat logs/smartxdr.log
```

### View Nginx Logs
```bash
docker compose logs nginx

# Or access volume directly
docker volume inspect smartxdr-nginx-logs
```

### Reset Everything
```bash
./start clean     # Remove containers and volumes
./start setup     # Recreate directories
./start build     # Rebuild images
./start start     # Start fresh
```

## Security Best Practices

1. **Change default certificates**: Use proper SSL certificates in production
2. **Secure .env file**: Never commit `.env` to version control
3. **Firewall rules**: Restrict access to ports 8080/8443
4. **API key rotation**: Regularly rotate API keys
5. **Monitor logs**: Review logs for suspicious activity
6. **Update regularly**: Pull latest images for security patches

## Support

For issues, feature requests, or questions:
- GitHub Issues: https://github.com/WanThinnn/Cyberfortress-SmartXDR-Core/issues
- Documentation: https://github.com/WanThinnn/Cyberfortress-SmartXDR-Core/tree/main/docs
