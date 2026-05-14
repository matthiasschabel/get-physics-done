"""Retry gating for arxiv tool calls.

The naive "always retry on 429/timeout with 60s backoff" pattern is
empirically a bad fit for arxiv: an agent earlier proved that 75% of
production timeouts cluster in agentic-loop bursts where retrying
inside the burst window has only a 13-19% rescue rate (BQ trace
replay). The bad case is doubly costly — 60s of dead time AND the
same error.

The fix is to retry only on *isolated* failures: a failure that has no
prior failure within the last ``_BURST_WINDOW`` seconds is likely a
transient blip, and a 60s backoff has a reasonable chance of clearing
it. A failure inside a burst is a sustained-overload signal and
shouldn't be retried — the burst has to settle first.

This module exposes a single predicate, ``is_likely_transient``, plus a
``FailureLog`` deque to track recent failure timestamps per bridge
instance.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque

# How long after the most recent failure to consider the next failure
# part of the same burst. 30s matches the median inter-failure gap in
# the bursty cohort per BQ analysis.
_BURST_WINDOW: float = 30.0

# Cap the failure-log size so a long-lived bridge process doesn't grow
# the deque unbounded.
_MAX_LOG: int = 32


def make_failure_log() -> Deque[float]:
    """Create a new per-bridge-instance failure timestamp log."""
    return deque(maxlen=_MAX_LOG)


def record_failure(log: Deque[float]) -> None:
    """Stamp `time.monotonic()` into the log."""
    log.append(time.monotonic())


def is_likely_transient(log: Deque[float]) -> bool:
    """Return True iff the *previous* failure (if any) is older than
    ``_BURST_WINDOW`` seconds.

    The caller invokes this AFTER its first failed attempt but BEFORE
    deciding whether to retry. ``log`` should NOT yet include the current
    failure — the implementation checks the existing most-recent entry
    as the comparison point.

    Examples (with ``_BURST_WINDOW = 30``):
      - log = [] → True (no prior failure; this is a one-off)
      - log = [now - 50] → True (prior failure was outside the burst)
      - log = [now - 10] → False (prior failure was 10s ago — still in burst)
    """
    if not log:
        return True
    return (time.monotonic() - log[-1]) > _BURST_WINDOW
