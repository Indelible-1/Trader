from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timezone

from ..logging import get_logger


logger = get_logger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_ntp_sync(max_skew_seconds: float = 1.0) -> None:
    """Best-effort check of NTP synchronization."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "timedatectl",
            "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="ignore")
        if "System clock synchronized: yes" not in output:
            logger.warning("ntp.unsynchronized", output=output)
    except FileNotFoundError:
        logger.warning("ntp.timedatectl_missing")
    except Exception as exc:  # pragma: no cover
        logger.error("ntp.check_failed", error=str(exc))
