#!/bin/bash
set -e

echo "Initializing database..."

# Create extensions if they don't exist
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create extensions if needed
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

    -- You can add other initialization SQL here
    CREATE DATABASE mxtoaitest;

    GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $POSTGRES_USER;
EOSQL

echo "Database initialization completed!"
