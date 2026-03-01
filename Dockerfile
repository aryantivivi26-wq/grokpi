FROM python:3.12-slim

LABEL maintainer="GrokPi" \
      description="GrokPi — Grok/Gemini Image & Video API Gateway + Telegram Bot"

# System deps (including Chromium for Gemini browser automation)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
        chromium chromium-driver \
        fonts-liberation libatk-bridge2.0-0 libatk1.0-0 \
        libcups2 libdrm2 libgbm1 libnss3 libxcomposite1 \
        libxdamage1 libxrandr2 xdg-utils && \
    rm -rf /var/lib/apt/lists/*

# Set Chromium flags for container environment
ENV CHROMIUM_FLAGS="--no-sandbox --disable-dev-shm-usage"

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
