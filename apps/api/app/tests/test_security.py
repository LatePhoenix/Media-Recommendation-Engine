"""Regression tests for the pre-release security hardening pass.

These cover the DB-free logic (config guards, SSRF URL validation, error
sanitization, rate limiting, and JWT claims/revocation) so the protections can't
silently regress. They set the required secrets via the environment before the app
package is imported.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault(
    "API_SECRET_KEY", "test-secret-key-that-is-definitely-long-enough-1234567890"
)
os.environ.setdefault("CREDENTIALS_FERNET_KEY", "vyErqHdYcVkJLcxYI04YW5JVAuRBAu3ad58GfOzMf3k=")


class ConfigGuardTests(unittest.TestCase):
    def test_rejects_insecure_and_short_secret_keys(self) -> None:
        from app.config import INSECURE_SECRET_KEY_DEFAULT, Settings

        for bad in (INSECURE_SECRET_KEY_DEFAULT, "short", ""):
            with self.assertRaises(Exception):
                Settings(_env_file=None, api_secret_key=bad)

    def test_accepts_strong_secret_key(self) -> None:
        from app.config import Settings

        s = Settings(_env_file=None, api_secret_key="x" * 40)
        self.assertEqual(len(s.api_secret_key), 40)


class SsrfGuardTests(unittest.TestCase):
    def test_blocks_internal_and_bad_schemes(self) -> None:
        from app.net_security import UnsafeUrlError, validate_public_url

        blocked = [
            "http://127.0.0.1:32400",
            "http://localhost/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5",
            "http://192.168.1.10:8096",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "file:///etc/passwd",
            "ftp://example.com",
        ]
        for url in blocked:
            with self.assertRaises(UnsafeUrlError, msg=url):
                validate_public_url(url)

    def test_allows_public_hosts(self) -> None:
        from app.net_security import validate_public_url

        for url in ("https://api.trakt.tv", "http://example.com", "https://plex.tv:443/x"):
            validate_public_url(url)  # must not raise

    def test_import_url_allows_lan_when_private_enabled(self) -> None:
        from app.net_security import UnsafeUrlError, validate_import_url

        for url in (
            "http://192.168.1.10:8096",
            "http://127.0.0.1:32400",
            "http://10.0.0.5",
        ):
            resolved = validate_import_url(url, allow_private=True)
            self.assertTrue(resolved.pinned_ip)

        for url in (
            "http://169.254.169.254/latest/meta-data/",
            "file:///etc/passwd",
            "ftp://example.com",
        ):
            with self.assertRaises(UnsafeUrlError, msg=url):
                validate_import_url(url, allow_private=True)

    def test_import_url_strict_when_private_disabled(self) -> None:
        from app.net_security import UnsafeUrlError, validate_import_url

        with self.assertRaises(UnsafeUrlError):
            validate_import_url("http://192.168.1.10:8096", allow_private=False)


class ErrorSanitizationTests(unittest.TestCase):
    def test_internal_details_are_not_leaked(self) -> None:
        import httpx

        from workers.importers.runner import _safe_error

        msg = _safe_error(RuntimeError("psycopg: password=hunter2 host=db.internal"))
        self.assertNotIn("hunter2", msg)
        self.assertNotIn("db.internal", msg)
        req = httpx.Request("GET", "http://x")
        unauth = _safe_error(
            httpx.HTTPStatusError("x", request=req, response=httpx.Response(401, request=req))
        )
        self.assertIn("Authentication", unauth)


class RateLimitTests(unittest.TestCase):
    def test_blocks_after_limit(self) -> None:
        from fastapi import HTTPException

        import app.rate_limit as rl

        rl._backend = rl._InMemoryBackend()  # deterministic, no Redis
        allowed = 0
        blocked = False
        for _ in range(8):
            try:
                rl.enforce_rate_limit("rl:test:ip:1.2.3.4", times=5, window_seconds=60)
                allowed += 1
            except HTTPException as exc:
                blocked = True
                self.assertEqual(exc.status_code, 429)
        self.assertEqual(allowed, 5)
        self.assertTrue(blocked)
        # A different key is tracked independently.
        rl.enforce_rate_limit("rl:test:ip:9.9.9.9", times=5, window_seconds=60)

    def test_fail_closed_on_backend_error(self) -> None:
        from fastapi import HTTPException

        import app.rate_limit as rl
        from app.config import get_settings

        class _Boom:
            def hit(self, key: str, window: int):
                raise RuntimeError("redis down")

        rl._backend = _Boom()
        get_settings.cache_clear()
        os.environ["RATE_LIMIT_FAIL_OPEN"] = "false"
        get_settings.cache_clear()
        with self.assertRaises(HTTPException) as ctx:
            rl.enforce_rate_limit("rl:test:fail", times=5, window_seconds=60)
        self.assertEqual(ctx.exception.status_code, 503)
        os.environ["RATE_LIMIT_FAIL_OPEN"] = "true"
        get_settings.cache_clear()
        rl.enforce_rate_limit("rl:test:fail-open", times=5, window_seconds=60)
        os.environ.pop("RATE_LIMIT_FAIL_OPEN", None)
        get_settings.cache_clear()
        rl.reset_backend_for_tests()

    def test_in_memory_backend_prunes_expired_buckets(self) -> None:
        # H-2: expired windows must be reclaimed so attacker-varied keys (per-username /
        # per-IP) can't grow the bucket map without bound (memory-exhaustion DoS).
        import app.rate_limit as rl

        backend = rl._InMemoryBackend()
        backend._PRUNE_THRESHOLD = 5  # keep the test small
        # window=0 → each bucket's reset_at is its creation instant, so it is already
        # expired relative to every later call and becomes prunable.
        for i in range(10):
            backend.hit(f"expired:{i}", window=0)
        # A live key plus the hits above cross the threshold and trigger a prune sweep.
        backend.hit("live", window=60)
        # Without pruning this would be 11; with it, only the live entry (and at most a
        # couple of same-instant stragglers) survive.
        self.assertLess(len(backend._buckets), 10)
        self.assertIn("live", backend._buckets)

    def test_in_memory_backend_keeps_live_buckets(self) -> None:
        # H-2: pruning must not drop windows that are still open.
        import app.rate_limit as rl

        backend = rl._InMemoryBackend()
        backend._PRUNE_THRESHOLD = 5
        for i in range(10):
            backend.hit(f"live:{i}", window=60)  # all still within their window
        n_before = len(backend._buckets)
        backend.hit("trigger", window=60)
        # Nothing was expired, so the only change is the new key.
        self.assertEqual(len(backend._buckets), n_before + 1)

    def test_reprobes_redis_and_recovers_after_cooldown(self) -> None:
        # H-1: a transient Redis outage must not pin the process to the in-memory
        # fallback forever — it re-probes on a cooldown and adopts Redis once it's back.
        from unittest import mock

        import redis as redis_module

        import app.rate_limit as rl

        rl.reset_backend_for_tests()

        class _FakeRedis:
            up = False

            @classmethod
            def from_url(cls, *args, **kwargs):
                return cls()

            def ping(self):
                if not _FakeRedis.up:
                    raise RuntimeError("redis down")
                return True

        clock = {"t": 1000.0}
        try:
            with mock.patch.object(redis_module, "Redis", _FakeRedis), mock.patch.object(
                rl.time, "monotonic", lambda: clock["t"]
            ):
                # Redis down → auto-fallback installed and tracked by identity.
                b1 = rl._get_backend()
                self.assertIsInstance(b1, rl._InMemoryBackend)
                self.assertIs(b1, rl._fallback_backend)

                # Within the cooldown: same instance, no re-probe — even once Redis is back.
                clock["t"] += rl._FALLBACK_RETRY_SECONDS / 2
                _FakeRedis.up = True
                self.assertIs(rl._get_backend(), b1)

                # After the cooldown elapses, the re-probe succeeds and Redis is adopted.
                clock["t"] += rl._FALLBACK_RETRY_SECONDS + 1
                b2 = rl._get_backend()
                self.assertIsInstance(b2, rl._RedisBackend)
                self.assertIsNone(rl._fallback_backend)

                # An established Redis backend is authoritative: even if Redis drops again
                # it is not re-probed or silently downgraded.
                _FakeRedis.up = False
                clock["t"] += 10_000
                self.assertIs(rl._get_backend(), b2)
        finally:
            rl.reset_backend_for_tests()

    def test_fallback_instance_reused_across_reprobe(self) -> None:
        # H-1: while Redis stays down, the *same* in-memory instance is reused across
        # re-probes so accumulated counters aren't reset (no fresh brute-force window).
        from unittest import mock

        import redis as redis_module

        import app.rate_limit as rl

        rl.reset_backend_for_tests()

        class _DownRedis:
            @classmethod
            def from_url(cls, *args, **kwargs):
                return cls()

            def ping(self):
                raise RuntimeError("redis down")

        clock = {"t": 5000.0}
        try:
            with mock.patch.object(redis_module, "Redis", _DownRedis), mock.patch.object(
                rl.time, "monotonic", lambda: clock["t"]
            ):
                b1 = rl._get_backend()
                b1.hit("rl:test:ip:1.1.1.1", window=60)
                count, _ = b1.hit("rl:test:ip:1.1.1.1", window=60)
                self.assertEqual(count, 2)

                # Cross the cooldown; Redis is still down so the probe fails again.
                clock["t"] += rl._FALLBACK_RETRY_SECONDS + 1
                b2 = rl._get_backend()
                self.assertIs(b2, b1)  # same instance, not a fresh one
                count, _ = b2.hit("rl:test:ip:1.1.1.1", window=60)
                self.assertEqual(count, 3)  # counter preserved across the re-probe
        finally:
            rl.reset_backend_for_tests()

    def test_user_rate_limiter_blocks_after_limit(self) -> None:
        # M-1: per-user limiter caps expensive feed regeneration independent of client IP.
        import asyncio

        from fastapi import HTTPException

        import app.rate_limit as rl

        rl._backend = rl._InMemoryBackend()

        class _User:
            id = "11111111-1111-1111-1111-111111111111"

        limiter = rl.UserRateLimiter("feedtest", times=3, window_seconds=60)
        allowed, blocked = 0, False
        for _ in range(5):
            try:
                asyncio.run(limiter(user=_User()))  # type: ignore[arg-type]
                allowed += 1
            except HTTPException as exc:
                blocked = True
                self.assertEqual(exc.status_code, 429)
        self.assertEqual(allowed, 3)
        self.assertTrue(blocked)
        # A different user is tracked independently.
        class _Other:
            id = "22222222-2222-2222-2222-222222222222"

        asyncio.run(limiter(user=_Other()))  # type: ignore[arg-type]
        rl.reset_backend_for_tests()


class LoginTimingTests(unittest.TestCase):
    def test_missing_user_still_pays_bcrypt_cost(self) -> None:
        # M-2: a login for a non-existent username must still verify a password, so the
        # response time doesn't reveal whether the account exists (user enumeration).
        from fastapi import HTTPException

        import app.rate_limit as rl
        import app.routers.auth as auth_router

        rl._backend = rl._InMemoryBackend()

        verified_against: list[str] = []
        original = auth_router.verify_password

        def _spy(plain: str, hashed: str) -> bool:
            verified_against.append(hashed)
            return False

        class _NoUserQuery:
            def filter(self, *a, **k):
                return self

            def first(self):
                return None

        class _FakeDB:
            def query(self, *a, **k):
                return _NoUserQuery()

        class _Form:
            username = "ghost-account"
            password = "irrelevant"

        auth_router.verify_password = _spy  # type: ignore[assignment]
        try:
            with self.assertRaises(HTTPException) as ctx:
                auth_router.login(form_data=_Form(), db=_FakeDB())  # type: ignore[arg-type]
            self.assertEqual(ctx.exception.status_code, 401)
            # Exactly one verification, against the dummy hash — matching the user-exists path.
            self.assertEqual(verified_against, [auth_router._DUMMY_PASSWORD_HASH])
        finally:
            auth_router.verify_password = original  # type: ignore[assignment]
            rl.reset_backend_for_tests()


class LowFindingTests(unittest.TestCase):
    def test_escape_like_neutralizes_wildcards(self) -> None:
        # L-1: %, _ and \ in a search term must be matched literally, not as wildcards.
        from app.services.catalog import escape_like

        self.assertEqual(escape_like("a%b_c\\d"), "a\\%b\\_c\\\\d")
        self.assertEqual(escape_like("plain"), "plain")

    def test_user_prefs_rejects_unknown_media_types(self) -> None:
        # L-3: enabled_media_types must be validated so junk can't reach the DB.
        from pydantic import ValidationError

        from app.schemas import UserPrefsUpdate

        UserPrefsUpdate(enabled_media_types=["movie", "tv"])  # valid
        UserPrefsUpdate(enabled_media_types=None)  # unset is allowed
        with self.assertRaises(ValidationError):
            UserPrefsUpdate(enabled_media_types=["movie", "not-a-media-type"])

    def test_fernet_keys_are_cached(self) -> None:
        # L-4: repeated loads reuse the same Fernet objects instead of re-parsing keys.
        from app.security_crypto import _load_keys

        first = _load_keys()
        second = _load_keys()
        self.assertIs(first[0], second[0])
        self.assertIs(first[1], second[1])


class AdminAuthzTests(unittest.TestCase):
    def test_require_admin_rejects_non_admin(self) -> None:
        from fastapi import HTTPException

        from app.auth import require_admin

        class _User:
            is_admin = False

        with self.assertRaises(HTTPException) as ctx:
            require_admin(user=_User())  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.status_code, 403)

    def test_require_admin_accepts_admin(self) -> None:
        from app.auth import require_admin

        class _User:
            is_admin = True

        user = _User()
        self.assertIs(require_admin(user=user), user)  # type: ignore[arg-type]


class JwtTests(unittest.TestCase):
    def test_claims_present_and_revocation_enforced(self) -> None:
        from uuid import uuid4

        from fastapi import HTTPException
        from jose import jwt

        from app.auth import ALGORITHM, create_access_token, get_current_user
        from app.config import get_settings

        uid = str(uuid4())
        token = create_access_token(uid, extra={"username": "bob"}, token_version=3)
        claims = jwt.decode(token, get_settings().api_secret_key, algorithms=[ALGORITHM])
        for claim in ("iat", "jti", "typ", "tv", "exp", "sub"):
            self.assertIn(claim, claims)
        self.assertEqual(claims["typ"], "access")
        self.assertEqual(claims["tv"], 3)

        class _User:
            def __init__(self, tv: int) -> None:
                self.token_version = tv

        class _DB:
            def __init__(self, tv: int) -> None:
                self._u = _User(tv)

            def get(self, _model, _uid):  # noqa: ANN001
                return self._u

        # Matching version is accepted; a bumped version (logout-all) is rejected.
        get_current_user(token=token, db=_DB(3))
        with self.assertRaises(HTTPException):
            get_current_user(token=token, db=_DB(4))


if __name__ == "__main__":
    unittest.main()
