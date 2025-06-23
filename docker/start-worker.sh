#!/bin/bash
set -e

echo "Starting Dramatiq worker..."

# Set Python path to include /app for module imports
export PYTHONPATH=/app

# Wait for database to be ready
echo "Waiting for database to be ready..."
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME; do
  echo "Database is unavailable - sleeping"
  sleep 2
done

echo "Database is ready!"

# Wait for RabbitMQ to be ready
echo "Waiting for RabbitMQ to be ready..."
while ! nc -z $RABBITMQ_HOST $RABBITMQ_PORT; do
  echo "RabbitMQ is unavailable - sleeping"
  sleep 2
done

echo "RabbitMQ is ready!"

# Start the worker
echo "Starting Dramatiq worker..."
exec poetry run dramatiq mxtoai.tasks --watch ./mxtoai