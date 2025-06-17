# Database Management

This directory contains database models, migrations, and utilities for mxtoai. We use SQLAlchemy as our ORM and Alembic for database migrations.

## Overview

- **SQLAlchemy ORM**: Defines database models in Python
- **Alembic**: Manages database schema changes over time with versioned migrations
- **alembic_version table**: Tracks current database schema version

## Environment Variables

Set these environment variables before running migrations:

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=your_database
export DB_USER=your_user
export DB_PASSWORD=your_password
```

Alternatively, add them to your `.env` file.

## Common Commands

### Create a new migration
```bash
cd mxtoai/db
alembic revision --autogenerate -m "Description of changes"
```

### Apply migrations
```bash
# Upgrade to latest
alembic upgrade head

# Upgrade to specific version
alembic upgrade <revision_id>
```

### Rollback migrations
```bash
# Rollback one version
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>
```

### View migration history
```bash
alembic history
alembic current
```

## Fixing Migration Forks

When multiple branches create conflicting migrations:

```bash
alembic merge -m "Merge migration forks" <revision1> <revision2>
alembic upgrade head
```

## Critical Warning

⚠️ **ALWAYS REVIEW AUTO-GENERATED MIGRATIONS**: Alembic's `--autogenerate` may create drop statements for tables not defined in our models (e.g., `apscheduler_jobs`, Supabase tables). **Comment out these drop statements** before applying migrations to prevent data loss.

## Best Practices

- **Always review** generated migration files before applying
- Test migrations on development database first
- Back up production database before applying migrations
- Keep migration descriptions clear and descriptive
