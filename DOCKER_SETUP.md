# 🐳 Docker Setup Guide

This guide will help you set up MXTOAI using Docker for easy self-hosting.

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
Edit the `.env` file that was created and configure your settings:

```bash
# Database settings (can leave as default for local development)
DB_NAME=mxtoai
DB_USER=mxtoai
DB_PASSWORD=changeme

# Redis settings (can leave as default for local development)
REDIS_PASSWORD=changeme

# RabbitMQ settings (can leave as default for local development)
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Required: Configure at least one AI service
OPENAI_API_KEY=your_api_key_here
# OR
AZURE_OPENAI_API_KEY=your_azure_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2023-05-15
```

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
- **Scheduler** - Scheduled task manager

### 4. Verify Setup

Once all services are running:

1. **API Health Check**: Visit http://localhost:8000/health
2. **RabbitMQ Management**: Visit http://localhost:15672 (guest/guest)
3. **API Documentation**: Visit http://localhost:8000/docs

## Service Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│   API Server    │◄───┤   PostgreSQL │    │    RabbitMQ     │
│   (Port 8000)   │    │  (Port 5432) │    │  (Port 5672)    │
└─────────────────┘    └──────────────┘    └─────────────────┘
         │                                           │
         ▼                                           ▼
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│      Redis      │    │    Worker    │    │   Scheduler     │
│   (Port 6379)   │    │  (Background │    │  (APScheduler)  │
└─────────────────┘    │   Tasks)     │    └─────────────────┘
                       └──────────────┘
```

## Production Configuration

### Environment Variables for Production

```bash
# Production settings
ENVIRONMENT=production
IS_PROD=true
DEBUG=false

# Security
SECRET_KEY=your_very_secure_secret_key_here

# Database (use external managed database in production)
DB_HOST=your.database.host
DB_PORT=5432
DB_NAME=mxtoai_production
DB_USER=mxtoai_production_user
DB_PASSWORD=secure_password_here

# Redis (use external managed Redis in production)
REDIS_HOST=your.redis.host
REDIS_PORT=6379
REDIS_PASSWORD=secure_redis_password

# Email (for sending replies)
SMTP_HOST=smtp.yourprovider.com
SMTP_PORT=587
SMTP_USERNAME=your_email@domain.com
SMTP_PASSWORD=your_app_specific_password
FROM_EMAIL=your_email@domain.com
```

### Production Deployment

1. **Use external databases**: Don't run PostgreSQL and Redis in containers in production
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

## Scaling

### Horizontal Scaling

```yaml
# Scale workers for higher throughput
services:
  worker:
    deploy:
      replicas: 3
```

### Load Balancing

For multiple API server instances:

```yaml
services:
  api_server:
    deploy:
      replicas: 2

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    # Configure nginx for load balancing
```

## Monitoring

### Health Checks

All services include health checks:
- **API Server**: `curl http://localhost:8000/health`
- **PostgreSQL**: Built-in `pg_isready`
- **Redis**: Built-in ping
- **RabbitMQ**: Built-in diagnostics

### Metrics

Consider adding:
- Prometheus metrics
- Grafana dashboards
- Log aggregation (ELK stack)
- APM (Application Performance Monitoring)

## Security Considerations

1. **Change default passwords**: Update all default passwords in `.env`
2. **API keys**: Secure your AI service API keys
3. **Network isolation**: Use Docker networks for service isolation
4. **Firewall rules**: Restrict access to only necessary ports
5. **Regular updates**: Keep Docker images and dependencies updated

For production deployments, also consider:
- Container scanning for vulnerabilities
- Secrets management (Docker secrets, Kubernetes secrets)
- Certificate management for HTTPS
- Regular security audits