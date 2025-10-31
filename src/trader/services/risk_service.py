from __future__ import annotations

import asyncio
from typing import Dict

from ..config import Settings
from ..db import create_session_factory, session_scope
from ..events import Event
from ..logging import get_logger
from ..models import Position
from ..utils.risk import PortfolioState, apply_circuit_breakers
from .base import BaseService


logger = get_logger(__name__)


class RiskService(BaseService):
    """Applies portfolio-level risk checks and publishes approved signals."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._last_id = "0-0"
        self._session_factory = create_session_factory(settings)
        self._equity = 100000.0  # Placeholder until account service feeds real value

    async def run(self) -> None:
        signal_stream = self.settings.redis.streams.signals
        approved_stream = self.settings.redis.streams.approved_signals

        while not self.is_stopping:
            try:
                event, message_id = await self.bus.consume(signal_stream, self._last_id)
                self._last_id = message_id
                await self._handle_signal(event, approved_stream)
            except asyncio.TimeoutError:
                continue

    async def _handle_signal(self, event: Event, approved_stream: str) -> None:
        risk_payload = event.payload.get("risk", {})
        if not risk_payload:
            logger.warning("risk_service.missing_risk_payload", signal=event.payload)
            return

        stop_distance = risk_payload.get("stop_distance")
        position_size = risk_payload.get("position_size")
        if not stop_distance or not position_size:
            logger.warning("risk_service.incomplete_risk_payload", signal=event.payload)
            return

        open_risk = self._calculate_open_risk()
        equity = self._equity
        daily_loss = 0.0  # TODO: integrate with PnL service
        drawdown = 0.0    # TODO: integrate with PnL service

        state = PortfolioState(
            equity=equity,
            open_risk=open_risk + stop_distance * position_size,
            daily_loss=daily_loss,
            cumulative_drawdown=drawdown,
        )
        risk_settings = self.settings.risk.model_dump()
        if apply_circuit_breakers(state, risk_settings):
            logger.error("risk_service.signal_rejected_circuit_breaker", signal=event.payload)
            return

        leverage_limit = risk_settings.get("max_leverage", 1.0)
        notional = position_size
        if notional / equity > leverage_limit:
            logger.warning(
                "risk_service.signal_rejected_leverage",
                notional=notional,
                equity=equity,
            )
            return

        approved_event = Event(
            type="approved_signal",
            payload={
                **event.payload,
                "risk_approved": True,
            },
        )
        await self.bus.publish(approved_stream, approved_event)
        logger.info(
            "risk_service.signal_approved",
            strategy=event.payload.get("strategy"),
            symbol=event.payload.get("symbol"),
        )

    def _calculate_open_risk(self) -> float:
        with session_scope(self._session_factory) as session:
            positions = session.query(Position).all()
            open_risk = 0.0
            for pos in positions:
                stop_distance = abs(pos.entry_price - pos.stop_price)
                open_risk += stop_distance * abs(pos.quantity)
            return open_risk
