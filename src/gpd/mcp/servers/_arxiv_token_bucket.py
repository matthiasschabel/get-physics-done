"""Process-local token bucket for arxiv-domain HTTP traffic.

Why this exists
---------------
Production tracing showed ~17% of arxiv tool calls failing as a mix of
explicit HTTP 429 and MCP timeouts (the latter being arxiv stalling
under throttle). 75% of timeouts cluster in agentic-loop bursts — the
LLM fires N tool calls in rapid succession, each spawning an arxiv
request before the prior one has cleared arxiv's 1-req/3s ceiling.

The upstream `arxiv_mcp_server` package already has a
``_MIN_REQUEST_INTERVAL = 3.0`` lock in its ``tools/search.py``, but
that lock only covers the API-search path. The HTML fetch in
``tools/download.py``, the semantic_search indexer, and the
`PaperManager.list_resources` enumerator all bypass it. From outside
the subprocess, the bridge can't see the upstream's lock — so we add a
second token bucket *here* that serializes every call our bridge makes
into `session.call_tool(...)`. That way regardless of which upstream
tool path runs, our bridge process can never issue more than one
in-flight arxiv-domain call.

This bucket does NOT replace the upstream lock; it stacks on top of it,
which is fine because both are wait-only (no work is duplicated when
both fire).
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

# Match arxiv's documented limit (1 req / 3s, https://info.arxiv.org/help/api/tou.html).
# Even though Feb 2026 tightening means this no longer guarantees zero 429s,
# going below 3s is explicitly prohibited by ToU.
_MIN_INTERVAL: float = 3.0

_lock: asyncio.Lock | None = None
_last_request_time: float = 0.0


def _get_lock() -> asyncio.Lock:
    """Lazy-create the asyncio.Lock so we bind to the running event loop."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


@asynccontextmanager
async def acquire() -> AsyncIterator[None]:
    """Serialize callers to at most one arxiv-bound request every ``_MIN_INTERVAL`` seconds.

    Usage::

        async with _arxiv_token_bucket.acquire():
            result = await self.session.call_tool(name, args)

    The lock is held for the duration of the request (caller's `with` block).
    On entry, sleeps until at least ``_MIN_INTERVAL`` has passed since the
    previous request completed. On exit, stamps the current time.

    This shape (sleep-inside-lock, stamp-on-exit) means the inter-request
    gap is measured wall-clock from the *previous request's completion*,
    not from its start — matching arxiv's "incorporate a 3 second delay"
    phrasing in the User's Manual.
    """
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
    """Reset module state for unit tests."""
    global _lock, _last_request_time
    _lock = None
    _last_request_time = 0.0
