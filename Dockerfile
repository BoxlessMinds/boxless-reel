# YouTube Transcript API - Dockerfile
# Multi-stage build for Python FastAPI backend

# =============================================================================
# Stage 1: Build stage with uv
# =============================================================================
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.9.11 /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies with agent extras (openai + anthropic for LLM features)
RUN uv sync --frozen --no-dev --no-install-project --extra agents

# =============================================================================
# Stage 2: Runtime stage
# =============================================================================
FROM python:3.11-slim AS runtime

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY src/ ./src/

# Copy scripts for migrations
COPY scripts/ ./scripts/

# Create data directory for LanceDB, and an unprivileged user to run as
RUN mkdir -p /app/data \
    && useradd --uid 1000 --create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run as a non-root user
USER app

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
