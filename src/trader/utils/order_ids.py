from __future__ import annotations

import hashlib
import time
from typing import Optional


def make_client_order_id(
    strategy: str,
    symbol: str,
    side: str,
    *,
    timestamp_ns: Optional[int] = None,
    nonce: int = 0,
) -> str:
    """Generate deterministic, collision-resistant client order id."""
    ts = timestamp_ns if timestamp_ns is not None else time.time_ns()
    payload = f"{strategy}:{symbol}:{side}:{ts}:{nonce}"
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=12).hexdigest()
