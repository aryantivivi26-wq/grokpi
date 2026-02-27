# GrokPi — Multi-Backend AI Image/Video API Gateway + Telegram Bot

Gateway API kompatibel OpenAI untuk **generate gambar dan video** menggunakan **Grok (xAI)** dan **Gemini Business (Google)**, dilengkapi **Telegram Bot** dengan fitur subscription, payment QRIS, referral, leaderboard, dan lainnya.

---

## Fitur Utama

### Multi-Backend AI
- **⚡ Grok** — Image & Video generation via xAI WebSocket
- **💎 Gemini Business** — Image & Video generation via Google Discovery Engine
- Toggle model dari bot: `🤖 Model: ⚡ Grok` / `🤖 Model: 💎 Gemini`
- Prefix routing: `grok-*` → Grok, `gemini-*` → Gemini

### Gateway API
- `POST /v1/images/generations` — Generate gambar (Grok / Gemini Imagen)
- `POST /v1/videos/generations` — Generate video (Grok / Gemini Veo)
- `POST /v1/chat/completions` — Chat completion (Gemini)
- `GET /v1/models` — List semua model (10 model)
- Auto CF_CLEARANCE via FlareSolverr (untuk Grok video)
- Auto download media ke cache lokal
- Multi-SSO rotation + retry/fallback
- QRIS webhook: `POST /webhook/qris`

### Telegram Bot
- 🖼 Generate image via tombol (batch prompt untuk Grok)
- 🎬 Generate video via tombol
- 🤖 Pilih model Grok / Gemini (persistent per user)
- 💎 Subscription system (Free / Basic / Premium)
- 💳 Pembayaran QRIS otomatis (Hubify)
- 📦 Topup kuota extra (tidak expired)
- 🔗 Referral program (+10 bonus image)
- 🎁 Trial Premium 12 jam untuk user baru
- 🏆 Leaderboard generator bulanan

---

## Arsitektur

```
┌───────────────────────┐
│   Telegram Users      │
│ (bot @your_bot)       │
└──────────┬────────────┘
           │ aiogram v3 (polling)
           ▼
┌───────────────────────┐     ┌──────────────┐
│   Bot Process         │────▶│  SQLite DB   │
│   (python -m bot.main)│     │  (bot.db)    │
└──────────┬────────────┘     └──────────────┘
           │ HTTP
           ▼
┌───────────────────────┐     ┌──────────────┐
│   Gateway (FastAPI)   │────▶│ FlareSolverr │
│   port 9563           │     │  port 8191   │
│   ┌─────────────────┐ │     └──────────────┘
│   │ BackendRouter   │ │
│   │  ├─ GrokClient  │─┼──▶ grok.com (WSS/HTTPS)
│   │  └─ GeminiClient│─┼──▶ business.gemini.google (HTTPS)
│   └─────────────────┘ │
└───────────────────────┘
```

### Model yang Tersedia

| Model | Backend | Tipe |
|-------|---------|------|
| `grok-imagine` | Grok | Image |
| `grok-2-image` | Grok | Image |
| `grok-2-video` | Grok | Video |
| `gemini-auto` | Gemini | Chat |
| `gemini-2.5-flash` | Gemini | Chat |
| `gemini-2.5-pro` | Gemini | Chat |
| `gemini-3-flash-preview` | Gemini | Chat |
| `gemini-3.1-pro-preview` | Gemini | Chat |
| `gemini-imagen` | Gemini | Image |
| `gemini-veo` | Gemini | Video |

---

## Quick Start — Docker Compose

Cara paling cepat untuk deploy, baik di VPS maupun lokal.

### 1. Clone & Configure

```bash
git clone https://github.com/aryantivivi26-wq/grokpi.git
cd grokpi
cp .env.example .env
nano .env   # Isi semua variabel yang diperlukan
```

### 2. SSO Token Grok

```bash
# Ambil dari grok.com → DevTools → Cookies → "sso"
echo "SSO_TOKEN_KAMU" > key.txt
```

### 3. Jalankan

```bash
docker compose up -d
```

Selesai! Gateway jalan di `http://localhost:9563`, bot otomatis nyala.

```bash
# Verifikasi
curl http://localhost:9563/health
curl http://localhost:9563/v1/models
docker compose logs -f
```

---

## Deploy via Coolify

### 1. Di Coolify Dashboard

1. **New Resource** → **Docker Compose** (atau **Dockerfile**)
2. Connect **GitHub repo**: `aryantivivi26-wq/grokpi`
3. Branch: `main`
4. Build Pack: **Docker Compose** (pakai `docker-compose.yml`)

### 2. Environment Variables

Di tab **Environment**, tambahkan semua variabel dari `.env.example`:

```env
# Wajib
API_KEY=api-key-kamu
TELEGRAM_BOT_TOKEN=123456:ABC...
BOT_ADMIN_IDS=1269254705
SSO_COOKIE=sso_token_grok_kamu

# Gemini (opsional)
GEMINI_ENABLED=true
GEMINI_ACCOUNTS_CONFIG=[{"secure_c_ses":"...","csesidx":"...","config_id":"..."}]

# Internal (jangan diubah)
GATEWAY_BASE_URL=http://127.0.0.1:9563
FLARESOLVERR_URL=http://flaresolverr:8191
GATEWAY_API_KEY=api-key-kamu
```

> **Catatan**: `SSO_COOKIE` otomatis ditulis ke `key.txt` saat container start. Jadi kamu tidak perlu mount file.

### 3. Ports & Volumes

- Expose port: `9563` (atau sesuai `PORT`)
- Coolify otomatis manage volumes dari `docker-compose.yml`

### 4. Deploy

Klik **Deploy**. Coolify akan build image dan jalankan container.

```bash
# Health check
curl https://your-coolify-domain/health
```

### 5. Custom Domain (Opsional)

Di Coolify, tambahkan domain di tab **Domains** untuk akses HTTPS otomatis (Traefik/Caddy). Domain ini juga bisa dipakai untuk webhook QRIS:

```
https://grokpi.yourdomain.com/webhook/qris
```

---

## Deploy Manual (VPS tanpa Docker)

### Requirements

- **OS**: Ubuntu 20.04+ / Debian 11+
- **Python**: 3.10+
- **Docker**: Untuk FlareSolverr (opsional, hanya untuk Grok video)

### Step 1: Install Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git curl sqlite3
```

### Step 2: Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Logout & login ulang agar group docker aktif
```

### Step 3: Clone Repository

```bash
cd ~
git clone https://github.com/aryantivivi26-wq/grokpi.git
cd grokpi
```

### Step 4: Setup Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 5: Jalankan FlareSolverr

```bash
docker run -d \
  --name flaresolverr \
  --restart unless-stopped \
  -p 8191:8191 \
  -e LOG_LEVEL=info \
  ghcr.io/flaresolverr/flaresolverr:latest
```

Verifikasi:
```bash
curl -s http://localhost:8191/ | python3 -m json.tool
# Output: "msg": "FlareSolverr is ready!"
```

### Step 6: Ambil SSO Token Grok

1. Buka [grok.com](https://grok.com) di browser lokal, **login**
2. DevTools (`F12`) → **Application** → **Cookies** → `grok.com`
3. Copy cookie bernama **`sso`**
4. Simpan ke file:

```bash
echo "PASTE_SSO_TOKEN_DISINI" > key.txt
```

### Step 7: Setup Gemini Business (Opsional)

1. Buka [business.gemini.google](https://business.gemini.google) di browser, **login**
2. DevTools (`F12`) → **Application** → **Cookies**
3. Copy:
   - `__Secure-C_SES` → `secure_c_ses`
   - `__Host-C_OSES` → `host_c_oses`
4. Dari URL: `business.gemini.google/app/cid/CONFIG_ID?csesidx=CSESIDX`
   - Path setelah `/cid/` → `config_id`
   - Parameter `csesidx` → `csesidx`
5. Di `.env`, tambahkan:

```env
GEMINI_ENABLED=true
GEMINI_ACCOUNTS_CONFIG=[{"secure_c_ses":"...","host_c_oses":"...","csesidx":"1234","config_id":"uuid-here"}]
```

### Step 8: Buat Telegram Bot

1. Chat [@BotFather](https://t.me/BotFather) di Telegram
2. `/newbot` → ikuti instruksi → dapatkan **BOT_TOKEN**
3. Chat [@userinfobot](https://t.me/userinfobot) → dapatkan **Telegram User ID** kamu (untuk admin)

### Step 9: Konfigurasi `.env`

```bash
cp .env.example .env
nano .env
```

Isi semua variabel:

```env
# ============ Server ============
HOST=0.0.0.0
PORT=9563
DEBUG=false

# ============ API Key ============
API_KEY=ganti-dengan-api-key-rahasia

# ============ Cloudflare (otomatis via FlareSolverr) ============
CF_CLEARANCE=
FLARESOLVERR_URL=http://localhost:8191
CF_REFRESH_INTERVAL=3600

# ============ Telegram Bot ============
TELEGRAM_BOT_TOKEN=123456:ABC-DEF... 
BOT_ADMIN_IDS=123456789
GATEWAY_BASE_URL=http://127.0.0.1:9563
GATEWAY_API_KEY=ganti-dengan-api-key-rahasia

# ============ Gemini Business (Opsional) ============
GEMINI_ENABLED=false
GEMINI_ACCOUNTS_CONFIG=

# ============ QRIS Payment (Hubify) ============
QRIS_API_KEY=sk_xxxxxxxx
QRIS_WEBHOOK_SECRET=whsec_xxxxxxxx
QRIS_BASE_URL=https://qris.hubify.store/api
QRIS_POLL_INTERVAL=10
QRIS_POLL_TIMEOUT=900
```

### Step 10: Jalankan dengan systemd (Production)

**Service Gateway:**

```bash
sudo tee /etc/systemd/system/grokpi-gateway.service << EOF
[Unit]
Description=GrokPi API Gateway
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/grokpi
ExecStart=$HOME/grokpi/.venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PATH=$HOME/grokpi/.venv/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF
```

**Service Bot:**

```bash
sudo tee /etc/systemd/system/grokpi-bot.service << EOF
[Unit]
Description=GrokPi Telegram Bot
After=grokpi-gateway.service
Wants=grokpi-gateway.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/grokpi
ExecStart=$HOME/grokpi/.venv/bin/python -m bot.main
Restart=always
RestartSec=5
Environment=PATH=$HOME/grokpi/.venv/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF
```

**Aktifkan:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now grokpi-gateway grokpi-bot
```

**Cek status:**

```bash
sudo systemctl status grokpi-gateway
sudo systemctl status grokpi-bot
sudo journalctl -u grokpi-gateway -f   # live log gateway
sudo journalctl -u grokpi-bot -f       # live log bot
```

### Step 11: Verifikasi

```bash
# Health check
curl -s http://localhost:9563/health

# Test generate gambar
curl -X POST http://localhost:9563/v1/images/generations \
  -H "Authorization: Bearer API_KEY_KAMU" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a cute cat","n":1}'

# Test generate video
curl -X POST http://localhost:9563/v1/videos/generations \
  -H "Authorization: Bearer API_KEY_KAMU" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"cinematic sunset","duration_seconds":6}'
```

---

## Database (SQLite)

Bot menggunakan **SQLite** (`bot.db` di root project). Database otomatis dibuat saat bot pertama kali jalan.

### Tabel

| Tabel | Fungsi |
|-------|--------|
| `users` | Data user (id, nama, username, first_seen, referral_code, trial_used, referred_by) |
| `subscriptions` | Subscription aktif (tier, expires, granted_by) |
| `daily_usage` | Pemakaian harian per user (images, videos per tanggal WIB) |
| `payments` | Riwayat pembayaran QRIS (transaction_id, tier, duration, amount, status) |
| `referrals` | Tracking referral (referrer_id → referred_id, bonus_given) |
| `extra_quota` | Saldo kuota extra dari topup/referral (images, videos) |
| `reminders_sent` | Tracking reminder expiry yang sudah dikirim |

### Backup Database

```bash
# Backup
cp bot.db bot.db.bak

# Atau dengan sqlite3 dump
sqlite3 bot.db .dump > backup.sql

# Restore
sqlite3 bot.db < backup.sql
```

### Lihat Data

```bash
sqlite3 bot.db

# Daftar tabel
.tables

# Lihat semua user
SELECT * FROM users ORDER BY last_seen DESC LIMIT 20;

# Lihat subscriber aktif
SELECT u.first_name, s.tier, datetime(s.expires, 'unixepoch') as expires
FROM subscriptions s
JOIN users u ON s.user_id = u.user_id
WHERE s.expires > unixepoch() AND s.tier != 'free';

# Lihat total revenue
SELECT SUM(amount) as total_revenue FROM payments WHERE status = 'paid';

# Leaderboard bulan ini
SELECT u.first_name, SUM(d.images) as img, SUM(d.videos) as vid
FROM daily_usage d
JOIN users u ON d.user_id = u.user_id
WHERE d.date_key LIKE strftime('%Y-%m', 'now') || '%'
GROUP BY d.user_id ORDER BY (img + vid) DESC LIMIT 10;

# Lihat referral stats
SELECT r.referrer_id, u.first_name, COUNT(*) as referrals
FROM referrals r
JOIN users u ON r.referrer_id = u.user_id
GROUP BY r.referrer_id ORDER BY referrals DESC;

.quit
```

### Reset Data (Hati-hati!)

```bash
# Reset semua data — bot auto-create DB baru saat restart
rm bot.db

# Atau reset tabel tertentu
sqlite3 bot.db "DELETE FROM daily_usage;"
sqlite3 bot.db "DELETE FROM payments WHERE status = 'expired';"
```

---

## QRIS Payment Webhook

### URL Webhook

Webhook endpoint di gateway:

```
POST http://<IP_VPS>:9563/webhook/qris
```

Jika menggunakan domain + reverse proxy (Nginx/Caddy):

```
POST https://api.yourdomain.com/webhook/qris
```

### Cara Setup di Hubify

1. Login ke [qris.hubify.store](https://qris.hubify.store)
2. Buka **Settings** / **Webhook**
3. Isi:
   - **Webhook URL**: `https://api.yourdomain.com/webhook/qris`
   - **Webhook Secret**: Sama dengan `QRIS_WEBHOOK_SECRET` di `.env`
4. Simpan

### Payload yang Diterima

```json
{
  "amount": 5000,
  "order_id": "GROKPI-123456-ABCD1234",
  "customer_id": "123456",
  "status": "completed",
  "payment_method": "qris",
  "completed_at": "2026-01-15T12:05:00.123+07:00"
}
```

### Verifikasi Keamanan

Webhook diverifikasi dengan dua metode (salah satu):

1. **HMAC-SHA256**: Header `X-Webhook-Signature` = HMAC(body, secret)
2. **Simple Secret**: Header `X-Webhook-Secret` = secret

### Flow Pembayaran

```
User klik "Beli Subscription" / "Topup Kuota" di bot
  │
  ▼
Bot buat transaksi → API Hubify → return QR code
  │
  ▼
User scan QRIS → bayar
  │
  ├──▶ Bot auto-poll status setiap 10s (max 15 menit)
  │    Jika paid → grant subscription / topup
  │
  └──▶ Hubify kirim webhook → Gateway /webhook/qris
       Verifikasi → mark paid → grant subscription / topup
```

Kedua path (poll + webhook) bersifat **idempotent** — hanya di-grant sekali.

### Test Webhook Manual

```bash
# Tanpa verifikasi (jika QRIS_WEBHOOK_SECRET kosong)
curl -X POST http://localhost:9563/webhook/qris \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 5000,
    "order_id": "TEST-123",
    "customer_id": "123456789",
    "status": "completed"
  }'
```

---

## Reverse Proxy (Nginx) — Untuk Domain + HTTPS

Agar webhook QRIS bisa dipanggil dari luar, kamu perlu expose gateway dengan domain + SSL.

### Install Nginx + Certbot

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### Konfigurasi Nginx

```bash
sudo tee /etc/nginx/sites-available/grokpi << 'EOF'
server {
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:9563;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout untuk generate video (bisa lama)
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/grokpi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### SSL dengan Let's Encrypt

```bash
sudo certbot --nginx -d api.yourdomain.com
```

Setelah SSL aktif, webhook URL menjadi:
```
https://api.yourdomain.com/webhook/qris
```

---

## Subscription & Pricing

### Tier

| Tier | Image/hari | Video/hari | Batch Prompt | Cooldown |
|------|-----------|-----------|-------------|----------|
| 🆓 Free | 20 | 10 | 1 | 30 detik |
| ⭐ Basic | 500 | 200 | 3 | 15 detik |
| 💎 Premium | Unlimited | Unlimited | 10 | 5 detik |

### Harga Subscription

| Durasi | Basic | Premium |
|--------|-------|---------|
| Harian (1 hari) | Rp 5.000 | Rp 8.000 |
| Mingguan (7 hari) | Rp 25.000 | Rp 40.000 |
| Bulanan (30 hari) | Rp 75.000 | Rp 120.000 |

### Topup Kuota Extra

| Paket | Harga |
|-------|-------|
| 50 Image | Rp 3.000 |
| 100 Image | Rp 5.000 |
| 20 Video | Rp 5.000 |
| 50 Video | Rp 10.000 |

> Kuota extra **tidak expired** dan dipakai otomatis saat limit harian habis.

### Fitur Tambahan

- **Trial**: User baru otomatis dapat Premium 12 jam gratis
- **Referral**: Ajak teman → kedua pihak dapat +10 extra image
- **Leaderboard**: Top 10 generator bulan ini
- **Reminder**: Notifikasi otomatis H-24h dan H-1h sebelum subscription expired

---

## Cara Kerja FlareSolverr + CF_CLEARANCE

```
FlareSolverr (Docker)
  │ Chromium headless → buka grok.com → bypass Cloudflare challenge
  │ Return: cf_clearance cookie + User-Agent
  ▼
Gateway (cf_solver.py)
  │ Simpan cf_clearance + pakai UA yang sama
  │ Auto-refresh setiap 1 jam (configurable)
  ▼
grok.com REST API
  │ cf_clearance + UA match → ✅ bypass Cloudflare
  ▼
Video generation berhasil!
```

- **Image generation**: Pakai WebSocket, **tidak butuh** cf_clearance
- **Video generation**: Pakai HTTP REST, **butuh** cf_clearance (otomatis via FlareSolverr)

---

## Variabel .env Lengkap

| Variabel | Default | Keterangan |
|----------|---------|------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `9563` | Port server |
| `DEBUG` | `false` | Mode debug |
| `API_KEY` | _(kosong)_ | Bearer token untuk API |
| `CF_CLEARANCE` | _(kosong)_ | Auto-diisi oleh FlareSolverr |
| `FLARESOLVERR_URL` | `http://localhost:8191` | URL FlareSolverr |
| `CF_REFRESH_INTERVAL` | `3600` | Refresh CF tiap N detik |
| `PROXY_URL` | _(kosong)_ | HTTP/SOCKS5 proxy |
| `SSO_ROTATION_STRATEGY` | `hybrid` | round_robin / least_used / hybrid dll |
| `SSO_DAILY_LIMIT` | `10` | Limit per key per 24 jam |
| `GEMINI_ENABLED` | `false` | Aktifkan Gemini backend |
| `GEMINI_ACCOUNTS_CONFIG` | _(kosong)_ | JSON array config akun Gemini |
| `TELEGRAM_BOT_TOKEN` | _(kosong)_ | Token bot dari BotFather |
| `BOT_ADMIN_IDS` | _(kosong)_ | Telegram user ID admin (pisahkan koma) |
| `GATEWAY_BASE_URL` | `http://127.0.0.1:9563` | URL gateway untuk bot |
| `GATEWAY_API_KEY` | _(kosong)_ | API key untuk bot |
| `QRIS_API_KEY` | _(kosong)_ | API key Hubify QRIS |
| `QRIS_WEBHOOK_SECRET` | _(kosong)_ | Secret untuk verifikasi webhook |
| `QRIS_BASE_URL` | `https://qris.hubify.store/api` | Base URL API QRIS |
| `QRIS_POLL_INTERVAL` | `10` | Interval poll status pembayaran (detik) |
| `QRIS_POLL_TIMEOUT` | `900` | Timeout polling (15 menit) |
| `SSO_COOKIE` | _(kosong)_ | SSO token via env (Docker/Coolify) |

---

## Maintenance

### Auto Maintenance

Bot menjalankan **midnight cleanup** setiap 00:00 WIB:
- Hapus cache image/video di server
- Bersihkan usage record lama
- Broadcast notifikasi maintenance ke admin

### Subscription Reminder

Scheduler berjalan setiap 6 jam:
- Cek subscription yang expired dalam 24 jam → kirim reminder
- Cek subscription yang expired dalam 1 jam → kirim reminder urgent

### Update

```bash
cd ~/grokpi
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart grokpi-gateway grokpi-bot
```

### Log

```bash
# Live log
sudo journalctl -u grokpi-gateway -f
sudo journalctl -u grokpi-bot -f

# Log hari ini
sudo journalctl -u grokpi-bot --since today
```

---

## Troubleshooting

| Problem | Solusi |
|---------|--------|
| Video gagal 403 Cloudflare | Pastikan FlareSolverr jalan: `docker ps` & `curl localhost:8191` |
| Gemini 401/403 | Cookie expired — ambil ulang `__Secure-C_SES` dari browser |
| Gemini image lama (~2 menit) | Normal, Google image generation memang lambat |
| Bot tidak respond | Cek token: `docker compose logs -f grokpi` |
| Model tidak berubah di bot | Klik 🤖 Model di menu, pilih Gemini/Grok |
| QRIS webhook tidak masuk | Pastikan port terbuka atau gunakan reverse proxy + domain |
| Database corrupt | Backup lalu hapus: `cp bot.db bot.db.bak && rm bot.db` lalu restart |
| cf_clearance expired | Restart FlareSolverr: `docker restart flaresolverr` |

---

## Struktur Project

```
grokpi/
├── Dockerfile               # Docker image build
├── docker-compose.yml       # Docker Compose (Gateway + FlareSolverr)
├── entrypoint.sh            # Container entrypoint (gateway + bot)
├── main.py                  # FastAPI gateway entry
├── bot.db                   # SQLite database (auto-created)
├── key.txt                  # SSO token(s)
├── .env                     # Konfigurasi
├── .env.example             # Template konfigurasi
├── requirements.txt
├── app/
│   ├── api/
│   │   ├── chat.py          # Chat completion endpoint
│   │   ├── imagine.py       # Image/video generation endpoints
│   │   ├── admin.py         # Admin API endpoints
│   │   └── webhook.py       # QRIS webhook handler
│   ├── backends/
│   │   ├── base.py          # BackendClient ABC
│   │   ├── router.py        # BackendRouter (prefix routing)
│   │   ├── grok/
│   │   │   └── client.py    # GrokBackendClient wrapper
│   │   └── gemini/
│   │       ├── client.py    # GeminiBackendClient
│   │       ├── jwt_manager.py   # JWT HMAC-SHA256
│   │       ├── google_api.py    # Discovery Engine API
│   │       ├── account.py       # Multi-account manager
│   │       ├── message.py       # Context builder
│   │       └── streaming_parser.py  # Google JSON parser
│   ├── core/
│   │   ├── config.py        # Gateway settings
│   │   ├── logger.py
│   │   └── security.py
│   └── services/
│       ├── cf_solver.py     # FlareSolverr integration
│       ├── grok_client.py   # Grok API client
│       └── sso_manager.py   # SSO rotation manager
├── bot/
│   ├── main.py              # Bot entry point
│   ├── config.py            # Bot settings
│   ├── database.py          # SQLite layer (7 tables)
│   ├── keyboards.py         # Inline keyboard definitions
│   ├── ui.py                # UI helpers (clear_state, get_backend)
│   ├── states.py            # FSM states
│   ├── rate_limiter.py      # Tier-based cooldowns
│   ├── subscription_manager.py  # Subscription logic
│   ├── user_limit_manager.py    # Daily limit + extra quota
│   ├── payment_client.py    # QRIS Hubify API client
│   ├── cleanup_scheduler.py # Midnight cleanup + reminder
│   └── handlers/
│       ├── common.py        # /start, /help, /cancel, model toggle
│       ├── image.py         # Image generation
│       ├── video.py         # Video generation
│       ├── subscription.py  # Subscription management
│       ├── payment.py       # QRIS subscription purchase
│       ├── topup.py         # QRIS topup kuota extra
│       ├── referral.py      # Referral program
│       ├── leaderboard.py   # Monthly leaderboard
│       ├── admin.py         # Admin media management
│       ├── admin_users.py   # Admin user management + broadcast
│       └── sso.py           # SSO key management
└── scripts/
    └── probe_video_ws.py    # Video WebSocket probe utility
```

---

## Disclaimer

Gunakan sesuai kebijakan layanan upstream dan akun milik sendiri.
