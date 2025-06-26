FROM python:3.13-slim-bookworm

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    netcat-traditional \
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

# Install dependencies
RUN poetry config virtualenvs.create false && poetry install --no-root --no-interaction --no-ansi

# Copy application code
COPY mxtoai ./mxtoai

# Create directories
RUN mkdir -p /app/attachments

# Set Python path
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import psutil; exit(0 if any('dramatiq' in ' '.join(p.info['cmdline'] or []) for p in psutil.process_iter(['cmdline'])) else 1)"

# Start the worker
CMD ["poetry", "run", "dramatiq", "mxtoai.tasks"]
