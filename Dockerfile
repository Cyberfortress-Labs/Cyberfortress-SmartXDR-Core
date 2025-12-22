# SmartXDR Core - Multi-stage Production Dockerfile
# Stage 1: Builder - Install dependencies
FROM python:3.10-slim AS builder

WORKDIR /build

# Install build dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    --prefix=/install \
    --no-compile \
    -r requirements.txt \
    && find /install -type d -name __pycache__ -exec rm -rf {} + || true

# Stage 2: Runtime - Minimal final image
FROM python:3.10-slim

LABEL maintainer="Cyberfortress Team"
LABEL description="SmartXDR Core - AI-powered XDR Platform"
LABEL version="1.0.0"

WORKDIR /app

# Install curl and ca-certificates for health checks and SSL
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install cloudflared for Telegram webhook tunneling
RUN CLOUDFLARED_VERSION="2024.10.0" && \
    ARCH=$(dpkg --print-architecture) && \
    wget -q "https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-${ARCH}" -O /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared && \
    cloudflared --version

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Install custom root CA certificate (for *.cyberfortress.local)
COPY certs/CyberFortress-RootCA.crt /usr/local/share/ca-certificates/cyberfortress-root-ca.crt
RUN update-ca-certificates && \
    echo "Custom root CA installed: CyberFortress-RootCA"

# Create non-root user and directories with proper permissions
RUN useradd -m -u 1000 smartxdr && \
    mkdir -p /app/data /app/logs /app/chroma_db /home/smartxdr/.cache/huggingface && \
    chown -R smartxdr:smartxdr /app /home/smartxdr && \
    chmod -R 755 /app/chroma_db

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy application code (as root first)
COPY . .

# Fix permissions - ensure directories have execute bit
RUN find /app -type d -exec chmod 755 {} \; && \
    find /app -type f -exec chmod 644 {} \; && \
    chown -R smartxdr:smartxdr /app

# Switch to non-root user
USER smartxdr

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run with entrypoint script (handles tunnel + gunicorn)
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
