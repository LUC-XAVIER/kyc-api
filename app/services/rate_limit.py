"""In-process sliding-window rate limiter.

A dependency-free throttle for endpoints that have no per-tenant quota to
lean on — notably the stateless ``/partner/verify`` route, whose synchronous
CPU-heavy pipeline must not be hammered by a single key.

Scope note: state lives in this process's memory, so with multiple worker
processes the effective limit is *per worker*. That is deliberate — it needs
no shared store (Redis) and still bounds the load one process will accept.
Tighten ``partner_rate_limit_per_minute`` if you run many workers.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock


class SlidingWindowRateLimiter:
    """Allow at most ``max_events`` per ``window_seconds`` for each key."""

    def __init__(self, max_events: int, window_seconds: float) -> None:
        """Configure the limit and the rolling window it applies over."""
        self._max_events = max_events
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        """Record a hit for ``key`` and report whether it is within limit.

        Thread-safe: FastAPI runs sync endpoints in a worker threadpool, so
        concurrent calls for the same key can race here. Drops timestamps
        that have aged out of the window before counting.
        """
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self._max_events:
                return False
            hits.append(now)
            return True
