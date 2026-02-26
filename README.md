# Grok Imagine API Gateway

Gateway API kompatibel OpenAI untuk **generate gambar dan video** menggunakan Grok, dengan cache media lokal, gallery modern, serta manajemen multi-SSO.

## Fitur Utama

- API OpenAI-style:
  - `POST /v1/images/generations`
  - `POST /v1/videos/generations`
  - `POST /v1/chat/completions`
- Generate image via WebSocket Grok (streaming progress didukung)
- Generate video via reverse flow (`media post` + `app-chat stream`)
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
- Dependensi di `requirements.txt`

## Instalasi

```bash
pip install -r requirements.txt
```

## Konfigurasi

Aplikasi akan membuat file `.env` otomatis jika belum ada.

### Konfigurasi minimum

- Isi `key.txt` (1 token SSO per baris)
- Isi `.env`:

```env
HOST=0.0.0.0
PORT=9563
DEBUG=false

API_KEY=your-api-key
CF_CLEARANCE=your-cf-clearance
```

### Variabel penting

- `API_KEY` : Bearer token untuk akses API gateway
- `CF_CLEARANCE` : membantu flow reverse/age verification
- `PROXY_URL` / `HTTP_PROXY` / `HTTPS_PROXY` : proxy opsional
- `SSO_ROTATION_STRATEGY` : `round_robin|least_used|least_recent|weighted|hybrid`
- `SSO_DAILY_LIMIT` : limit harian penggunaan key
- `TELEGRAM_BOT_TOKEN` : token bot Telegram
- `BOT_ADMIN_IDS` : daftar user id admin bot (contoh: `12345,67890`)
- `GATEWAY_BASE_URL` : base URL API gateway untuk bot (default `http://127.0.0.1:9563`)
- `GATEWAY_API_KEY` : API key gateway yang dipakai bot
- `USER_DAILY_IMAGE_LIMIT` : limit harian generate image untuk user biasa (default `5`)
- `USER_DAILY_VIDEO_LIMIT` : limit harian generate video untuk user biasa (default `1`)

Alias yang juga didukung:

- Token bot: `BOT_TOKEN`, `TG_BOT_TOKEN`
- Admin IDs: `ADMIN_ID`, `ADMIN_IDS`, `TELEGRAM_ADMIN_IDS`
- API key bot: jika `GATEWAY_API_KEY` kosong, nilai `API_KEY` tetap terbaca lewat alias

## Menjalankan Server

```bash
python main.py
```

## Menjalankan di Windows (PowerShell)

1. Buat dan aktifkan virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependensi:

```powershell
pip install -r requirements.txt
```

3. Jalankan gateway:

```powershell
python main.py
```

4. (Opsional, terminal lain) Jalankan bot:

```powershell
python -m bot.main
```

## Menjalankan di Linux

1. Buat dan aktifkan virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependensi:

```bash
pip install -r requirements.txt
```

3. Jalankan gateway:

```bash
python main.py
```

4. (Opsional, terminal lain) Jalankan bot:

```bash
python -m bot.main
```

## Menjalankan Telegram Bot

Pastikan `.env` sudah berisi:

```env
TELEGRAM_BOT_TOKEN=isi_dari_botfather
BOT_ADMIN_IDS=123456789
GATEWAY_BASE_URL=http://127.0.0.1:9563
GATEWAY_API_KEY=your-api-key
USER_DAILY_IMAGE_LIMIT=5
USER_DAILY_VIDEO_LIMIT=1
```

Jalankan bot:

```bash
python -m bot.main
```

Rekomendasi production:

- Isi `BOT_ADMIN_IDS` agar hanya admin yang bisa akses panel admin/SSO.
- Gunakan `GATEWAY_API_KEY` yang sama dengan `API_KEY` gateway.
- Jalankan bot sebagai service terpisah (systemd/pm2/supervisor) agar auto-restart saat crash.

Fitur bot terbaru:

- Menu `My Limit` untuk cek sisa limit harian user.
- Admin Panel mendukung `Add SSO Key` langsung dari menu admin.
- Saat flow input key SSO, tersedia tombol `Cancel` untuk kembali ke menu sebelumnya.

Akses:

- Docs (Swagger): `http://127.0.0.1:9563/docs`
- ReDoc: `http://127.0.0.1:9563/redoc`
- Health: `http://127.0.0.1:9563/health`
- Image Gallery: `http://127.0.0.1:9563/gallery`
- Video Gallery: `http://127.0.0.1:9563/video-gallery`

## Autentikasi (Swagger & API)

Semua endpoint `/v1/*` menggunakan Bearer auth saat `API_KEY` di-set.
Endpoint `/admin/*` juga menggunakan Bearer auth saat `API_KEY` di-set.

Header:

```http
Authorization: Bearer <API_KEY>
```

Di Swagger, gunakan tombol **Authorize** (ikon gembok), lalu isi token tanpa kata `Bearer`.

## Contoh Request

### 1) Generate Image

```bash
curl -X POST http://127.0.0.1:9563/v1/images/generations \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a cinematic portrait of a cat",
    "n": 1,
    "aspect_ratio": "9:16"
  }'
```

### 2) Generate Video

```bash
curl -X POST http://127.0.0.1:9563/v1/videos/generations \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "vertical cyberpunk alley, smooth camera movement",
    "aspect_ratio": "9:16",
    "duration_seconds": 6,
    "resolution": "480p",
    "preset": "normal"
  }'
```

### 3) Chat Completions (Image Workflow)

```bash
curl -X POST http://127.0.0.1:9563/v1/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-imagine",
    "messages": [{"role": "user", "content": "gambar seekor kucing imut"}],
    "stream": true
  }'
```

## Endpoint Ringkas

- `GET /` : informasi service
- `GET /health` : health check
- `GET /gallery` : gallery image
- `GET /video-gallery` : gallery video
- `GET /images/{filename}` : static image
- `GET /videos/{filename}` : static video
- `POST /v1/images/generations` : generate image
- `POST /v1/videos/generations` : generate video
- `POST /v1/chat/completions` : chat-compatible image generation
- `GET /admin/status` : status service/admin
- `GET /admin/images/list` : list image cache
- `GET /admin/videos/list` : list video cache
- `DELETE /admin/media/image/{filename}` : hapus image by file
- `DELETE /admin/media/video/{filename}` : hapus video by file

## Struktur Cache Media

- `data/images` : file image cache
- `data/videos` : file video cache

## Catatan Operasional

- Jika video/image reverse flow kena 403, refresh `CF_CLEARANCE` dari browser.
- Jika menggunakan reverse proxy/domain, set `BASE_URL` agar URL media sesuai domain publik.
- Untuk deployment multi-instance, aktifkan Redis agar status rotasi token konsisten.

## Disclaimer

Gunakan sesuai kebijakan layanan upstream dan akun milik sendiri.
