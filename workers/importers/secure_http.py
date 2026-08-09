"""Pinned-host httpx helpers for import connectors (DNS-rebinding defense)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlparse, urlunparse

import httpx

from app.config import get_settings
from app.net_security import ResolvedUrl, validate_import_url


def _rewrite_to_pinned(url: str, resolved: ResolvedUrl) -> tuple[str, str]:
    """Return (connect_url, Host header value) using the pinned IP."""
    parsed = urlparse(url)
    host = resolved.pinned_ip
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parsed.port or resolved.port
    netloc = f"{host}:{port}" if port else host
    connect = urlunparse(
        (resolved.scheme, netloc, parsed.path or "/", parsed.params, parsed.query, parsed.fragment)
    )
    return connect, resolved.hostname


class _PinnedRedirectTransport(httpx.AsyncHTTPTransport):
    """Transport that connects via pinned IP and re-validates redirect targets."""

    def __init__(self, resolved: ResolvedUrl, **kwargs) -> None:
        super().__init__(**kwargs)
        self._resolved = resolved

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # On a redirect to a different host, re-run SSRF validation and re-pin to the new
        # host's vetted IP — otherwise a 3xx Location could smuggle a request to an
        # internal target. Same-host requests reuse the already-validated pin.
        req_host = request.url.host
        if req_host and req_host != self._resolved.hostname:
            resolved = validate_import_url(
                str(request.url),
                allow_private=get_settings().allow_private_import_urls,
            )
        else:
            resolved = self._resolved
        connect_url, host_header = _rewrite_to_pinned(str(request.url), resolved)
        headers = request.headers.copy()
        headers["Host"] = host_header
        # The connect URL's host is the pinned IP (so the socket connects to the vetted
        # address, defeating DNS rebinding), but TLS SNI and certificate verification must
        # still use the real hostname — otherwise every https:// source fails cert
        # validation against the bare IP. The sni_hostname extension overrides the TLS
        # server_hostname without changing the connect address.
        extensions = {**request.extensions, "sni_hostname": resolved.hostname}
        pinned_req = httpx.Request(
            request.method,
            connect_url,
            headers=headers,
            content=request.content,
            extensions=extensions,
        )
        return await super().handle_async_request(pinned_req)


@asynccontextmanager
async def pinned_async_client(
    base_url: str,
    *,
    timeout: float = 30.0,
    follow_redirects: bool = False,
) -> AsyncIterator[httpx.AsyncClient]:
    """AsyncClient that connects to the SSRF-validated pinned IP for ``base_url``."""
    settings = get_settings()
    resolved = validate_import_url(
        base_url,
        allow_private=settings.allow_private_import_urls,
    )
    transport = _PinnedRedirectTransport(resolved)
    async with httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=follow_redirects,
    ) as client:
        yield client
