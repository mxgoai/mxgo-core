# Docker Setup Guide

This guide will help you set up MXTOAI using Docker for easy self-hosting.

MXTOAI uses a simplified Docker architecture with health checks and dependency management built into docker-compose.yml.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) (includes Docker Compose)
- At least 4GB of RAM available for Docker
- At least 10GB of free disk space

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd mxtoai

# Run the setup script
chmod +x scripts/setup-local.sh
./scripts/setup-local.sh
```

### 2. Configure Environment

#### Environment Variables (.env)

**Quick Setup:**
```bash
# Copy the template
cp .env.example .env

# Edit with your values
nano .env  # or your preferred editor
```

**Required Configuration:**
- `X_API_KEY` - Set to a secure random string (32+ characters)
- `LITELLM_DEFAULT_MODEL_GROUP` - Default AI model group (usually "gpt-4")
- AWS SES credentials for email sending (if needed)

**Docker Defaults:**
The Docker setup provides secure defaults for all infrastructure services:
- PostgreSQL, Redis, RabbitMQ are preconfigured
- Only external services need your API keys

📚 **Complete Reference**: See [ENV_VARIABLES.md](ENV_VARIABLES.md) for all configuration options.

#### AI Model Configuration (model.config.toml)
Edit the `model.config.toml` file to configure your AI models:

```toml
# Example for OpenAI
[[model]]
model_name = "gpt-4"
litellm_params = { model = "gpt-4", api_key = "your_openai_api_key_here" }

# Example for Azure OpenAI
[[model]]
model_name = "azure-gpt-4"
litellm_params = {
    model = "azure/gpt-4",
    api_key = "your_azure_openai_api_key_here",
    base_url = "https://your-resource.openai.azure.com/",
    api_version = "2023-05-15"
}
```

### 3. Start Services

```bash
# Start all services
./scripts/start-local.sh

# Or manually with docker-compose
docker-compose up --build
```

This will start:
- **PostgreSQL** - Database (port 5432)
- **Redis** - Cache and session storage (port 6379)
- **RabbitMQ** - Message queue (port 5672, management UI on port 15672)
- **API Server** - Main application (port 8000)
- **Worker** - Background task processor
- **Scheduler** - Scheduled task manager (depends on worker health)

The services start in order based on health checks, with the scheduler waiting for the worker to be healthy before starting.

### 4. Verify Setup

Once all services are running:

1. **API Health Check**: Visit http://localhost:8000/health
2. **RabbitMQ Management**: Visit http://localhost:15672 (guest/guest)
3. **API Documentation**: Visit http://localhost:8000/docs

### Production Deployment

1. **Use external databases**: Evaluate if it's okay to run PostgreSQL and Redis in containers as per task workload, else use external services.
2. **Configure HTTPS**: Use a reverse proxy like nginx or Traefik
3. **Set resource limits**: Configure Docker memory and CPU limits
4. **Enable monitoring**: Set up logging and monitoring
5. **Backup strategy**: Implement database backups

### Docker Compose for Production

```yaml
# docker-compose.prod.yml
version: "3.9"
services:
  api_server:
    # ... same configuration but with:
    restart: always
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'

  worker:
    restart: always
    deploy:
      replicas: 2  # Scale workers based on load
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
```

## Troubleshooting

### Common Issues

1. **Port conflicts**: Change ports in `.env` if default ports are in use
2. **Out of memory**: Increase Docker Desktop memory allocation
3. **Permission errors**: Ensure Docker has necessary permissions
4. **Database connection fails**: Wait for all services to fully start

### Viewing Logs

```bash
# View logs for specific service
docker-compose logs api_server
docker-compose logs worker
docker-compose logs scheduler

# Follow logs in real-time
docker-compose logs -f api_server
```

### Accessing Services

```bash
# Access running container
docker exec -it api_server bash
docker exec -it postgres psql -U mxtoai -d mxtoai

# Check service status
docker-compose ps
```

### Clean Reset

```bash
# Stop all services and remove data
docker-compose down -v

# Remove all images and rebuild
docker-compose down --rmi all -v
docker-compose up --build
```

### Health Checks

All services include health checks:
- **API Server**: `curl http://localhost:8000/health`
- **PostgreSQL**: Built-in `pg_isready`
- **Redis**: Built-in ping
- **RabbitMQ**: Built-in diagnostics