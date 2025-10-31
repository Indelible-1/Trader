from __future__ import annotations

import asyncio
from typing import Any, Dict

import ccxt.async_support as ccxt_async  # type: ignore

from ..config import Settings
from ..db import create_session_factory, session_scope
from ..events import Event
from ..logging import get_logger
from ..models import Order, OrderSide, OrderStatus, OrderType, Position
from ..utils import make_client_order_id, utc_now
from .base import BaseService


logger = get_logger(__name__)


class ExecutionService(BaseService):
    """Submits exchange orders with idempotent IDs and installs server-side stops."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._last_id = "0-0"
        self._session_factory = create_session_factory(settings)
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
            logger.info(
                "execution_service.exchange_initialized",
                exchange=exchange_conf["name"],
                module=module,
            )

    async def run(self) -> None:
        stream = self.settings.redis.streams.approved_signals
        while not self.is_stopping:
            try:
                event, message_id = await self.bus.consume(stream, self._last_id)
                self._last_id = message_id
                await self._handle_signal(event)
            except asyncio.TimeoutError:
                continue

    async def _handle_signal(self, event: Event) -> None:
        payload = event.payload
        exchange_name = payload.get("exchange")
        symbol = payload.get("symbol")
        strategy = payload.get("strategy")
        decision = payload.get("decision")
        risk = payload.get("risk", {})
        client = self._clients.get(exchange_name)
        if not client:
            logger.error("execution_service.unknown_exchange", exchange=exchange_name)
            return

        position_size = risk.get("position_size")
        stop_distance = risk.get("stop_distance")
        if not position_size or not stop_distance:
            logger.error("execution_service.missing_risk_info", payload=payload)
            return

        side = OrderSide.BUY if decision == "buy" else OrderSide.SELL
        client_order_id = make_client_order_id(strategy, symbol, side.value)
        order_type = OrderType.LIMIT
        price = payload.get("price")

        order_request = {
            "symbol": symbol,
            "type": order_type.value,
            "side": side.value,
            "amount": position_size,
            "price": price,
            "params": {
                "clientOrderId": client_order_id,
            },
        }
        if self.settings.app.dry_run:
            logger.info("execution_service.dry_run_order", order=order_request)
            await self._record_order(
                client_order_id=client_order_id,
                exchange=exchange_name,
                strategy=strategy,
                symbol=symbol,
                side=side,
                order_type=order_type,
                price=price,
                quantity=position_size,
                raw_request=order_request,
                raw_response={"status": "dry_run"},
                status=OrderStatus.NEW,
            )
            return

        try:
            response = await client.create_order(**order_request)
            await self._record_order(
                client_order_id=client_order_id,
                exchange=exchange_name,
                strategy=strategy,
                symbol=symbol,
                side=side,
                order_type=order_type,
                price=price,
                quantity=position_size,
                raw_request=order_request,
                raw_response=response,
                status=OrderStatus.PENDING,
            )
            await self._install_stop(
                client=client,
                strategy=strategy,
                exchange=exchange_name,
                symbol=symbol,
                side=side,
                entry_price=price,
                stop_distance=stop_distance,
                position_size=position_size,
            )
        except Exception as exc:
            logger.error(
                "execution_service.order_failed",
                exchange=exchange_name,
                symbol=symbol,
                error=str(exc),
            )

    async def _install_stop(
        self,
        client: Any,
        *,
        strategy: str,
        exchange: str,
        symbol: str,
        side: OrderSide,
        entry_price: float,
        stop_distance: float,
        position_size: float,
    ) -> None:
        stop_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
        stop_price = entry_price - stop_distance if side == OrderSide.BUY else entry_price + stop_distance
        client_order_id = make_client_order_id(strategy, symbol, stop_side.value)
        stop_request = {
            "symbol": symbol,
            "type": OrderType.STOP_MARKET.value,
            "side": stop_side.value,
            "amount": position_size,
            "price": None,
            "params": {
                "clientOrderId": client_order_id,
                "reduceOnly": True,
                "stopPrice": stop_price,
            },
        }
        if self.settings.app.dry_run:
            logger.info("execution_service.dry_run_stop", order=stop_request)
            return
        try:
            response = await client.create_order(**stop_request)
            logger.info(
                "execution_service.stop_installed",
                exchange=exchange,
                symbol=symbol,
                stop_price=stop_price,
            )
            await self._update_position(
                symbol=symbol,
                exchange=exchange,
                strategy=strategy,
                quantity=position_size if side == OrderSide.BUY else -position_size,
                entry_price=entry_price,
                stop_price=stop_price,
            )
        except Exception as exc:
            logger.error(
                "execution_service.stop_install_failed",
                exchange=exchange,
                symbol=symbol,
                error=str(exc),
            )

    async def _record_order(
        self,
        *,
        client_order_id: str,
        exchange: str,
        strategy: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        price: float | None,
        quantity: float,
        raw_request: Dict[str, Any],
        raw_response: Dict[str, Any],
        status: OrderStatus,
    ) -> None:
        with session_scope(self._session_factory) as session:
            order = Order(
                client_order_id=client_order_id,
                strategy=strategy,
                symbol=symbol,
                exchange=exchange,
                side=side,
                type=order_type,
                price=price,
                quantity=quantity,
                raw_request=raw_request,
                raw_response=raw_response,
                status=status,
            )
            session.add(order)

    async def _update_position(
        self,
        *,
        symbol: str,
        exchange: str,
        strategy: str,
        quantity: float,
        entry_price: float,
        stop_price: float,
    ) -> None:
        with session_scope(self._session_factory) as session:
            position = (
                session.query(Position)
                .filter_by(symbol=symbol, exchange=exchange, strategy=strategy)
                .one_or_none()
            )
            if position:
                position.quantity += quantity
                position.entry_price = entry_price
                position.stop_price = stop_price
                position.mark_stop_installed()
            else:
                position = Position(
                    symbol=symbol,
                    exchange=exchange,
                    strategy=strategy,
                    quantity=quantity,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    reduce_only_stop_installed=True,
                    opened_at=utc_now(),
                )
                session.add(position)

    async def stop(self) -> None:
        await super().stop()
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
