FROM python:3.13-slim-bookworm

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    build-essential \
    ffmpeg \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Poetry (latest)
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Copy dependency files first (for cache)
COPY pyproject.toml poetry.lock ./

# Install dependencies (no virtualenv)
RUN poetry config virtualenvs.create false && poetry install --no-root --no-interaction --no-ansi

# Copy application code
COPY mxtoai ./mxtoai
COPY run_api.py .

# Create directories
RUN mkdir -p /app/attachments

# Set Python path
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run migrations then start the API server
CMD ["sh", "-c", "cd /app/mxtoai/db && poetry run alembic upgrade head && exec poetry run uvicorn mxtoai.api:app --host 0.0.0.0 --port 8000 --workers 4"]
