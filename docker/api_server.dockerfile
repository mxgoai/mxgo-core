FROM python:3.13-slim-bookworm

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    ffmpeg \
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

# Copy only the relevant application code
COPY mxtoai ./mxtoai
COPY run_api.py .

# Run the API via uvicorn
CMD ["poetry", "run", "uvicorn", "mxtoai.api:app", "--host", "0.0.0.0", "--port", "9292", "--workers", "4"]
