"""Bounded per-process rate limiter. Scale-out needs a shared limiter."""
import asyncio
import time
from collections import OrderedDict, deque


class InMemoryRateLimiter:
    def __init__(self, max_requests, window_seconds, max_users=10000):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_users = max_users
        self._events = OrderedDict()
        self._lock = asyncio.Lock()

    async def allow(self, key):
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            # Entries are ordered by last accepted request.
            while self._events:
                oldest = next(iter(self._events))
                if self._events[oldest][-1] > cutoff:
                    break
                self._events.popitem(last=False)
            events = self._events.get(key)
            if events is None:
                if len(self._events) >= self.max_users:
                    return False
                events = deque()
                self._events[key] = events
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.max_requests:
                return False
            events.append(now)
            self._events.move_to_end(key)
            return True
