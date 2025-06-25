# 🔧 Environment Variables Reference

This document provides a comprehensive guide to all environment variables used in MXTOAI.

## 📋 Quick Setup Checklist

### ✅ **Minimum Required Setup**
For a basic working installation, you need:

1. **AI Model Configuration**: Edit `model.config.toml` with your AI provider credentials
2. **Application Security**: Set `X_API_KEY` to a secure random string
3. **Database**: Use Docker defaults or configure external database
4. **Email Service**: Configure AWS SES for sending responses

### 🔧 **Core Application Variables**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT` | No | `8000` | API server port |
| `HOST` | No | `0.0.0.0` | API server host |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `IS_PROD` | No | `false` | Production mode flag |
| `X_API_KEY` | **Yes** | - | API authentication key |

### 🤖 **AI Model Configuration**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LITELLM_CONFIG_PATH` | No | `model.config.toml` | Path to model configuration |
| `LITELLM_DEFAULT_MODEL_GROUP` | **Yes** | - | Default model group name |
| `HF_TOKEN` | Conditional | - | Hugging Face token (required for HF models) |

> **Note**: Primary AI model configuration is done via `model.config.toml`, not environment variables.

### 💾 **Infrastructure Services**

#### PostgreSQL Database
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_HOST` | **Yes** | `postgres` | Database host |
| `DB_PORT` | No | `5432` | Database port |
| `DB_NAME` | **Yes** | `mxtoai` | Database name |
| `DB_USER` | **Yes** | `mxtoai` | Database username |
| `DB_PASSWORD` | **Yes** | - | Database password |

#### Redis Cache
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_HOST` | **Yes** | `redis` | Redis host |
| `REDIS_PORT` | No | `6379` | Redis port |
| `REDIS_DB` | No | `0` | Redis database number |
| `REDIS_PASSWORD` | Recommended | - | Redis password |

#### RabbitMQ Message Queue
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RABBITMQ_HOST` | **Yes** | `rabbitmq` | RabbitMQ host |
| `RABBITMQ_PORT` | No | `5672` | RabbitMQ port |
| `RABBITMQ_USER` | **Yes** | `guest` | RabbitMQ username |
| `RABBITMQ_PASSWORD` | **Yes** | `guest` | RabbitMQ password |
| `RABBITMQ_VHOST` | No | `/` | RabbitMQ virtual host |
| `RABBITMQ_HEARTBEAT` | No | `60` | Connection heartbeat interval |

#### Supabase (For signups/auth)
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SUPABASE_URL` | Conditional | - | Supabase project URL |
| `SUPABASE_KEY` | Conditional | - | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Conditional | - | Supabase service role key |

### �� **Email Service (AWS SES)**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_REGION` | **Yes** | - | AWS region (e.g., `us-east-1`) |
| `AWS_ACCESS_KEY_ID` | **Yes** | - | AWS access key ID |
| `AWS_SECRET_ACCESS_KEY` | **Yes** | - | AWS secret access key |
| `SENDER_EMAIL` | **Yes** | - | Verified sender email address |

### 🔍 **Search Services (Optional)**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SERPAPI_API_KEY` | No | - | SerpAPI key for Google search (premium) |
| `SERPER_API_KEY` | No | - | Serper key for Google search (premium) |
| `BRAVE_SEARCH_API_KEY` | No | - | Brave Search API key (moderate cost) |

**Search Provider Hierarchy:**
1. **DDG Search**: Always available (free, built-in)
2. **Brave Search**: Available if `BRAVE_SEARCH_API_KEY` is set
3. **Google Search**: Available if `SERPAPI_API_KEY` or `SERPER_API_KEY` is set

### 🔗 **External APIs (Optional)**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JINA_API_KEY` | No | - | Jina AI for deep research functionality |
| `RAPIDAPI_KEY` | No | - | RapidAPI for LinkedIn and other services |

### 📊 **Monitoring & Observability**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LOGFIRE_TOKEN` | No | - | Logfire token for advanced logging |

### ⚙️ **Scheduler & Worker Configuration**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SCHEDULER_API_BASE_URL` | No | `http://api_server:8000` | Internal API URL for scheduler |
| `SCHEDULER_API_TIMEOUT` | No | `300` | API timeout in seconds |
| `SCHEDULER_MAX_WORKERS` | No | `5` | Maximum number of worker processes |

### 🛠️ **MCP Tools Configuration(Support in Progress)**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MXTOAI_ENABLE_MCP` | No | `true` | Enable Model Context Protocol tools |
| `MXTOAI_MCP_CONFIG_PATH` | No | `mcp.toml` | Path to MCP configuration |
| `MXTOAI_MCP_TIMEOUT` | No | `30` | MCP connection timeout in seconds |

### 🌐 **Frontend & External URLs**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FRONTEND_URL` | No | - | Frontend application URL |
| `WHITELIST_SIGNUP_URL` | No | - | Whitelist signup page URL |

## 🐳 Docker Configuration

### Service Defaults
When using Docker Compose, these services have built-in defaults:

```yaml
# PostgreSQL
DB_HOST=postgres
DB_NAME=mxtoai
DB_USER=mxtoai
DB_PASSWORD=docker_changeme_123

# Redis
REDIS_HOST=redis
REDIS_PASSWORD=docker_redis_123

# RabbitMQ
RABBITMQ_HOST=rabbitmq
RABBITMQ_USER=docker_guest
RABBITMQ_PASSWORD=docker_guest_123
```

### Port Overrides
You can override Docker ports if needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PORT` | `8000` | External API port |
| `RABBITMQ_MANAGEMENT_PORT` | `15672` | RabbitMQ management UI port |

## 🚀 Deployment Environments

### Development
```bash
# Copy and configure
cp .env.example .env
# Edit with your development values
```

### Production
```bash
# Use stronger defaults
cp .env.example .env.production
# Configure with production values and strong passwords
```

### Docker
```bash
# Uses docker-compose defaults
# Override only what you need in .env
```
