"""Unit tests for the per-process arxiv token bucket."""

from __future__ import annotations

import asyncio

import pytest

from gpd.mcp.servers import _arxiv_token_bucket


@pytest.fixture(autouse=True)
def reset_bucket() -> None:
    _arxiv_token_bucket._reset_for_tests()
    yield
    _arxiv_token_bucket._reset_for_tests()


@pytest.mark.asyncio
async def test_first_acquire_does_not_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first call should not pay the 3s gate — _last_request_time starts at 0."""
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(_arxiv_token_bucket.asyncio, "sleep", fake_sleep)
    async with _arxiv_token_bucket.acquire():
        pass
    # Initial _last_request_time=0; monotonic() is huge; wait is hugely negative,
    # so no sleep should fire.
    assert slept == []


@pytest.mark.asyncio
async def test_back_to_back_calls_sleep_for_min_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second call should sleep ~3 seconds (the _MIN_INTERVAL)."""
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(_arxiv_token_bucket.asyncio, "sleep", fake_sleep)
    async with _arxiv_token_bucket.acquire():
        pass
    async with _arxiv_token_bucket.acquire():
        pass

    # Exactly one sleep call, with a value close to 3.0 seconds.
    assert len(slept) == 1
    assert 2.0 <= slept[0] <= 3.5


@pytest.mark.asyncio
async def test_acquire_is_serialized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two concurrent tasks must not run their critical sections in parallel."""

    async def fake_sleep(_seconds: float) -> None:
        # Stripping the sleep so the test runs fast; the lock is what
        # we're verifying, not the wait.
        return None

    monkeypatch.setattr(_arxiv_token_bucket.asyncio, "sleep", fake_sleep)

    in_flight = 0
    max_seen = 0

    async def worker() -> None:
        nonlocal in_flight, max_seen
        async with _arxiv_token_bucket.acquire():
            in_flight += 1
            max_seen = max(max_seen, in_flight)
            await asyncio.sleep(0)  # yield to other tasks
            in_flight -= 1

    await asyncio.gather(worker(), worker(), worker())
    assert max_seen == 1, "token bucket failed to serialize concurrent acquirers"
