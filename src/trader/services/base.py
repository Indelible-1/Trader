from __future__ import annotations

import abc
import asyncio
from typing import Optional

from ..config import Settings
from ..events import EventBus
from ..logging import get_logger


logger = get_logger(__name__)


class BaseService(abc.ABC):
    """Shared lifecycle helpers for asynchronous services."""

    def __init__(
        self,
        settings: Settings,
        *,
        redis_url: Optional[str] = None,
    ):
        self.settings = settings
        self.redis_url = redis_url or settings.redis.url
        self._bus = EventBus(redis_url=self.redis_url if settings.redis.enabled else None)
        self._stopping = asyncio.Event()

    async def setup(self) -> None:
        await self._bus.connect()
        logger.info("%s.setup_complete", self.__class__.__name__)

    async def start(self) -> None:
        await self.setup()
        try:
            await self.run()
        finally:
            await self._bus.disconnect()

    async def stop(self) -> None:
        self._stopping.set()

    @property
    def is_stopping(self) -> bool:
        return self._stopping.is_set()

    @property
    def bus(self) -> EventBus:
        return self._bus

    @abc.abstractmethod
    async def run(self) -> None:
        ...
