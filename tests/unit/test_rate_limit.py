"""Unit tests for the in-process sliding-window rate limiter."""

import app.services.rate_limit as rl_mod
from app.services.rate_limit import SlidingWindowRateLimiter


def test_allows_up_to_limit_then_blocks() -> None:
    """The first ``max_events`` calls pass; the next is refused."""
    limiter = SlidingWindowRateLimiter(2, window_seconds=60.0)
    assert limiter.allow("k")
    assert limiter.allow("k")
    assert not limiter.allow("k")


def test_keys_are_independent() -> None:
    """One key hitting its limit does not affect another."""
    limiter = SlidingWindowRateLimiter(1, window_seconds=60.0)
    assert limiter.allow("a")
    assert limiter.allow("b")
    assert not limiter.allow("a")


def test_window_slides(monkeypatch) -> None:
    """Hits older than the window drop off, freeing capacity again."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(rl_mod.time, "monotonic", lambda: clock["t"])
    limiter = SlidingWindowRateLimiter(1, window_seconds=60.0)

    assert limiter.allow("k")
    assert not limiter.allow("k")

    clock["t"] += 61.0  # the first hit ages out of the window
    assert limiter.allow("k")
