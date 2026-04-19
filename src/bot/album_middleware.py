from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)

MAX_TRACKED_ALBUMS = 100


class AlbumMiddleware(BaseMiddleware):
    def __init__(self, latency: float = 1.2) -> None:
        self.latency = latency
        self.albums: dict[str, list[Message]] = {}
        self.flushed: set[str] = set()
        self._lock = asyncio.Lock()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.media_group_id:
            return await handler(event, data)

        group_id = event.media_group_id

        async with self._lock:
            if group_id in self.flushed:
                return
            if group_id not in self.albums:
                if len(self.albums) >= MAX_TRACKED_ALBUMS:
                    oldest = next(iter(self.albums))
                    self.albums.pop(oldest, None)
                    logger.warning("Album buffer full; dropped oldest group %s", oldest)
                self.albums[group_id] = [event]
                is_first = True
            else:
                self.albums[group_id].append(event)
                is_first = False

        if not is_first:
            return

        await asyncio.sleep(self.latency)

        async with self._lock:
            messages = self.albums.pop(group_id, [])
            self.flushed.add(group_id)

        if not messages:
            return

        messages.sort(key=lambda m: m.message_id)
        data["album"] = messages
        return await handler(messages[0], data)
