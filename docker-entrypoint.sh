#!/bin/bash
set -e

# SmartXDR Core - Docker Entrypoint
# Handles Cloudflare Tunnel setup for Telegram webhook

echo "Starting SmartXDR Core..."

# Check if Telegram webhook is enabled (case-insensitive)
TELEGRAM_BOT_ENABLED=$(echo "${TELEGRAM_BOT_ENABLED:-true}" | tr '[:upper:]' '[:lower:]')
TELEGRAM_WEBHOOK_ENABLED=$(echo "${TELEGRAM_WEBHOOK_ENABLED:-true}" | tr '[:upper:]' '[:lower:]')
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"

echo "DEBUG: TELEGRAM_BOT_ENABLED=$TELEGRAM_BOT_ENABLED"
echo "DEBUG: TELEGRAM_WEBHOOK_ENABLED=$TELEGRAM_WEBHOOK_ENABLED"
echo "DEBUG: TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:+***set***}"

if [ "$TELEGRAM_BOT_ENABLED" = "true" ] && [ "$TELEGRAM_WEBHOOK_ENABLED" = "true" ] && [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "Starting Cloudflare Tunnel for Telegram webhook..."
    
    # Start cloudflared in background
    cloudflared tunnel --url http://localhost:8080 > /tmp/cloudflared.log 2>&1 &
    TUNNEL_PID=$!
    
    # Wait for tunnel URL (max 30 seconds)
    TUNNEL_URL=""
    for i in {1..30}; do
        sleep 1
        # Extract tunnel URL from logs
        TUNNEL_URL=$(grep -oP 'https://[a-z][a-z0-9-]*\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | head -1)
        if [ -n "$TUNNEL_URL" ]; then
            echo "Tunnel URL: $TUNNEL_URL"
            break
        fi
    done
    
    if [ -z "$TUNNEL_URL" ]; then
        echo "Failed to get tunnel URL, webhook not set"
        kill $TUNNEL_PID 2>/dev/null || true
    else
        # Set webhook (with retry for DNS propagation)
        echo "Setting Telegram webhook..."
        WEBHOOK_URL="${TUNNEL_URL}/api/telegram/webhook"
        
        # Wait for DNS propagation and retry
        RESPONSE=""
        for retry in {1..3}; do
            echo "Attempt $retry/3 to set webhook..."
            sleep 5  # Wait for DNS
            
            RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
                -H "Content-Type: application/json" \
                -d "{\"url\":\"${WEBHOOK_URL}\",\"allowed_updates\":[\"message\"],\"drop_pending_updates\":true}")
            
            if echo "$RESPONSE" | grep -q '"ok":true'; then
                break
            fi
            echo "  Retry $retry failed, waiting..."
        done
        
        if echo "$RESPONSE" | grep -q '"ok":true'; then
            echo "Telegram webhook set successfully: $WEBHOOK_URL"
        else
            echo "Failed to set webhook: $RESPONSE"
            kill $TUNNEL_PID 2>/dev/null || true
        fi
    fi
else
    echo "Telegram webhook disabled"
fi

# Start gunicorn
echo "Starting Gunicorn..."
exec gunicorn --config gunicorn.conf.py run:app
