#!/bin/bash
set -e

echo "🚀 Starting MXTOAI Local Development Environment"
echo "================================================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Please copy .env.example to .env and configure your environment variables."
    echo "Run: cp .env.example .env"
    exit 1
fi

# Check if model config exists
if [ ! -f model.config.toml ]; then
    echo "❌ Model configuration not found!"
    echo "Please copy model.config.example.toml to model.config.toml"
    echo "and configure your AI model credentials."
    echo "Run: cp model.config.example.toml model.config.toml"
    exit 1
fi

# Check if attachments directory exists
if [ ! -d attachments ]; then
    echo "📁 Creating attachments directory..."
    mkdir -p attachments
fi

echo "✅ Environment setup complete!"
echo ""
echo "Starting services with Docker Compose..."
echo "This will start:"
echo "  - PostgreSQL database"
echo "  - Redis cache"
echo "  - RabbitMQ message queue"
echo "  - API server"
echo "  - Background worker"
echo "  - Task scheduler"
echo ""

# Start Docker Compose (use new format if available, fallback to old)
if docker compose version &> /dev/null; then
    docker compose up --build
else
    docker-compose up --build
fi

echo ""
echo "🎉 MXTOAI is now running!"
echo "   API Server: http://localhost:8000"
echo "   RabbitMQ Management: http://localhost:15672 (guest/guest)"
echo ""
echo "To stop all services, press Ctrl+C or run: docker-compose down"
