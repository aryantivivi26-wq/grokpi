# Grok Imagine API Gateway

Gateway API kompatibel OpenAI untuk **generate gambar dan video** menggunakan Grok, dengan cache media lokal, gallery modern, serta manajemen multi-SSO.

## Fitur Utama

- API OpenAI-style:
  - `POST /v1/images/generations`
  - `POST /v1/videos/generations`
  - `POST /v1/chat/completions`
- Generate image via WebSocket Grok (streaming progress didukung)
- Generate video via reverse flow (`media post` + `app-chat stream`)
- **Auto CF_CLEARANCE via FlareSolverr** — tidak perlu ambil manual dari browser
- Auto download hasil media ke cache lokal:
  - Image ke `data/images`
  - Video ke `data/videos`
- Gallery modern:
  - `GET /gallery` (image)
  - `GET /video-gallery` (video)
- Delete media per item langsung dari gallery (image/video)
- Multi-SSO rotation strategy + retry/fallback
- Dukungan proxy HTTP/HTTPS/SOCKS5
- Dukungan Redis (opsional) untuk status rotasi SSO
- Telegram bot modular (`bot/`) dengan UI tombol untuk image/video/admin/SSO
  - Generate image/video via tombol
  - Kirim hasil media langsung ke Telegram (bukan link, fallback ke link jika perlu)
  - Admin media manager (list + delete image/video cache)
  - Admin Panel bisa langsung `Add SSO Key`
  - Flow `Add SSO Key` punya tombol `Cancel`
  - Limit harian user biasa + menu `My Limit` (admin tetap unlimited)

## Requirement

- Python 3.10+
- Docker (untuk FlareSolverr)
- VPS minimal: **2 vCPU, 2 GB RAM, 10 GB disk** (rekomendasi 4 GB RAM)
- Dependensi di `requirements.txt`

---

## Instalasi di VPS (Ubuntu)

### 1. Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Logout & login ulang agar group docker aktif
```

### 2. Install Python & Git

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

### 3. Clone Repository

```bash
git clone https://github.com/aryantivivi26-wq/grok.git
cd grok
```

### 4. Setup Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5. Jalankan FlareSolverr

FlareSolverr dibutuhkan untuk **auto-refresh `cf_clearance`** agar video generation bisa berjalan.

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
# Harus muncul: "msg": "FlareSolverr is ready!"
```

### 6. Ambil SSO Token Grok

1. Buka [grok.com](https://grok.com) di browser lokal, **login**
2. DevTools (`F12`) → **Application** → **Cookies** → `grok.com`
3. Copy nilai cookie bernama **`sso`**
4. Buat file `key.txt` di root project:

```bash
echo "PASTE_SSO_TOKEN_DISINI" > key.txt
```

> SSO token tahan berbulan-bulan, cukup ambil sekali.

### 7. Konfigurasi `.env`

```bash
nano .env
```

Isi minimal:

```env
# ============ Server ============
HOST=0.0.0.0
PORT=9563
DEBUG=false

# ============ API Key ============
API_KEY=ganti-dengan-api-key-kamu

# ============ Cloudflare (otomatis via FlareSolverr) ============
# Biarkan kosong, akan diisi otomatis oleh FlareSolverr
CF_CLEARANCE=

# ============ FlareSolverr ============
FLARESOLVERR_URL=http://localhost:8191
CF_REFRESH_INTERVAL=3600

# ============ Telegram Bot (opsional) ============
TELEGRAM_BOT_TOKEN=isi-dari-botfather
BOT_ADMIN_IDS=id-telegram-kamu
GATEWAY_BASE_URL=http://127.0.0.1:9563
GATEWAY_API_KEY=ganti-dengan-api-key-kamu
USER_DAILY_IMAGE_LIMIT=5
USER_DAILY_VIDEO_LIMIT=1
```

### 8. Jalankan Gateway + Bot

**Opsi A: Langsung di terminal**

```bash
# Terminal 1 - Gateway
source .venv/bin/activate
python main.py

# Terminal 2 - Bot (opsional)
source .venv/bin/activate
python -m bot.main
```

**Opsi B: Menggunakan systemd (rekomendasi production)**

Buat service gateway:

```bash
sudo tee /etc/systemd/system/grok-gateway.service << 'EOF'
[Unit]
Description=Grok Imagine API Gateway
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/grok
ExecStart=/home/$USER/grok/.venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PATH=/home/$USER/grok/.venv/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF
```

Buat service bot:

```bash
sudo tee /etc/systemd/system/grok-bot.service << 'EOF'
[Unit]
Description=Grok Telegram Bot
After=grok-gateway.service
Wants=grok-gateway.service

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/grok
ExecStart=/home/$USER/grok/.venv/bin/python -m bot.main
Restart=always
RestartSec=5
Environment=PATH=/home/$USER/grok/.venv/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF
```

Aktifkan dan jalankan:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now grok-gateway grok-bot
```

Cek status:

```bash
sudo systemctl status grok-gateway
sudo systemctl status grok-bot
sudo journalctl -u grok-gateway -f   # live log gateway
sudo journalctl -u grok-bot -f       # live log bot
```

### 9. Verifikasi

```bash
# Cek gateway
curl -s http://localhost:9563/health

# Cek status + CF solver
curl -s http://localhost:9563/admin/status \
  -H "Authorization: Bearer API_KEY_KAMU" | python3 -m json.tool

# Test generate gambar
curl -X POST http://localhost:9563/v1/images/generations \
  -H "Authorization: Bearer API_KEY_KAMU" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a cute cat","n":1}'

# Test generate video
curl -X POST http://localhost:9563/v1/videos/generations \
  -H "Authorization: Bearer API_KEY_KAMU" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"cinematic sunset","duration_seconds":6,"resolution":"480p","preset":"normal"}'
```

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

- **Image generation**: Pakai WebSocket, tidak butuh cf_clearance
- **Video generation**: Pakai HTTP REST, butuh cf_clearance (otomatis via FlareSolverr)

---

## Variabel .env Lengkap

| Variabel | Default | Keterangan |
|----------|---------|------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `9563` | Port server |
| `DEBUG` | `false` | Mode debug (log ke file) |
| `API_KEY` | _(kosong)_ | Bearer token untuk API |
| `CF_CLEARANCE` | _(kosong)_ | Auto-diisi oleh FlareSolverr |
| `FLARESOLVERR_URL` | `http://localhost:8191` | URL FlareSolverr |
| `CF_REFRESH_INTERVAL` | `3600` | Refresh CF tiap N detik |
| `PROXY_URL` | _(kosong)_ | HTTP/SOCKS5 proxy |
| `SSO_ROTATION_STRATEGY` | `hybrid` | `round_robin\|least_used\|least_recent\|weighted\|hybrid` |
| `SSO_DAILY_LIMIT` | `10` | Limit per key per 24 jam |
| `TELEGRAM_BOT_TOKEN` | _(kosong)_ | Token bot dari BotFather |
| `BOT_ADMIN_IDS` | _(kosong)_ | Telegram user ID admin |
| `GATEWAY_BASE_URL` | `http://127.0.0.1:9563` | URL gateway untuk bot |
| `GATEWAY_API_KEY` | _(kosong)_ | API key untuk bot |
| `USER_DAILY_IMAGE_LIMIT` | `5` | Limit image per user |
| `USER_DAILY_VIDEO_LIMIT` | `1` | Limit video per user |

Alias yang juga didukung:

- Token bot: `BOT_TOKEN`, `TG_BOT_TOKEN`
- Admin IDs: `ADMIN_ID`, `ADMIN_IDS`, `TELEGRAM_ADMIN_IDS`
- API key bot: jika `GATEWAY_API_KEY` kosong, nilai `API_KEY` tetap terbaca lewat alias

## Catatan Operasional

- `cf_clearance` otomatis diambil dan di-refresh oleh FlareSolverr, tidak perlu manual.
- Jika FlareSolverr tidak berjalan, video generation tetap bisa jika `CF_CLEARANCE` diisi manual (harus dari IP yang sama).
- Image generation tidak butuh `CF_CLEARANCE` (pakai WebSocket).
- SSO token (`key.txt`) tahan berbulan-bulan, cukup ambil sekali dari browser.
- Untuk deployment multi-instance, aktifkan Redis agar status rotasi token konsisten.
- Jika menggunakan reverse proxy/domain, set `BASE_URL` agar URL media sesuai domain publik.

## Disclaimer

Gunakan sesuai kebijakan layanan upstream dan akun milik sendiri.
