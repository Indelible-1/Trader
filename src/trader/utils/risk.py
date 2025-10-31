from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np

from ..logging import get_logger


logger = get_logger(__name__)


@dataclass
class PortfolioState:
    equity: float
    open_risk: float
    cumulative_drawdown: float
    daily_loss: float
    volatility_scalar: float = 1.0


def calculate_volatility_targeted_position_value(
    equity: float,
    target_portfolio_vol: float,
    asset_vol: float,
) -> float:
    if asset_vol <= 0:
        raise ValueError("Asset volatility must be positive.")
    vol_scalar = target_portfolio_vol / asset_vol
    return equity * vol_scalar


def calculate_position_size(
    equity: float,
    stop_distance: float,
    settings: Dict[str, float],
    asset_vol: float | None = None,
) -> float:
    """Return notional position size respecting volatility targeting and risk caps."""
    max_risk = equity * settings.get("max_risk_per_trade", 0.02)
    if stop_distance <= 0:
        raise ValueError("stop_distance must be positive")
    risk_capped_size = max_risk / stop_distance

    if settings.get("volatility_targeting", {}).get("enabled") and asset_vol:
        target_vol = settings["volatility_targeting"]["target_portfolio_vol"]
        vol_size = calculate_volatility_targeted_position_value(equity, target_vol, asset_vol) / stop_distance
        return min(risk_capped_size, vol_size)
    return risk_capped_size


def apply_circuit_breakers(state: PortfolioState, config: Dict[str, float]) -> bool:
    """Return True if trading should halt."""
    breaker = config.get("circuit_breakers", {})
    if state.daily_loss <= -breaker.get("daily_loss", 1.0) * state.equity:
        logger.error("circuit_breaker.daily_loss", daily_loss=state.daily_loss)
        return True
    if state.cumulative_drawdown <= -breaker.get("total_drawdown", 1.0) * state.equity:
        logger.error("circuit_breaker.drawdown", drawdown=state.cumulative_drawdown)
        return True
    max_heat = config.get("max_portfolio_heat", 0.06) * state.equity
    if state.open_risk > max_heat:
        logger.error("circuit_breaker.portfolio_heat", open_risk=state.open_risk)
        return True
    return False
