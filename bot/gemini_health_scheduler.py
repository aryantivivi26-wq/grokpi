"""
Background Gemini server health check scheduler.

Runs every GEMINI_HEALTH_INTERVAL_MINUTES (default: 15) and updates
the in-memory status cache in gemini_manager. Notifies admins when
a server transitions from active → dead.
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


class GeminiHealthScheduler:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._bot: Optional[Bot] = None
        self._admin_ids: list[int] = []
        self._gemini_mgr = None  # set on start
        self._prev_statuses: dict[int, str] = {}

    def start(self, bot: Bot, admin_ids: list[int], gemini_mgr) -> None:
        self._bot = bot
        self._admin_ids = admin_ids
        self._gemini_mgr = gemini_mgr
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "[GeminiHealth] Scheduler started (interval: %d min)",
            HEALTH_INTERVAL_MINUTES,
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

            # Detect transitions
            alerts = []
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

                self._prev_statuses[i] = new_status

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

        except Exception as exc:
            logger.warning("[GeminiHealth] Health check failed: %s", exc)


gemini_health_scheduler = GeminiHealthScheduler()
