import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ErrorEvent

from .config import settings
from .handlers import get_routers
from . import database as db
from .cleanup_scheduler import midnight_cleaner
from .gemini_health_scheduler import gemini_health_scheduler

logger = logging.getLogger(__name__)


async def main() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN belum diisi di .env")

    logging.basicConfig(level=logging.INFO)

    # --- Initialize SQLite database ---
    await db.get_db()
    logger.info("[Bot] SQLite database initialized at %s", db.DB_PATH)

    # --- Migrate old JSON files if they exist ---
    subs_json = Path(settings.LIMITS_STATE_FILE).parent / "subscriptions.json"
    if settings.LIMITS_STATE_FILE.exists() or subs_json.exists():
        stats = await db.migrate_from_json(settings.LIMITS_STATE_FILE, subs_json)
        if stats["subscriptions"] or stats["usage"]:
            logger.info("[Bot] JSON migration: %s", stats)

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()

    for router in get_routers():
        dp.include_router(router)

    @dp.error()
    async def on_error(event: ErrorEvent) -> None:
        logging.exception("Unhandled bot error: %s", event.exception)
        if event.update and event.update.message:
            try:
                await event.update.message.answer("Terjadi error internal. Coba ulang beberapa saat lagi.")
            except Exception:
                pass

    # --- Start midnight cleanup scheduler ---
    midnight_cleaner.start(bot=bot, admin_ids=settings.admin_ids)

    # --- Start Gemini health check scheduler ---
    from .handlers.gemini import gemini_mgr
    gemini_health_scheduler.start(bot=bot, admin_ids=settings.admin_ids, gemini_mgr=gemini_mgr)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        gemini_health_scheduler.stop()
        midnight_cleaner.stop()
        await db.close_db()
        logger.info("[Bot] Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
