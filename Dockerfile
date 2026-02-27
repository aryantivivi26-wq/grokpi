FROM python:3.12-slim

LABEL maintainer="GrokPi" \
      description="GrokPi — Grok/Gemini Image & Video API Gateway + Telegram Bot"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Persistent data directories
RUN mkdir -p /app/data/images /app/data/videos

# Volumes for persistent data
VOLUME ["/app/data", "/app/bot.db"]

EXPOSE 9563

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:${PORT:-9563}/health || exit 1

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
