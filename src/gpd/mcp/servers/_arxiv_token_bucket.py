"""Process-local token bucket for arxiv-domain HTTP traffic."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_MIN_INTERVAL: float = 3.0

_lock: asyncio.Lock | None = None
_last_request_time: float = 0.0


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


@asynccontextmanager
async def acquire() -> AsyncIterator[None]:
    global _last_request_time
    lock = _get_lock()
    async with lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            yield
        finally:
            _last_request_time = time.monotonic()


def _reset_for_tests() -> None:
    global _lock, _last_request_time
    _lock = None
    _last_request_time = 0.0
