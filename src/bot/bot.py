from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from bot.handlers import router
from core.settings import settings


async def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("Не задан BOT_TOKEN в .env")

    logging.basicConfig(level=logging.INFO)

    # aiogram expects `AiohttpSession.timeout` to be a number (seconds).
    # Passing `aiohttp.ClientTimeout` breaks polling timeout calculations.
    session = AiohttpSession(timeout=settings.telegram_timeout_seconds)
    bot = Bot(token=settings.bot_token, session=session)
    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass