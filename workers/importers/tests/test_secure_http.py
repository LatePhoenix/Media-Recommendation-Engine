"""Tests for the SSRF-pinned HTTP transport and connector wiring (H-1)."""

from __future__ import annotations

import asyncio
import inspect
import unittest

import httpx

from workers.importers import tmdb, trakt
from workers.importers.secure_http import (
    _PinnedRedirectTransport,
    _rewrite_to_pinned,
)
from app.net_security import ResolvedUrl


class RewriteToPinnedTests(unittest.TestCase):
    def test_rewrites_host_to_pinned_ip_and_keeps_hostname(self) -> None:
        resolved = ResolvedUrl(
            url="https://api.themoviedb.org/3/movie/popular",
            hostname="api.themoviedb.org",
            pinned_ip="93.184.216.34",
            port=None,
            scheme="https",
        )
        connect, host_header = _rewrite_to_pinned(
            "https://api.themoviedb.org/3/movie/popular", resolved
        )
        self.assertIn("93.184.216.34", connect)
        self.assertNotIn("themoviedb.org", connect)
        self.assertEqual(host_header, "api.themoviedb.org")


class PinnedTransportSniTests(unittest.TestCase):
    def test_pins_ip_but_preserves_sni_hostname_for_tls(self) -> None:
        resolved = ResolvedUrl(
            url="https://api.trakt.tv/sync/watched/movies",
            hostname="api.trakt.tv",
            pinned_ip="203.0.113.7",
            port=None,
            scheme="https",
        )
        transport = _PinnedRedirectTransport(resolved)

        captured: dict[str, httpx.Request] = {}

        async def fake_super(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200)

        # Intercept the actual network send so we can inspect the rewritten request.
        transport_super = httpx.AsyncHTTPTransport.handle_async_request
        httpx.AsyncHTTPTransport.handle_async_request = (  # type: ignore[method-assign]
            lambda self, request: fake_super(request)
        )
        try:
            req = httpx.Request("GET", "https://api.trakt.tv/sync/watched/movies")
            asyncio.run(transport.handle_async_request(req))
        finally:
            httpx.AsyncHTTPTransport.handle_async_request = transport_super  # type: ignore[method-assign]

        sent = captured["req"]
        # Socket connects to the pinned IP...
        self.assertEqual(sent.url.host, "203.0.113.7")
        # ...but TLS SNI / cert verification uses the real hostname.
        self.assertEqual(sent.extensions.get("sni_hostname"), "api.trakt.tv")
        self.assertEqual(sent.headers.get("Host"), "api.trakt.tv")


class ConnectorWiringTests(unittest.TestCase):
    """Guard against a connector silently dropping the SSRF-pinned client again."""

    def test_tmdb_uses_pinned_client(self) -> None:
        src = inspect.getsource(tmdb)
        self.assertIn("pinned_async_client(self.base_url", src)
        self.assertNotIn("httpx.AsyncClient(", src)

    def test_trakt_uses_pinned_client(self) -> None:
        src = inspect.getsource(trakt)
        self.assertIn("pinned_async_client(self.base_url", src)
        self.assertNotIn("httpx.AsyncClient(", src)


if __name__ == "__main__":
    unittest.main()
