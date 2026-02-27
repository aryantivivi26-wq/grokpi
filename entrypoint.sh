#!/bin/bash
set -e

# Write SSO key from env if provided and key.txt doesn't exist
if [ -n "$SSO_COOKIE" ] && [ ! -f /app/key.txt ]; then
    echo "$SSO_COOKIE" > /app/key.txt
    echo "[entrypoint] SSO key written to key.txt"
fi

# Ensure media dirs exist
mkdir -p /app/data/images /app/data/videos

echo "[entrypoint] Starting GrokPi Gateway + Bot..."

# Start gateway in background
python main.py &
GATEWAY_PID=$!

# Wait for gateway to be ready
echo "[entrypoint] Waiting for gateway on port ${PORT:-9563}..."
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${PORT:-9563}/health" > /dev/null 2>&1; then
        echo "[entrypoint] Gateway ready!"
        break
    fi
    sleep 1
done

# Start bot if token is configured
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "[entrypoint] Starting Telegram Bot..."
    python -m bot.main &
    BOT_PID=$!
else
    echo "[entrypoint] TELEGRAM_BOT_TOKEN not set, bot skipped."
    BOT_PID=""
fi

# Trap signals for graceful shutdown
shutdown() {
    echo "[entrypoint] Shutting down..."
    [ -n "$BOT_PID" ] && kill $BOT_PID 2>/dev/null
    kill $GATEWAY_PID 2>/dev/null
    wait
    exit 0
}
trap shutdown SIGTERM SIGINT

# Wait for any process to exit
wait -n
EXIT_CODE=$?
echo "[entrypoint] Process exited with code $EXIT_CODE, shutting down..."
shutdown
