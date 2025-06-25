#!/bin/bash
set -e

echo "🔍 MXTOAI Environment Validation"
echo "================================"

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found"
    echo "   Run: cp .env.example .env"
    exit 1
fi

echo "✅ .env file found"

# Source the .env file
set -a
source .env
set +a

# Check critical variables
ERRORS=0

check_required_var() {
    local var_name=$1
    local var_value=$2
    local description=$3
    
    if [ -z "$var_value" ]; then
        echo "❌ $var_name is not set - $description"
        ERRORS=$((ERRORS + 1))
    else
        echo "✅ $var_name is configured"
    fi
}

check_optional_var() {
    local var_name=$1
    local var_value=$2
    local description=$3
    
    if [ -z "$var_value" ]; then
        echo "⚠️  $var_name is not set - $description (optional)"
    else
        echo "✅ $var_name is configured"
    fi
}

echo ""
echo "🔧 Core Application Variables:"
check_required_var "X_API_KEY" "$X_API_KEY" "Required for API authentication"
check_required_var "LITELLM_DEFAULT_MODEL_GROUP" "$LITELLM_DEFAULT_MODEL_GROUP" "Required for AI model routing"

echo ""
echo "💾 Infrastructure Services:"
check_required_var "DB_HOST" "$DB_HOST" "Database host"
check_required_var "DB_NAME" "$DB_NAME" "Database name"
check_required_var "DB_USER" "$DB_USER" "Database user"
check_required_var "DB_PASSWORD" "$DB_PASSWORD" "Database password"

echo ""
echo "📧 Email Service:"
check_required_var "AWS_REGION" "$AWS_REGION" "AWS region for SES"
check_required_var "AWS_ACCESS_KEY_ID" "$AWS_ACCESS_KEY_ID" "AWS access key"
check_required_var "AWS_SECRET_ACCESS_KEY" "$AWS_SECRET_ACCESS_KEY" "AWS secret key"
check_required_var "SENDER_EMAIL" "$SENDER_EMAIL" "Verified sender email"

echo ""
echo "🔍 Search Services (Optional):"
check_optional_var "SERPAPI_API_KEY" "$SERPAPI_API_KEY" "Google search via SerpAPI"
check_optional_var "SERPER_API_KEY" "$SERPER_API_KEY" "Google search via Serper"
check_optional_var "BRAVE_SEARCH_API_KEY" "$BRAVE_SEARCH_API_KEY" "Brave search API"

echo ""
echo "🔗 External APIs (Optional):"
check_optional_var "JINA_API_KEY" "$JINA_API_KEY" "Deep research functionality"
check_optional_var "RAPIDAPI_KEY" "$RAPIDAPI_KEY" "LinkedIn and other services"
check_optional_var "HF_TOKEN" "$HF_TOKEN" "Hugging Face models"

# Check model.config.toml
echo ""
echo "🤖 AI Model Configuration:"
if [ ! -f model.config.toml ]; then
    echo "❌ model.config.toml not found"
    echo "   Run: cp model.config.example.toml model.config.toml"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ model.config.toml found"
    
    # Basic validation of model config
    if grep -q "your_.*_api_key" model.config.toml; then
        echo "⚠️  model.config.toml contains placeholder values"
        echo "   Please update with your actual API keys"
    else
        echo "✅ model.config.toml appears configured"
    fi
fi

echo ""
echo "📊 Validation Summary:"
if [ $ERRORS -eq 0 ]; then
    echo "🎉 Environment validation passed!"
    echo "   Your configuration looks good to go."
else
    echo "❌ Found $ERRORS critical issues"
    echo "   Please fix the issues above before starting the system."
    exit 1
fi

echo ""
echo "💡 Next Steps:"
echo "   1. Start the system: ./scripts/start-local.sh"
echo "   2. Check health: curl http://localhost:8000/health"
echo "   3. View docs: http://localhost:8000/docs"
