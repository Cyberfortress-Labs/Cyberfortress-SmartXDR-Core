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

# Install curl for health checks
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user and directories with proper permissions
RUN useradd -m -u 1000 smartxdr && \
    mkdir -p /app/data /app/logs /app/chroma_db && \
    chown -R smartxdr:smartxdr /app && \
    chmod -R 755 /app/chroma_db

# Copy application code
COPY --chown=smartxdr:smartxdr . .

# Switch to non-root user
USER smartxdr

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run with gunicorn
CMD ["gunicorn", \
    "--config", "gunicorn.conf.py", \
    "run:app"]
