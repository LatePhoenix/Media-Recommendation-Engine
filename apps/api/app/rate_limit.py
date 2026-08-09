import logging
import threading
import time

from fastapi import Depends, HTTPException, Request, status

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

    # Prune expired buckets once the map grows past this, so attacker-varied keys
    # (per-username / per-IP) can't grow the dict without bound (memory-exhaustion DoS).
    _PRUNE_THRESHOLD = 10_000

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, window: int) -> tuple[int, int]:
        now = time.monotonic()
        with self._lock:
            if len(self._buckets) > self._PRUNE_THRESHOLD:
                # Drop windows that have already reset; cheap amortized cleanup.
                self._buckets = {k: v for k, v in self._buckets.items() if v[1] > now}
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
# The specific in-memory instance _get_backend() auto-installed when Redis was down.
# Tracked by identity so a directly-assigned _backend (tests, explicit config) is always
# treated as authoritative and never re-probed.
_fallback_backend = None
# monotonic() timestamp of the last Redis probe while on the auto-fallback.
_fallback_since = 0.0
# How long to stay on the in-memory fallback before re-probing Redis. Without this, a
# single Redis blip at startup (WinSW start races are expected — see wait_for_deps) would
# pin the process to per-process/per-worker limits forever, silently weakening
# brute-force protection with no recovery short of a restart.
_FALLBACK_RETRY_SECONDS = 30.0


def _get_backend():
    global _backend, _fallback_backend, _fallback_since
    # Any backend that isn't our auto-fallback (Redis, or one injected directly) is
    # authoritative and reused without a probe.
    b = _backend
    if b is not None and b is not _fallback_backend:
        return b
    with _backend_lock:
        b = _backend
        if b is not None and b is not _fallback_backend:
            return b
        # Currently on the auto-fallback: keep serving it until the retry window elapses.
        if (
            _backend is _fallback_backend
            and _fallback_backend is not None
            and time.monotonic() - _fallback_since < _FALLBACK_RETRY_SECONDS
        ):
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
            _fallback_backend = None
            logger.info("Rate limiter using Redis backend")
        except Exception as exc:  # noqa: BLE001
            if _fallback_backend is None:
                # Log once on transition to the fallback, not on every re-probe. Reuse the
                # same instance across re-probes so accumulated counters aren't reset.
                logger.warning(
                    "Rate limiter: Redis unavailable (%s); using in-memory backend "
                    "(per-process limits; will re-probe every %ss)",
                    exc,
                    int(_FALLBACK_RETRY_SECONDS),
                )
                _fallback_backend = _InMemoryBackend()
            _backend = _fallback_backend
            _fallback_since = time.monotonic()
        return _backend


def reset_backend_for_tests() -> None:
    global _backend, _fallback_backend, _fallback_since
    _backend = None
    _fallback_backend = None
    _fallback_since = 0.0


def active_backend_name() -> str:
    """Read-only report of the current backend for observability (no probe side effect).

    'redis' = shared limits; 'memory' = per-process fallback (brute-force protection is
    weaker across workers); 'uninitialized' = not yet selected (no rate-limited request
    has been served on this process).
    """
    if isinstance(_backend, _RedisBackend):
        return "redis"
    if isinstance(_backend, _InMemoryBackend):
        return "memory"
    return "uninitialized"


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
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rate limiter error (%s)", exc)
        if get_settings().rate_limit_fail_open:
            logger.warning("Rate limiter fail-open; allowing request")
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter unavailable. Please try again shortly.",
        ) from exc
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


# Imported here (not at module top) so this low-level util has no import-time dependency
# on the auth/model layers; the reference is only needed when the dependency is built.
from app.auth import get_current_user  # noqa: E402
from app.models import User  # noqa: E402


class UserRateLimiter:
    """FastAPI dependency: fixed-window per-authenticated-user limit for a named scope.

    Use for expensive authenticated endpoints (e.g. feed generation) where the natural
    subject is the user, not the client IP (which is shared behind NAT / not meaningful
    once authenticated).
    """

    def __init__(self, scope: str, times: int, window_seconds: int) -> None:
        self.scope = scope
        self.times = times
        self.window_seconds = window_seconds

    async def __call__(self, user: User = Depends(get_current_user)) -> None:
        enforce_rate_limit(
            f"rl:{self.scope}:user:{user.id}", self.times, self.window_seconds
        )
