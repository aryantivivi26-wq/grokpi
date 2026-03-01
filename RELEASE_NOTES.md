# Release Notes

## 2026-03-01 — Gemini Auto-Management (Auto-Login, Auto-Register, Health Monitor)

### ✨ Highlights
- **Auto-Register**: Buat akun Gemini baru otomatis via headless Chrome + generator.email
- **Auto-Login**: Refresh cookies otomatis saat expired via headless Chrome
- **Health Monitor**: Background health check setiap 15 menit, notifikasi admin saat status berubah
- **Server Status UI**: Indikator 🟢/🔴 per server di Gemini menu
- **Cookie Auto-Refresh**: JWT manager otomatis capture Set-Cookie dari response

### 🤖 Bot — Gemini Server Manager
- `/gemini` command — akses langsung ke Gemini Server Manager (tidak perlu lewat /admin)
- 🆕 **Auto-Register** button — buat akun baru tanpa input manual
- 🔄 **Auto-Login** button per server — refresh cookies via headless Chrome
- 📧 **Set Email** per server — konfigurasi email untuk auto-login
- 🩺 **Health Check** — cek status semua server, update indikator 🟢/🔴
- Per-server **info panel** dengan masked cookies, config_id, email, expires
- 5-step **Add Server** flow (secure_c_ses → host_c_oses → csesidx → config_id → email)

### ⚙️ Gateway — API Endpoints
- `GET /admin/gemini/health` — Health check semua Gemini accounts
- `POST /admin/gemini/autologin` — Trigger auto-login untuk account tertentu
- `GET /admin/gemini/autologin/status` — Status last auto-login attempts
- `POST /admin/gemini/autoregister` — Auto-create new Gemini accounts (max 5 per call)

### 🔧 Infrastructure
- Docker image sekarang include **Chromium + ChromeDriver** untuk browser automation
- **DrissionPage** >= 4.0.5 ditambahkan ke requirements
- Background **health scheduler** di bot (configurable interval)
- Auto-login triggered otomatis untuk dead servers

### 📋 New Environment Variables
| Variable | Default | Keterangan |
|----------|---------|------------|
| `GENERATOR_EMAIL_DOMAINS` | _(kosong)_ | Domain untuk temp email (MX → generator.email) |
| `GEMINI_BROWSER_HEADLESS` | `true` | Headless mode Chrome |
| `GEMINI_AUTH_PROXY` | _(kosong)_ | Proxy untuk browser automation |
| `GEMINI_HEALTH_INTERVAL_MINUTES` | `15` | Interval health check (menit) |
| `GEMINI_AUTO_LOGIN_ENABLED` | `true` | Auto-login dead servers |

### 📌 Notes
- Untuk auto-register/auto-login, butuh domain dengan MX record pointing ke `mx.generator.email`
- Docker image ~200MB lebih besar karena Chromium
- Auto-register membutuhkan ~500MB RAM tambahan saat proses

---

## 2026-02-26 — Bot UX, Limits, and Admin Improvements

### ✨ Highlights
- Added full Telegram bot module with image/video/admin/SSO workflows.
- Improved bot UX to be cleaner and more professional:
  - `Clean` button in menus
  - safer message editing (no noisy `message is not modified` crashes)
  - direct media delivery to Telegram (image/video file-first)
- Added `My Limit` feature for users.
- Added per-user daily limits for non-admin users:
  - `USER_DAILY_IMAGE_LIMIT` (default `5`)
  - `USER_DAILY_VIDEO_LIMIT` (default `1`)
- Added `Add SSO Key` directly inside Admin Panel.
- Added `Cancel` flow while entering SSO key input.

### 🔐 Security / Access
- Admin endpoints are protected with API key.
- Bot admin access respects configured admin IDs.

### ⚙️ Config Updates
- New sample env file added: `.env.example`
- New bot limit env vars:
  - `USER_DAILY_IMAGE_LIMIT`
  - `USER_DAILY_VIDEO_LIMIT`

### 🧩 API / Server
- Added admin media listing endpoint for videos (`/admin/videos/list`).
- Improved docs in `README.md` including Windows and Linux run instructions.

### 📌 Notes
- Existing deployments should update `.env` with new bot-related variables.
- For higher concurrency and multi-instance deployments, enable Redis mode.
