"""Retry gating for arxiv tool calls — only retry isolated failures."""

from __future__ import annotations

import time
from collections import deque

_BURST_WINDOW: float = 30.0
_MAX_LOG: int = 32


def make_failure_log() -> deque[float]:
    return deque(maxlen=_MAX_LOG)


def record_failure(log: deque[float]) -> None:
    log.append(time.monotonic())


def is_likely_transient(log: deque[float]) -> bool:
    if not log:
        return True
    return (time.monotonic() - log[-1]) > _BURST_WINDOW
