"""Request pacing for the football-data.org free tier (10 requests/minute; we keep at least 6.5 s
between request starts, architecture section 8.5). Clock and sleep are injectable for tests."""

from __future__ import annotations

import time
from collections.abc import Callable


class Pacer:
    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must not be negative")
        self._interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> float:
        """Block until a request may start; returns the seconds slept."""
        slept = 0.0
        now = self._clock()
        if self._last is not None:
            remaining = self._interval - (now - self._last)
            if remaining > 0:
                self._sleep(remaining)
                slept = remaining
                now = self._clock()
        self._last = now
        return slept
