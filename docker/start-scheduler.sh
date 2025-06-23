#!/bin/bash
set -e

echo "Starting APScheduler..."

# Set Python path to include /app for module imports
export PYTHONPATH=/app

# Wait for database to be ready
echo "Waiting for database to be ready..."
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME; do
  echo "Database is unavailable - sleeping"
  sleep 2
done

echo "Database is ready!"

# Start the scheduler
echo "Starting APScheduler..."
exec poetry run python -m mxtoai.scheduler_runner