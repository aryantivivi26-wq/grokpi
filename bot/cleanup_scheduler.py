"""
Midnight cleanup scheduler (WIB timezone).

Every day at 00:00 WIB:
  1. Announce maintenance to all active users (via broadcast)
  2. Delete all cached images and videos from the gateway server
  3. Clean up old usage records from the database
  4. Announce maintenance complete (~00:10 WIB)
"""

import asyncio
import datetime
import logging
from typing import Optional

from aiogram import Bot

from .client import gateway_client
from . import database as db

logger = logging.getLogger(__name__)

WIB = datetime.timezone(datetime.timedelta(hours=7))

# Announcement messages
MAINT_START_MSG = (
    "🔧 <b>Maintenance Dimulai</b>\n\n"
    "⏰ Waktu: 00:00 - 00:10 WIB\n"
    "📋 Proses: Membersihkan cache foto &amp; video di server.\n\n"
    "Mohon tunggu sebentar, layanan akan kembali normal dalam beberapa menit. 🙏"
)

MAINT_DONE_MSG = (
    "✅ <b>Maintenance Selesai!</b>\n\n"
    "Cache foto &amp; video berhasil dibersihkan.\n"
    "Layanan sudah kembali normal. Selamat menggunakan! 🚀"
)


class MidnightCleaner:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._bot: Optional[Bot] = None
        self._admin_ids: list[int] = []

    def start(self, bot: Bot, admin_ids: list[int]) -> None:
        self._bot = bot
        self._admin_ids = admin_ids
        self._task = asyncio.create_task(self._loop())
        logger.info("[MidnightCleaner] Scheduler started (WIB midnight cleanup)")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("[MidnightCleaner] Scheduler stopped")

    async def _loop(self) -> None:
        try:
            while True:
                now = datetime.datetime.now(WIB)
                # Calculate next midnight WIB
                tomorrow = now.date() + datetime.timedelta(days=1)
                next_midnight = datetime.datetime.combine(
                    tomorrow,
                    datetime.time(0, 0, 0),
                    tzinfo=WIB,
                )
                wait_seconds = (next_midnight - now).total_seconds()
                logger.info(
                    f"[MidnightCleaner] Next cleanup in {wait_seconds:.0f}s "
                    f"(at {next_midnight.isoformat()})"
                )
                await asyncio.sleep(wait_seconds)
                await self._do_cleanup()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("[MidnightCleaner] Scheduler loop error")

    async def _do_cleanup(self) -> None:
        logger.info("[MidnightCleaner] Starting midnight cleanup...")

        # 1. Announce maintenance start
        await self._broadcast(MAINT_START_MSG)

        # 2. Delete cached media from gateway
        img_deleted = 0
        vid_deleted = 0
        try:
            result = await gateway_client.clear_images()
            img_deleted = result.get("deleted", 0)
            logger.info(f"[MidnightCleaner] Deleted {img_deleted} images")
        except Exception as e:
            logger.warning(f"[MidnightCleaner] Failed to clear images: {e}")

        try:
            result = await gateway_client.clear_videos()
            vid_deleted = result.get("deleted", 0)
            logger.info(f"[MidnightCleaner] Deleted {vid_deleted} videos")
        except Exception as e:
            logger.warning(f"[MidnightCleaner] Failed to clear videos: {e}")

        # 3. Clean up old usage records (keep last 2 days)
        try:
            cleaned = await db.cleanup_old_usage(days_to_keep=2)
            logger.info(f"[MidnightCleaner] Cleaned {cleaned} old usage records")
        except Exception as e:
            logger.warning(f"[MidnightCleaner] Failed to clean usage: {e}")

        # 4. Small delay then announce done
        await asyncio.sleep(10)  # simulate ~10s maintenance window

        done_msg = (
            "✅ <b>Maintenance Selesai!</b>\n\n"
            f"🖼 Image dihapus: <b>{img_deleted}</b>\n"
            f"🎬 Video dihapus: <b>{vid_deleted}</b>\n\n"
            "Layanan sudah kembali normal. Selamat menggunakan! 🚀"
        )
        await self._broadcast(done_msg)
        logger.info("[MidnightCleaner] Midnight cleanup complete")

    async def _broadcast(self, text: str) -> None:
        """Send message to all admin users."""
        if not self._bot:
            return
        for admin_id in self._admin_ids:
            try:
                await self._bot.send_message(admin_id, text)
            except Exception as e:
                logger.warning(f"[MidnightCleaner] Failed to notify admin {admin_id}: {e}")

    async def run_now(self) -> str:
        """Manually trigger cleanup (for admin command)."""
        await self._do_cleanup()
        return "Cleanup complete"


midnight_cleaner = MidnightCleaner()
