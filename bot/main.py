import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ErrorEvent

from .config import settings
from .handlers import get_routers


async def main() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN belum diisi di .env")

    logging.basicConfig(level=logging.INFO)

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

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
