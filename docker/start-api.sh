#!/bin/bash
set -e

echo "Starting API server..."

# Set Python path to include /app for module imports
export PYTHONPATH=/app

# Wait for database to be ready
echo "Waiting for database to be ready..."
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME; do
  echo "Database is unavailable - sleeping"
  sleep 2
done

echo "Database is ready!"

# Run database migrations
echo "Running database migrations..."
cd /app/mxtoai/db
poetry run alembic upgrade head

echo "Database migrations completed!"

# Start the API server
echo "Starting API server..."
exec poetry run uvicorn mxtoai.api:app --host 0.0.0.0 --port 8000 --workers 4