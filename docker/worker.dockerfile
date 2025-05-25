# docker/worker.Dockerfile

FROM python:3.13-slim-bookworm

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Install Poetry
ENV POETRY_VERSION=2.1.3
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Copy only dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false && poetry install --no-root --no-interaction --no-ansi

# Copy rest of the worker code
COPY . .

# Run Dramatiq worker (entrypoint can be adjusted)
CMD ["poetry", "run", "dramatiq", "mxtoai.tasks", "--watch", "./."]
