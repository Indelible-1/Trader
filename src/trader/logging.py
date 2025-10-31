from __future__ import annotations

import logging
from typing import Optional

import structlog


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Configure both stdlib logging and structlog."""
    logging_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=logging_level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging_level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
