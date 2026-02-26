# Release Notes

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
