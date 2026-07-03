from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import PRODUCTION, TelegramAPIServer

from bot.handlers import router
from core.settings import settings


async def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("Не задан BOT_TOKEN в .env")

    # logging.basicConfig(level=logging.INFO)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    api_server = PRODUCTION
    if settings.telegram_api_server_url:
        api_server = TelegramAPIServer.from_base(
            settings.telegram_api_server_url,
            is_local=settings.telegram_api_is_local,
        )
    else:
        if settings.max_download_mb > 20:
            logging.warning(
                "MAX_DOWNLOAD_MB=%s, but the official Telegram Bot API download limit is 20 MB. "
                "Configure TELEGRAM_API_SERVER_URL for larger downloads.",
                settings.max_download_mb,
            )
        if settings.max_upload_mb > 50:
            logging.warning(
                "MAX_UPLOAD_MB=%s, but the official Telegram Bot API upload limit is commonly 50 MB. "
                "Configure TELEGRAM_API_SERVER_URL for larger uploads.",
                settings.max_upload_mb,
            )

    # aiogram expects `AiohttpSession.timeout` to be a number (seconds).
    # Passing `aiohttp.ClientTimeout` breaks polling timeout calculations.
    session = AiohttpSession(api=api_server, timeout=settings.telegram_timeout_seconds)
    bot = Bot(token=settings.bot_token, session=session)
    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
