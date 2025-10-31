import argparse
import asyncio
from typing import Dict, Type

from trader.config import get_settings
from trader.logging import configure_logging, get_logger
from trader.services.base import BaseService
from trader.services.data_service import DataService
from trader.services.strategy_service import StrategyService
from trader.services.risk_service import RiskService
from trader.services.execution_service import ExecutionService
from trader.services.reconciliation_service import ReconciliationService
from trader.services.monitor_service import MonitorService


SERVICE_REGISTRY: Dict[str, Type[BaseService]] = {
    "data": DataService,
    "strategy": StrategyService,
    "risk": RiskService,
    "execution": ExecutionService,
    "reconciliation": ReconciliationService,
    "monitor": MonitorService,
}


async def _run_service(service_name: str) -> None:
    settings = get_settings()
    service_cls = SERVICE_REGISTRY[service_name]
    service = service_cls(settings)
    await service.start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a trader service.")
    parser.add_argument(
        "service",
        choices=sorted(SERVICE_REGISTRY.keys()),
        help="Service to launch.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    args = parser.parse_args()

    configure_logging(level=args.log_level)
    logger = get_logger("run_service")
    logger.info("service.starting", service=args.service)

    try:
        asyncio.run(_run_service(args.service))
    except KeyboardInterrupt:
        logger.info("service.stopped_by_user", service=args.service)


if __name__ == "__main__":
    main()
