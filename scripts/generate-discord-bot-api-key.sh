#!/bin/bash
# Script to generate an API key for the Discord bot service
# This creates a service user and generates an API key for authentication

set -e

# Configuration
SERVER_URL="${OPENNOTES_SERVICE_URL:-http://localhost:8000}"
BOT_USERNAME="discord-bot-service"
BOT_EMAIL="discord-bot@opennotes.local"
BOT_PASSWORD=$(openssl rand -hex 32)

echo "🤖 Generating API key for Discord bot service..."
echo ""
echo "Server: $SERVER_URL"
echo "Username: $BOT_USERNAME"
echo ""

# Step 1: Register the service user
echo "📝 Step 1: Registering service user..."
REGISTER_RESPONSE=$(curl -s -X POST "$SERVER_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"username\": \"$BOT_USERNAME\",
    \"email\": \"$BOT_EMAIL\",
    \"password\": \"$BOT_PASSWORD\",
    \"full_name\": \"Discord Bot Service Account\"
  }")

if echo "$REGISTER_RESPONSE" | grep -q "error\|detail"; then
  echo "⚠️  User may already exist. Attempting to login..."
else
  echo "✅ Service user registered successfully"
fi

# Step 2: Login to get access token
echo "🔐 Step 2: Logging in..."
LOGIN_RESPONSE=$(curl -s -X POST "$SERVER_URL/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$BOT_USERNAME&password=$BOT_PASSWORD")

ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
  echo "❌ Failed to obtain access token"
  echo "Response: $LOGIN_RESPONSE"
  exit 1
fi

echo "✅ Logged in successfully"

# Step 3: Create API key
echo "🔑 Step 3: Creating API key..."
API_KEY_RESPONSE=$(curl -s -X POST "$SERVER_URL/api/v1/users/me/api-keys" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d "{
    \"name\": \"Discord Bot Service Key\",
    \"expires_in_days\": 365
  }")

API_KEY=$(echo "$API_KEY_RESPONSE" | grep -o '"key":"[^"]*"' | cut -d'"' -f4)

if [ -z "$API_KEY" ]; then
  echo "❌ Failed to create API key"
  echo "Response: $API_KEY_RESPONSE"
  exit 1
fi

echo "✅ API key created successfully"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Success! Your Discord bot API key:"
echo ""
echo "OPENNOTES_API_KEY=$API_KEY"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Next steps:"
echo "1. Add this to opennotes/.env:"
echo "   OPENNOTES_API_KEY=$API_KEY"
echo ""
echo "2. Restart the Discord bot:"
echo "   docker compose restart opennotes-discord"
echo ""
echo "⚠️  Keep this key secure! It grants full API access."
echo ""
