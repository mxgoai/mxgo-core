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

# Install dependencies
RUN poetry config virtualenvs.create false && poetry install --no-root --no-interaction --no-ansi

# Copy only the relevant worker code
COPY mxtoai ./mxtoai

# Run the Dramatiq worker
CMD ["poetry", "run", "dramatiq", "mxtoai.tasks", "--watch", "./mxtoai"]
