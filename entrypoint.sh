#!/bin/bash
set -e

# Ensure persistent dirs exist
mkdir -p /app/db /app/data/images /app/data/videos

# Determine SSO file location (persistent volume)
SSO_FILE="${SSO_FILE:-/app/db/key.txt}"
export SSO_FILE

# If SSO_COOKIE or SSO_TOKENS env is set, always write to file (sync env → file)
if [ -n "$SSO_COOKIE" ]; then
    echo "$SSO_COOKIE" > "$SSO_FILE"
    echo "[entrypoint] SSO key written to $SSO_FILE from SSO_COOKIE"
elif [ -n "$SSO_TOKENS" ]; then
    echo -e "$SSO_TOKENS" > "$SSO_FILE"
    echo "[entrypoint] SSO tokens written to $SSO_FILE from SSO_TOKENS"
fi

# Ensure SSO file exists (empty is OK, bot can add keys later)
touch "$SSO_FILE"

# Show SSO file status
SSO_COUNT=$(grep -c . "$SSO_FILE" 2>/dev/null || echo 0)
echo "[entrypoint] SSO file: $SSO_FILE ($SSO_COUNT keys)"

echo "[entrypoint] Starting Hubify Studio Gateway + Bot..."

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
