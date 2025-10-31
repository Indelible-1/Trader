from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel, Field


class RedisStreamsConfig(BaseModel):
    market_data: str
    signals: str
    approved_signals: str
    orders: str
    executions: str
    reconciliations: str


class RedisConfig(BaseModel):
    enabled: bool = True
    url: str = "redis://localhost:6379/0"
    client_name: str = "trader-bot"
    streams: RedisStreamsConfig


class DatabaseConfig(BaseModel):
    engine: str = Field(default="sqlite", pattern=r"^(sqlite|postgresql)$")
    url: str
    echo: bool = False
    pool_size: int = 5
    connect_args: Dict[str, Any] = Field(default_factory=dict)


class StrategyConfig(BaseModel):
    name: str
    enabled: bool = True
    module: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class RiskConfig(BaseModel):
    max_risk_per_trade: float = 0.02
    max_portfolio_heat: float = 0.06
    max_leverage: float = 1.5
    volatility_targeting: Dict[str, Any] = Field(default_factory=dict)
    circuit_breakers: Dict[str, Any] = Field(default_factory=dict)


class MonitoringConfig(BaseModel):
    telegram: Dict[str, Any] = Field(default_factory=dict)
    prometheus: Dict[str, Any] = Field(default_factory=dict)
    health_check: Dict[str, Any] = Field(default_factory=dict)


class ReconciliationConfig(BaseModel):
    enabled: bool = True
    interval_seconds: int = 30
    auto_repair: bool = True


class AppConfig(BaseModel):
    environment: str = "development"
    log_level: str = "INFO"
    base_currency: str = "USD"
    dry_run: bool = True


class Settings(BaseModel):
    app: AppConfig
    database: DatabaseConfig
    redis: RedisConfig
    risk: RiskConfig
    strategies: list[StrategyConfig]
    monitoring: MonitoringConfig
    reconciliation: ReconciliationConfig
    exchanges: list[Dict[str, Any]] = Field(default_factory=list)
    backtesting: Dict[str, Any] = Field(default_factory=dict)


def _load_yaml_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found at {path}")
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    return data


@lru_cache(maxsize=1)
def get_settings(config_path: str | None = None) -> Settings:
    """Load configuration from YAML, env vars override via ${VAR} placeholders."""
    candidate_paths = [
        Path(config_path) if config_path else None,
        Path(os.getenv("TRADER_CONFIG", "")) if os.getenv("TRADER_CONFIG") else None,
        Path("config/config.yaml"),
        Path("config/config.example.yaml"),
    ]
    for path in candidate_paths:
        if path and path.exists():
            raw = _load_yaml_config(path)
            resolved = _resolve_env_placeholders(raw)
            return Settings.model_validate(resolved)
    raise FileNotFoundError("Unable to locate configuration file. Set TRADER_CONFIG or provide config/config.yaml.")


def _resolve_env_placeholders(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively resolve ${ENV_VAR} placeholders in config."""
    def resolve(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_key = value[2:-1]
            env_value = os.getenv(env_key)
            if env_value is None:
                raise EnvironmentError(f"Environment variable {env_key} is not set.")
            return env_value
        if isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value

    return resolve(raw)
