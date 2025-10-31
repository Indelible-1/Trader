from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict

import ccxt.async_support as ccxt_async  # type: ignore

from ..config import Settings
from ..events import Event
from ..logging import get_logger
from .base import BaseService


logger = get_logger(__name__)


class DataService(BaseService):
    """Fetches market data from configured exchanges and publishes to Redis Streams."""

    def __init__(self, settings: Settings, poll_interval: float = 60.0):
        super().__init__(settings)
        self.poll_interval = poll_interval
        self._clients: Dict[str, Any] = {}

    async def setup(self) -> None:
        await super().setup()
        for exchange_conf in self.settings.exchanges:
            module = exchange_conf.get("module", "ccxt.binanceusdm")
            client_cls = getattr(ccxt_async, module.split(".")[-1])
            client = client_cls(
                {
                    "apiKey": exchange_conf.get("api_key"),
                    "secret": exchange_conf.get("api_secret"),
                    "enableRateLimit": True,
                }
            )
            if exchange_conf.get("sandbox"):
                if hasattr(client, "set_sandbox_mode"):
                    client.set_sandbox_mode(True)
            self._clients[exchange_conf["name"]] = client
            logger.info(
                "data_service.exchange_initialized",
                exchange=exchange_conf["name"],
                module=module,
            )

    async def run(self) -> None:
        while not self.is_stopping:
            await self._poll_once()
            await asyncio.sleep(self.poll_interval)

    async def _poll_once(self) -> None:
        streams = self.settings.redis.streams
        for exchange_conf in self.settings.exchanges:
            exchange_name = exchange_conf["name"]
            symbols = exchange_conf.get("symbols", [])
            client = self._clients.get(exchange_name)
            if not client:
                continue
            for symbol in symbols:
                try:
                    ohlcv = await client.fetch_ohlcv(symbol, timeframe="1m", limit=2)
                    event = Event(
                        type="market_data",
                        payload={
                            "exchange": exchange_name,
                            "symbol": symbol,
                            "timeframe": "1m",
                            "data": ohlcv,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )
                    await self.bus.publish(streams.market_data, event)
                    logger.info(
                        "data_service.published",
                        exchange=exchange_name,
                        symbol=symbol,
                        points=len(ohlcv),
                    )
                except Exception as exc:
                    logger.error(
                        "data_service.fetch_failed",
                        exchange=exchange_name,
                        symbol=symbol,
                        error=str(exc),
                    )

    async def stop(self) -> None:
        await super().stop()
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
