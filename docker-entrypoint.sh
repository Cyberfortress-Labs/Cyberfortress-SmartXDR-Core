#!/bin/bash
set -e

# SmartXDR Core - Docker Entrypoint
# Handles Cloudflare Tunnel setup for Telegram webhook

echo "Starting SmartXDR Core..."

# Function to setup Telegram webhook
setup_telegram_webhook() {
    if [ "$TELEGRAM_BOT_ENABLED" = "true" ] && [ "$TELEGRAM_WEBHOOK_ENABLED" = "true" ] && [ -n "$TELEGRAM_BOT_TOKEN" ]; then
        echo "[SmartXDR] Setting up Telegram webhook..."
        
        if [ -n "$TUNNEL_DOMAIN" ]; then
            # Using named tunnel domain
            WEBHOOK_URL="https://${TUNNEL_DOMAIN}/api/telegram/webhook"
            echo "[SmartXDR] Using named tunnel: $WEBHOOK_URL"
            
            # Wait for tunnel to be ready
            echo "[SmartXDR] Waiting for tunnel to be ready..."
            for i in {1..30}; do
                if curl -s -f "https://${TUNNEL_DOMAIN}/health" > /dev/null 2>&1; then
                    echo "[SmartXDR] Tunnel is ready"
                    break
                fi
                sleep 2
            done
            
            # Set webhook
            echo "[SmartXDR] Setting webhook..."
            RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
                -H "Content-Type: application/json" \
                -d "{\"url\":\"${WEBHOOK_URL}\",\"allowed_updates\":[\"message\",\"callback_query\"],\"drop_pending_updates\":true}")
            
            if echo "$RESPONSE" | grep -q '"ok":true'; then
                echo "[SmartXDR] Webhook set successfully: $WEBHOOK_URL"
            else
                echo "[SmartXDR] Failed to set webhook: $RESPONSE"
            fi
        else
            echo "[SmartXDR] TUNNEL_DOMAIN not set, webhook not configured"
            echo "[SmartXDR] Please set TUNNEL_DOMAIN in .env file"
        fi
    else
        echo "[SmartXDR] Telegram webhook disabled, using polling mode"
    fi
}

# Check if Telegram webhook is enabled (case-insensitive)
TELEGRAM_BOT_ENABLED=$(echo "${TELEGRAM_BOT_ENABLED:-true}" | tr '[:upper:]' '[:lower:]')
TELEGRAM_WEBHOOK_ENABLED=$(echo "${TELEGRAM_WEBHOOK_ENABLED:-false}" | tr '[:upper:]' '[:lower:]')
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TUNNEL_DOMAIN="${TUNNEL_DOMAIN:-}"

echo "DEBUG: TELEGRAM_BOT_ENABLED=$TELEGRAM_BOT_ENABLED"
echo "DEBUG: TELEGRAM_WEBHOOK_ENABLED=$TELEGRAM_WEBHOOK_ENABLED"
echo "DEBUG: TUNNEL_DOMAIN=${TUNNEL_DOMAIN:+***set***}"
echo "DEBUG: TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:+***set***}"

# Setup webhook in background after gunicorn starts
(
    sleep 10  # Wait for gunicorn to be ready
    setup_telegram_webhook
) &

# Start gunicorn
echo "Starting Gunicorn..."
exec gunicorn --config gunicorn.conf.py run:app
