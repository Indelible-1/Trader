from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

import numpy as np

from ..config import Settings, StrategyConfig
from ..events import Event
from ..logging import get_logger
from ..utils import calculate_position_size
from .base import BaseService


logger = get_logger(__name__)


class StrategyService(BaseService):
    """Consumes market data, generates trading signals, and publishes to Redis."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.price_history: Dict[Tuple[str, str], Deque[float]] = defaultdict(lambda: deque(maxlen=500))
        self.strategy_configs = {cfg.name: cfg for cfg in settings.strategies if cfg.enabled}
        self._last_id = "0-0"

    async def run(self) -> None:
        market_stream = self.settings.redis.streams.market_data
        signal_stream = self.settings.redis.streams.signals

        if not self.strategy_configs:
            logger.warning("strategy_service.no_strategies_enabled")
            return

        while not self.is_stopping:
            try:
                event, message_id = await self.bus.consume(market_stream, self._last_id)
                self._last_id = message_id
                await self._handle_market_event(event, signal_stream)
            except asyncio.TimeoutError:
                continue

    async def _handle_market_event(self, event: Event, signal_stream: str) -> None:
        exchange = event.payload.get("exchange")
        symbol = event.payload.get("symbol")
        data = event.payload.get("data", [])
        if not data:
            return
        close_price = data[-1][4]

        key = (exchange, symbol)
        history = self.price_history[key]
        history.append(close_price)

        for strategy_name, strategy in self.strategy_configs.items():
            decision = self._evaluate_trend_strategy(strategy, history)
            if decision:
                payload = {
                    "strategy": strategy_name,
                    "exchange": exchange,
                    "symbol": symbol,
                    "decision": decision["action"],
                    "confidence": decision["confidence"],
                    "price": close_price,
                    "risk": decision["risk"],
                }
                await self.bus.publish(signal_stream, Event(type="signal", payload=payload))
                logger.info(
                    "strategy_service.signal_published",
                    strategy=strategy_name,
                    symbol=symbol,
                    exchange=exchange,
                    action=decision["action"],
                )

    def _evaluate_trend_strategy(
        self,
        strategy: StrategyConfig,
        history: Deque[float],
    ) -> Dict[str, float] | None:
        params = strategy.parameters
        fast_period = int(params.get("fast_ma_period", 50))
        slow_period = int(params.get("slow_ma_period", 200))
        atr_period = int(params.get("atr_period", 14))

        if len(history) < max(fast_period, slow_period, atr_period) + 1:
            return None

        prices = np.array(history, dtype=float)
        fast_ma = prices[-fast_period:].mean()
        slow_ma = prices[-slow_period:].mean()
        atr = self._calculate_atr(prices, atr_period)

        if np.isnan(atr) or atr <= 0:
            return None

        action = None
        if fast_ma > slow_ma * 1.001:
            action = "buy"
        elif fast_ma < slow_ma * 0.999:
            action = "sell"

        if not action:
            return None

        stop_distance = atr * float(params.get("atr_multiplier", 2.0))
        risk_settings = self.settings.risk.model_dump()
        position_size = calculate_position_size(
            equity=100000.0,  # Placeholder equity; replace with account data service feed
            stop_distance=stop_distance,
            settings=risk_settings,
            asset_vol=params.get("asset_volatility"),
        )

        return {
            "action": action,
            "confidence": 0.6,
            "risk": {
                "stop_distance": stop_distance,
                "position_size": position_size,
            },
        }

    @staticmethod
    def _calculate_atr(prices: np.ndarray, period: int) -> float:
        if len(prices) <= period:
            return float("nan")
        returns = np.abs(np.diff(prices))
        atr = returns[-period:].mean()
        return float(atr)
