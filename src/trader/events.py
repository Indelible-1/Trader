from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import redis.asyncio as redis

from .logging import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class Event:
    type: str
    payload: Dict[str, Any]

    def dumps(self) -> bytes:
        return json.dumps({"type": self.type, "payload": self.payload}).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "Event":
        raw = json.loads(data.decode("utf-8"))
        return cls(type=raw["type"], payload=raw["payload"])


class EventBus:
    """Abstract event bus backed by Redis Streams or in-memory queue."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
        self._queue: Optional[asyncio.Queue[Event]] = None

    async def connect(self) -> None:
        if self.redis_url:
            self._redis = redis.from_url(self.redis_url, decode_responses=False)
            await self._redis.ping()
            logger.info("event_bus.redis_connected", url=self.redis_url)
        else:
            self._queue = asyncio.Queue()
            logger.warning("event_bus.in_memory_mode")

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()
        if self._queue:
            self._queue = None

    async def publish(self, stream: str, event: Event) -> None:
        if self._redis:
            await self._redis.xadd(stream, {"payload": event.dumps()})
        elif self._queue:
            await self._queue.put(event)
        else:
            raise RuntimeError("EventBus is not connected.")

    async def consume(self, stream: str, last_id: str = "$") -> Event:
        if self._redis:
            messages = await self._redis.xread({stream: last_id}, count=1, block=1_000)
            if not messages:
                raise asyncio.TimeoutError
            _, entries = messages[0]
            message_id, fields = entries[0]
            data = fields["payload"]
            if isinstance(data, str):
                data = data.encode("utf-8")
            return Event.from_bytes(data), message_id
        if self._queue:
            event = await self._queue.get()
            return event, ""
        raise RuntimeError("EventBus is not connected.")


def event_from_dict(data: Dict[str, Any]) -> Event:
    return Event(type=data["type"], payload=data.get("payload", {}))


def event_to_dict(event: Event) -> Dict[str, Any]:
    return asdict(event)
