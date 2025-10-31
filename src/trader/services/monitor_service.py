from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI
from prometheus_client import CollectorRegistry, CONTENT_TYPE_LATEST, Gauge, generate_latest
from starlette.responses import Response
from uvicorn import Config, Server

from ..config import Settings
from ..logging import get_logger
from ..utils import ensure_ntp_sync
from .base import BaseService


logger = get_logger(__name__)


class MonitorService(BaseService):
    """Exposes liveness/readiness endpoints and Prometheus metrics."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._registry = CollectorRegistry()
        self._gauges: Dict[str, Gauge] = {}
        self._server: Server | None = None

    async def setup(self) -> None:
        await super().setup()
        config = self.settings.monitoring
        host = config.prometheus.get("host", "0.0.0.0")
        port = config.prometheus.get("port", 9000)
        app = self._create_app()
        self._server = Server(Config(app=app, host=host, port=port, log_level="info"))

    async def run(self) -> None:
        assert self._server is not None
        await asyncio.gather(
            self._server.serve(),
            self._monitor_ntp(),
        )

    def _create_app(self) -> FastAPI:
        app = FastAPI(title="Trader Monitor")

        @app.get("/live")
        async def live() -> Dict[str, Any]:
            return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

        @app.get("/ready")
        async def ready() -> Dict[str, Any]:
            return {"status": "ready"}

        @app.get("/metrics")
        async def metrics() -> Response:
            data = generate_latest(self._registry)
            return Response(content=data, media_type=CONTENT_TYPE_LATEST)

        return app

    async def _monitor_ntp(self) -> None:
        interval = self.settings.monitoring.health_check.get("ntp_check_interval_seconds", 3600)
        max_skew = self.settings.monitoring.health_check.get("max_clock_skew_seconds", 1.0)
        while not self.is_stopping:
            await ensure_ntp_sync(max_skew)
            await asyncio.sleep(interval)
