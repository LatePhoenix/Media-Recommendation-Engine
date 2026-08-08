import logging
import threading
import time

from fastapi import HTTPException, Request, status

# NOTE: no `from __future__ import annotations` here. This module's IPRateLimiter is
# used as a class-instance FastAPI dependency; with stringized annotations FastAPI
# cannot resolve the `Request` type on `__call__` (an instance has no __globals__),
# and mis-detects `request` as a query parameter → 422 on every rate-limited route.

from app.config import get_settings

logger = logging.getLogger(__name__)


class _InMemoryBackend:
    """Process-local fixed-window counter. Used for dev/tests and as a Redis fallback.

    Note: state is per-process, so across multiple workers the effective limit is
    (limit * worker_count). Use Redis in multi-worker deployments for a shared limit.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, window: int) -> tuple[int, int]:
        now = time.monotonic()
        with self._lock:
            count, reset_at = self._buckets.get(key, (0, now + window))
            if now >= reset_at:
                count, reset_at = 0, now + window
            count += 1
            self._buckets[key] = (count, reset_at)
            return count, max(1, int(reset_at - now))


class _RedisBackend:
    def __init__(self, conn) -> None:
        self._conn = conn

    def hit(self, key: str, window: int) -> tuple[int, int]:
        pipe = self._conn.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()
        if count == 1 or ttl is None or ttl < 0:
            self._conn.expire(key, window)
            ttl = window
        return int(count), int(ttl)


_backend = None
_backend_lock = threading.Lock()


def _get_backend():
    global _backend
    if _backend is not None:
        return _backend
    with _backend_lock:
        if _backend is not None:
            return _backend
        try:
            from redis import Redis

            conn = Redis.from_url(
                get_settings().redis_url,
                socket_connect_timeout=0.25,
                socket_timeout=0.25,
            )
            conn.ping()
            _backend = _RedisBackend(conn)
            logger.info("Rate limiter using Redis backend")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Rate limiter: Redis unavailable (%s); using in-memory backend", exc)
            _backend = _InMemoryBackend()
        return _backend


def reset_backend_for_tests() -> None:
    global _backend
    _backend = None


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(key: str, times: int, window_seconds: int) -> None:
    """Raise HTTP 429 if `key` has been hit more than `times` within the window."""
    try:
        count, ttl = _get_backend().hit(key, window_seconds)
    except Exception as exc:  # noqa: BLE001 — never let limiter internals break auth
        logger.warning("Rate limiter error (%s); allowing request", exc)
        return
    if count > times:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again later.",
            headers={"Retry-After": str(ttl)},
        )


class IPRateLimiter:
    """FastAPI dependency: fixed-window per-client-IP limit for a named scope."""

    def __init__(self, scope: str, times: int, window_seconds: int) -> None:
        self.scope = scope
        self.times = times
        self.window_seconds = window_seconds

    async def __call__(self, request: Request) -> None:
        enforce_rate_limit(
            f"rl:{self.scope}:ip:{client_ip(request)}", self.times, self.window_seconds
        )
