---
sidebar_position: 5
---

# Self-Hosting Guide

MXGo can be self-hosted on your own infrastructure, giving you complete control over your email processing and data privacy. This guide will walk you through setting up MXGo on your own servers.

## 🚀 Quick Start (5 minutes)

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop) installed and running
- 4GB RAM available for Docker
- 10GB free disk space

### One-Command Setup

```bash
# Clone and start
git clone https://github.com/mxgo/mxgo-core.git
cd mxgo

# Automated setup and start
./scripts/setup-local.sh && ./scripts/start-local.sh
```

### Essential Configuration

After setup, configure these essential variables:

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with essential variables:**
   ```bash
   # Security (Required)
   X_API_KEY=your_secure_random_key_here

   # AI Models (Required)
   LITELLM_DEFAULT_MODEL_GROUP=gpt-4

   # Email Service (Required for sending responses)
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=your_aws_access_key
   AWS_SECRET_ACCESS_KEY=your_aws_secret_key
   SENDER_EMAIL=assistant@yourdomain.com
   ```

3. **Configure AI model in `model.config.toml`:**
   ```toml
   # For OpenAI
   [[model]]
   model_name = "gpt-4"
   litellm_params.model = "gpt-4"
   litellm_params.api_key = "your_openai_api_key_here"

   # For Azure OpenAI
   [[model]]
   model_name = "azure-gpt-4"
   litellm_params.model = "azure/gpt-4"
   litellm_params.api_key = "your_azure_openai_api_key"
   litellm_params.base_url = "https://your-resource.openai.azure.com/"
   litellm_params.api_version = "2023-05-15"
   ```

**That's it!** 🎉

After setup, your services will be available at:
- **API Server**: http://localhost:8000
- **Health Check**: http://localhost:8000/health
- **API Documentation**: http://localhost:8000/docs
- **RabbitMQ Management**: http://localhost:15672 (guest/guest)

## 📧 Setting Up Email Routing with Cloudflare

To receive emails at your custom domain (e.g., `ask@yourdomain.com`), you'll need to set up Cloudflare Email Routing with a Worker.

### 1. Prerequisites
- Domain managed by Cloudflare
- Cloudflare account with Workers enabled

### 2. Deploy the Email Worker

Navigate to the email-worker directory:

```bash
cd email-worker
npm install
```

### 3. Configure the Worker

Edit `email-worker/wrangler.toml`:
```toml
name = "mxgo-email-worker"
main = "src/worker.js"
compatibility_date = "2023-05-15"
workers_dev = true

[vars]
API_ENDPOINT = "https://your-domain.com/process-email"

[env.production.vars]
x_api_key = "your_x_api_key_here"
```

### 4. Deploy to Cloudflare

```bash
# Deploy the worker
npx wrangler deploy

# Set up environment variables
npx wrangler secret put x_api_key
# Enter your X_API_KEY when prompted
```

### 5. Configure Email Routing

1. **In Cloudflare Dashboard:**
   - Go to Email → Email Routing
   - Enable Email Routing for your domain
   - Add MX records (Cloudflare will guide you)

2. **Create Route Rules:**
   - **Catch-all rule**: `*@yourdomain.com` → Send to Worker

3. **Worker Configuration:**
   - Select your deployed `mxgo-email-worker`
   - Save the routing rules

## 📬 Process Your First Email

With Cloudflare Email Routing set up, you can now process emails by simply forwarding them:

### Send a Test Email

```
To: ask@yourdomain.com
Subject: Test Email
Body: Can you help me understand how MXGo works?
```

### What Happens:
1. Email arrives at Cloudflare Email Routing
2. Cloudflare Worker processes the email
3. Worker forwards email data to your MXGo API
4. MXGo processes the email with AI
5. Response is sent back to the original sender

## 🔄 Managing the System

### Docker Commands

```bash
# Check status
docker compose ps

# View logs
docker compose logs api_server
docker compose logs worker

# Restart services
docker compose restart

# Stop everything
docker compose down

# Clean reset (removes data)
docker compose down -v
```

### Monitor Email Processing

```bash
# Check API health
curl http://localhost:8000/health

# View worker logs for email processing
docker compose logs worker

# Check Cloudflare Worker logs
npx wrangler tail
```

## ⚙️ Advanced Configuration

### Optional Environment Variables

Enable additional functionality by adding these to your `.env`:

```bash
# Search APIs
SERPAPI_API_KEY=your_serpapi_key
SERPER_API_KEY=your_serper_key
BRAVE_SEARCH_API_KEY=your_brave_key

# Research APIs
JINA_API_KEY=your_jina_key

# Database (if not using Docker defaults)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mxgo
DB_USER=postgres
DB_PASSWORD=your_password
```

### Email Handles Configuration

Your Cloudflare routing supports all these handles:
- `ask@yourdomain.com` - General purpose
- `summarize@yourdomain.com` - Email summaries
- `research@yourdomain.com` - Deep research
- `news@yourdomain.com` - Personalized news briefings
- `schedule@yourdomain.com` - Task scheduling
- `meeting@yourdomain.com` - Meeting scheduling
- `pdf@yourdomain.com` - PDF export
- `fact-check@yourdomain.com` - Fact verification
- `background-research@yourdomain.com` - Background info
- `translate@yourdomain.com` - Translation
- `simplify@yourdomain.com` - Content simplification
- `delete@yourdomain.com` - Cancel scheduled tasks

## 🚀 Production Deployment

For production deployments:

1. **Use a reverse proxy** (nginx, Cloudflare) in front of your API server
2. **Set up SSL certificates** for HTTPS encryption
3. **Configure monitoring** with health checks
4. **Set up log aggregation** for debugging
5. **Configure backups** for your PostgreSQL database
6. **Use environment-specific configs** for different environments
7. **Scale workers** based on email volume

## 🆘 Troubleshooting

### Common Issues

**Docker containers won't start:**
- Check Docker Desktop is running
- Ensure ports 8000, 5432, 5672, 15672 are available
- Try `docker compose down -v` then restart

**API returns 500 errors:**
- Check `docker compose logs api_server`
- Verify your `model.config.toml` has valid API keys
- Ensure database migrations are applied

**Emails not processing:**
- Check worker logs: `docker compose logs worker`
- Verify RabbitMQ is running: http://localhost:15672
- Check Cloudflare Worker logs: `npx wrangler tail`

**Cloudflare Email Routing issues:**
- Verify MX records are set correctly
- Check Email Routing rules in Cloudflare dashboard
- Ensure Worker is deployed and configured
- Verify `x_api_key` secret is set correctly

### Debugging Steps

1. **Test API directly:**
   ```bash
   curl -X POST "http://localhost:8000/health"
   ```

2. **Check Worker logs:**
   ```bash
   cd email-worker
   npx wrangler tail
   ```

3. **Verify email routing:**
   - Send test email to your domain
   - Check Cloudflare Email Routing logs
   - Monitor API server logs

Need more help? Check our [Feedback and Support](./feedback-and-support.md) page.
