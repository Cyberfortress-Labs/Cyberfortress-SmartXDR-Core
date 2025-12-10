# SmartXDR API - Multi-stage Production Dockerfile
# Stage 1: Builder - Install dependencies
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies to /install
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt

# Stage 2: Runtime - Final image
FROM python:3.11-slim

LABEL maintainer="SmartXDR Team"
LABEL description="SmartXDR AI-powered Security Analysis API"
LABEL version="1.0.0"

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN useradd -m -u 1000 smartxdr && \
    mkdir -p /app/data /app/chroma_db /app/logs && \
    chown -R smartxdr:smartxdr /app

# Copy application code
COPY --chown=smartxdr:smartxdr . .

# Switch to non-root user
USER smartxdr

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Run with gunicorn for production
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "4", \
     "--threads", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "run:app"]
