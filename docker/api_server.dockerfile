# docker/api_server.Dockerfile

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

# Copy only dependency files to leverage Docker cache
COPY pyproject.toml poetry.lock ./

# Install dependencies (no venv)
RUN poetry config virtualenvs.create false && poetry install --no-root --no-interaction --no-ansi

# Copy the rest of the application
COPY . .

# Expose API port (change as needed)
EXPOSE 8000

# Run the API
CMD ["poetry", "run", "python", "run_api.py"]
