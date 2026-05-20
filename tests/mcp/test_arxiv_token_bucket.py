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
    # Capture the real sleep before monkeypatching so the worker still has a
    # genuine yield point. Without this, every ``await asyncio.sleep(0)``
    # inside ``worker`` hits ``fake_sleep`` (a coroutine that never yields),
    # and the event loop may run the workers serially by accident — making
    # ``max_seen == 1`` pass without actually exercising the bucket's lock.
    real_sleep = asyncio.sleep

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(_arxiv_token_bucket.asyncio, "sleep", fake_sleep)

    in_flight = 0
    max_seen = 0

    async def worker() -> None:
        nonlocal in_flight, max_seen
        async with _arxiv_token_bucket.acquire():
            in_flight += 1
            max_seen = max(max_seen, in_flight)
            await real_sleep(0)
            in_flight -= 1

    await asyncio.gather(worker(), worker(), worker())
    assert max_seen == 1, "token bucket failed to serialize concurrent acquirers"
