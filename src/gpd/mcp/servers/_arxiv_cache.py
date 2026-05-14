"""SQLite-backed cache for arxiv tool results.

Per-user disk cache for tool results that are deterministic given their
input — currently scoped to ``get_abstract``, which has a measured 41%
repeat-rate per BQ trace analysis. Search results are *not* cached
because production queries are 98% unique across users.

Storage: ``~/.arxiv-mcp-server/cache.sqlite`` (sibling to the upstream
markdown cache directory, so it's wiped together when a user resets
their arxiv state). One row per ``(tool, args_hash)`` with a TTL.

Why SQLite over JSON files: atomic single-statement writes; concurrent
readers across multiple bridge processes via the same venv; trivial TTL
expiry via ``WHERE expires_at > ?``. Why not pickling: pickle is a
deserialization-injection surface, and the cached values are MCP tool
results we control the shape of — JSON-string serialization is enough
and survives schema drift trivially.

The cache stores upstream-shaped results (the MCP ``CallToolResult``
content), so reading a cache hit produces the exact same envelope a
fresh upstream call would.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger("gpd.arxiv_bridge.cache")

_CACHE_DIR = Path.home() / ".arxiv-mcp-server"
_CACHE_DB = _CACHE_DIR / "cache.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS arxiv_cache (
    tool TEXT NOT NULL,
    args_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY (tool, args_hash)
)
"""


def _canonicalize_args(args: dict[str, Any]) -> str:
    """Stable JSON serialization of args, used as the cache key input.

    sort_keys ensures equivalent dicts hash to the same key regardless of
    insertion order. separators=(',', ':') removes whitespace so cache
    keys don't drift on Python version upgrades.
    """
    return json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)


def _hash_args(args: dict[str, Any]) -> str:
    return hashlib.sha256(_canonicalize_args(args).encode("utf-8")).hexdigest()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CACHE_DB), timeout=5.0, isolation_level=None)
    try:
        # WAL mode lets concurrent bridge processes read while one writes.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(_SCHEMA)
        yield conn
    finally:
        conn.close()


def _get_sync(tool: str, args: dict[str, Any]) -> Optional[str]:
    """Synchronous cache lookup; returns the stored JSON payload or None."""
    key = _hash_args(args)
    now = time.time()
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT payload FROM arxiv_cache "
                "WHERE tool = ? AND args_hash = ? AND expires_at > ?",
                (tool, key, now),
            ).fetchone()
            if row is None:
                return None
            return row[0]
    except sqlite3.Error as exc:
        logger.info("cache get failed for %s/%s: %s", tool, key[:12], exc)
        return None


def _set_sync(
    tool: str, args: dict[str, Any], payload: str, ttl_seconds: float
) -> None:
    """Synchronous cache write."""
    key = _hash_args(args)
    expires_at = time.time() + ttl_seconds
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO arxiv_cache (tool, args_hash, payload, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (tool, key, payload, expires_at),
            )
    except sqlite3.Error as exc:
        logger.info("cache set failed for %s/%s: %s", tool, key[:12], exc)


async def get(tool: str, args: dict[str, Any]) -> Optional[str]:
    """Async cache lookup. Returns stored JSON payload, or ``None`` on miss/error.

    Always returns ``None`` on any error (SQLite locked, disk I/O failure,
    etc.) so the caller falls through to a live upstream call. The cache
    is opportunistic — it must never break correctness.
    """
    return await asyncio.to_thread(_get_sync, tool, args)


async def set(
    tool: str, args: dict[str, Any], payload: str, ttl_days: int = 30
) -> None:
    """Async cache write. Silent on errors; the upstream result is already
    returned to the caller before we touch the cache."""
    ttl_seconds = float(ttl_days) * 86400.0
    await asyncio.to_thread(_set_sync, tool, args, payload, ttl_seconds)


async def purge_expired() -> int:
    """Delete expired rows. Returns count purged. Intended for a periodic
    sweep — not called on every request."""
    def _purge() -> int:
        try:
            with _connect() as conn:
                cur = conn.execute(
                    "DELETE FROM arxiv_cache WHERE expires_at <= ?", (time.time(),)
                )
                return cur.rowcount
        except sqlite3.Error as exc:
            logger.info("cache purge failed: %s", exc)
            return 0
    return await asyncio.to_thread(_purge)


def _cache_db_path() -> Path:
    """Expose the DB path for tests."""
    return _CACHE_DB
