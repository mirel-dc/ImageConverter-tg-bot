from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from bot.config import BOT_TOKEN
from bot.handlers import router


async def main() -> None:
    load_dotenv()
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN в .env")

    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass