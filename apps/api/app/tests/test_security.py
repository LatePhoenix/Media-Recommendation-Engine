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
