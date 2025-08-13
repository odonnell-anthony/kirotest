# Multi-stage Dockerfile for Wiki Documentation App with Security Hardening

# Build stage
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install security tools
RUN pip install --upgrade pip setuptools wheel

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim as production

# Security labels
LABEL maintainer="wiki-app-team" \
      version="1.0.0" \
      description="Wiki Documentation App - Production Image" \
      security.scan="enabled"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ENVIRONMENT=production \
    PYTHONPATH=/app

# Install runtime dependencies and security updates
RUN apt-get update && apt-get install -y \
    libpq5 \
    libmagic1 \
    curl \
    ca-certificates \
    postgresql-client \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get autoremove -y

# Create non-root user with specific UID/GID for security
RUN groupadd -r -g 1001 appuser && \
    useradd -r -u 1001 -g appuser -d /app -s /bin/bash appuser

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create application directory with proper permissions
WORKDIR /app

# Create directories with proper permissions and ownership
RUN mkdir -p /app/uploads /app/logs /app/tmp && \
    chown -R appuser:appuser /app && \
    chmod 755 /app && \
    chmod 750 /app/uploads /app/logs /app/tmp

# Copy application code with proper ownership
COPY --chown=appuser:appuser . .

# Make entrypoint script executable
RUN chmod +x /app/docker-entrypoint.sh

# Remove sensitive files that shouldn't be in production
RUN rm -f .env* docker-compose*.yml Dockerfile* README.md && \
    find /app -name "*.pyc" -delete && \
    find /app -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Set proper file permissions
RUN find /app -type f -exec chmod 644 {} \; && \
    find /app -type d -exec chmod 755 {} \; && \
    chmod +x /app/scripts/*.py 2>/dev/null || true

# Switch to non-root user
USER appuser

# Expose port (non-privileged)
EXPOSE 8000

# Add security-focused health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Set entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Use exec form for better signal handling
CMD ["gunicorn", "app.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keepalive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--preload", \
     "--access-logfile", "/app/logs/access.log", \
     "--error-logfile", "/app/logs/error.log", \
     "--log-level", "info"]