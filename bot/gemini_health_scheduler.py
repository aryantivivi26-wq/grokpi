"""
Background Gemini server health check + auto-login scheduler.

Every GEMINI_HEALTH_INTERVAL_MINUTES (default: 15):
  1. Health check all servers — update status cache
  2. Notify admins on status transitions (active → dead, dead → active)
  3. If a server is dead AND has email configured → trigger auto-login
"""

import asyncio
import logging
import os
from typing import Optional

from aiogram import Bot

from .client import gateway_client
from .gemini_manager import STATUS_ACTIVE, STATUS_DEAD, STATUS_ICONS

logger = logging.getLogger(__name__)

HEALTH_INTERVAL_MINUTES = int(os.environ.get("GEMINI_HEALTH_INTERVAL_MINUTES", "15"))
AUTO_LOGIN_ENABLED = os.environ.get("GEMINI_AUTO_LOGIN_ENABLED", "true").lower() in ("1", "true", "yes")


class GeminiHealthScheduler:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._bot: Optional[Bot] = None
        self._admin_ids: list[int] = []
        self._gemini_mgr = None  # set on start
        self._prev_statuses: dict[int, str] = {}
        self._login_in_progress: set[int] = set()  # indices currently being refreshed

    def start(self, bot: Bot, admin_ids: list[int], gemini_mgr) -> None:
        self._bot = bot
        self._admin_ids = admin_ids
        self._gemini_mgr = gemini_mgr
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "[GeminiHealth] Scheduler started (interval: %d min, auto-login: %s)",
            HEALTH_INTERVAL_MINUTES,
            AUTO_LOGIN_ENABLED,
        )

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("[GeminiHealth] Scheduler stopped")

    async def _loop(self) -> None:
        # Wait a bit after startup before first check
        await asyncio.sleep(30)
        try:
            while True:
                await self._check()
                await asyncio.sleep(HEALTH_INTERVAL_MINUTES * 60)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("[GeminiHealth] Scheduler loop crashed")

    async def _check(self) -> None:
        if not self._gemini_mgr:
            return

        try:
            health = await gateway_client.gemini_health()
            accounts = health.get("accounts", [])
            self._gemini_mgr.update_status(accounts)

            # Detect transitions + collect dead servers for auto-login
            alerts = []
            dead_with_email = []

            for i, acc in enumerate(accounts):
                new_status = acc.get("status", "unknown")
                old_status = self._prev_statuses.get(i)

                if old_status == STATUS_ACTIVE and new_status == STATUS_DEAD:
                    error = acc.get("error", "")
                    alerts.append(
                        f"🔴 <b>Server {i + 1} DOWN!</b>\n"
                        f"Status: {old_status} → {new_status}\n"
                        f"Error: {error[:100]}"
                    )
                elif old_status == STATUS_DEAD and new_status == STATUS_ACTIVE:
                    alerts.append(
                        f"🟢 <b>Server {i + 1} RECOVERED!</b>\n"
                        f"Status: {old_status} → {new_status}"
                    )

                # Track dead servers with email for auto-login
                if new_status == STATUS_DEAD:
                    local_acc = self._gemini_mgr.get_account(i)
                    if local_acc and local_acc.get("email"):
                        dead_with_email.append((i, local_acc))

                self._prev_statuses[i] = new_status

            # Notify admins
            if alerts and self._bot:
                text = "🩺 <b>Gemini Health Alert</b>\n\n" + "\n\n".join(alerts)
                for admin_id in self._admin_ids:
                    try:
                        await self._bot.send_message(admin_id, text)
                    except Exception as exc:
                        logger.warning("Failed to notify admin %d: %s", admin_id, exc)

            active = sum(1 for a in accounts if a.get("status") == STATUS_ACTIVE)
            total = len(accounts)
            logger.info("[GeminiHealth] Check complete: %d/%d active", active, total)

            # Auto-login dead servers that have email configured
            if AUTO_LOGIN_ENABLED and dead_with_email:
                for idx, acc_data in dead_with_email:
                    if idx in self._login_in_progress:
                        logger.info("[GeminiHealth] Server %d already being refreshed, skip", idx + 1)
                        continue
                    asyncio.create_task(self._auto_login(idx, acc_data))

        except Exception as exc:
            logger.warning("[GeminiHealth] Health check failed: %s", exc)

    async def _auto_login(self, idx: int, acc_data: dict) -> None:
        """Trigger auto-login for a dead server."""
        email = acc_data.get("email", "")
        self._login_in_progress.add(idx)
        logger.info("[GeminiHealth] Auto-login starting for Server %d (%s)", idx + 1, email)

        # Notify admins
        if self._bot:
            text = (
                f"🔄 <b>Auto-Login Server {idx + 1}</b>\n\n"
                f"📧 Email: {email}\n"
                f"⏳ Headless Chrome login dimulai..."
            )
            for admin_id in self._admin_ids:
                try:
                    await self._bot.send_message(admin_id, text)
                except Exception:
                    pass

        try:
            result = await gateway_client.gemini_autologin(
                account_index=idx,
                email=email,
                mail_provider=acc_data.get("mail_provider", "generatoremail"),
            )

            if result.get("success"):
                config = result.get("config", {})
                self._gemini_mgr.update_account_cookies(idx, config)

                # Reload gateway
                accounts_json = self._gemini_mgr.get_config_json()
                await gateway_client.reload_gemini(accounts_json)

                logger.info("[GeminiHealth] Auto-login SUCCESS for Server %d", idx + 1)

                if self._bot:
                    text = (
                        f"✅ <b>Auto-Login Server {idx + 1} Berhasil!</b>\n\n"
                        f"📧 Email: {email}\n"
                        f"🔑 Cookies baru di-update.\n"
                        f"⏰ Expires: {config.get('expires_at', '?')}\n"
                        f"🔄 Gateway reloaded."
                    )
                    for admin_id in self._admin_ids:
                        try:
                            await self._bot.send_message(admin_id, text)
                        except Exception:
                            pass
            else:
                error = result.get("error", "Unknown error")
                logger.warning("[GeminiHealth] Auto-login FAILED for Server %d: %s", idx + 1, error)

                if self._bot:
                    text = (
                        f"❌ <b>Auto-Login Server {idx + 1} Gagal</b>\n\n"
                        f"📧 Email: {email}\n"
                        f"Error: {error[:200]}"
                    )
                    for admin_id in self._admin_ids:
                        try:
                            await self._bot.send_message(admin_id, text)
                        except Exception:
                            pass

        except Exception as exc:
            logger.error("[GeminiHealth] Auto-login error for Server %d: %s", idx + 1, exc)
        finally:
            self._login_in_progress.discard(idx)


gemini_health_scheduler = GeminiHealthScheduler()
