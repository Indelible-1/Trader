from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import ccxt.async_support as ccxt_async  # type: ignore

from ..config import Settings
from ..db import create_session_factory, session_scope
from ..events import Event
from ..logging import get_logger
from ..models import Order, Position
from .base import BaseService


logger = get_logger(__name__)


class ReconciliationService(BaseService):
    """Continuously verifies that local state matches exchange reality."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._session_factory = create_session_factory(settings)
        self._interval = settings.reconciliation.interval_seconds
        self._clients: Dict[str, Any] = {}

    async def setup(self) -> None:
        await super().setup()
        for exchange_conf in self.settings.exchanges:
            module = exchange_conf.get("module", "ccxt.binanceusdm")
            cls_name = module.split(".")[-1]
            client_cls = getattr(ccxt_async, cls_name)
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

    async def run(self) -> None:
        while not self.is_stopping:
            await self._reconcile_once()
            await asyncio.sleep(self._interval)

    async def _reconcile_once(self) -> None:
        with session_scope(self._session_factory) as session:
            positions: List[Position] = session.query(Position).all()

        for position in positions:
            client = self._clients.get(position.exchange)
            if not client:
                continue
            try:
                exchange_positions = await client.fetch_positions([position.symbol])
                open_orders = await client.fetch_open_orders(symbol=position.symbol)
                await self._verify_position(position, exchange_positions, open_orders)
            except Exception as exc:
                logger.error(
                    "reconciliation.exchange_fetch_failed",
                    exchange=position.exchange,
                    symbol=position.symbol,
                    error=str(exc),
                )

    async def _verify_position(
        self,
        local: Position,
        exchange_positions: List[Dict[str, Any]],
        open_orders: List[Dict[str, Any]],
    ) -> None:
        matching = next((p for p in exchange_positions if p.get("symbol") == local.symbol), None)
        if not matching:
            logger.critical(
                "reconciliation.position_missing_on_exchange",
                symbol=local.symbol,
                exchange=local.exchange,
            )
            return
        qty = matching.get("contracts") or matching.get("positionAmt") or matching.get("size")
        if qty is not None and abs(float(qty)) == 0:
            logger.critical(
                "reconciliation.position_closed_but_local_open",
                symbol=local.symbol,
            )
        if not self._has_reduce_only_stop(local, open_orders):
            logger.critical(
                "reconciliation.stop_missing",
                symbol=local.symbol,
                exchange=local.exchange,
            )
            if self.settings.reconciliation.auto_repair:
                await self._publish_stop_repair(local)

    def _has_reduce_only_stop(self, local: Position, open_orders: List[Dict[str, Any]]) -> bool:
        for order in open_orders:
            if order.get("reduceOnly") and order.get("type", "").lower().startswith("stop"):
                return True
        return False

    async def _publish_stop_repair(self, position: Position) -> None:
        streams = self.settings.redis.streams.reconciliations
        payload = {
            "symbol": position.symbol,
            "exchange": position.exchange,
            "strategy": position.strategy,
            "quantity": position.quantity,
            "stop_price": position.stop_price,
        }
        await self.bus.publish(
            streams,
            Event(
                type="reinstall_stop",
                payload=payload,
            ),
        )
        logger.warning("reconciliation.requested_stop_repair", payload=payload)

    async def stop(self) -> None:
        await super().stop()
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
