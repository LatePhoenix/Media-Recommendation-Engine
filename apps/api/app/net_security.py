from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}


class UnsafeUrlError(ValueError):
    """Raised when a user-supplied URL is not safe to fetch server-side (SSRF guard)."""


@dataclass(frozen=True)
class ResolvedUrl:
    """URL that passed SSRF checks, with a pinned connect IP for DNS-rebinding defense."""

    url: str
    hostname: str
    pinned_ip: str
    port: int | None
    scheme: str


def _normalize(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> (
    ipaddress.IPv4Address | ipaddress.IPv6Address
):
    # ::ffff:127.0.0.1 style mapped addresses would otherwise evade the v4 checks.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _is_always_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Addresses that must never be fetched, even for local-first import sources."""
    ip = _normalize(ip)
    return (
        ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _is_non_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Private/loopback plus always-blocked ranges (strict public-URL policy)."""
    ip = _normalize(ip)
    return _is_always_blocked(ip) or ip.is_private or ip.is_loopback


def _resolve_ips(host: str, port: int | None) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve host: {host}") from exc
    if not infos:
        raise UnsafeUrlError(f"Could not resolve host: {host}")
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def _parse_http_url(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("URL scheme must be http or https")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL must include a host")
    return parsed.scheme, host, parsed.port


def validate_public_url(url: str) -> None:
    """Reject non-http(s) URLs and any host that resolves to a non-public address.

    Blocks SSRF against loopback, private RFC1918, link-local (incl. cloud metadata
    169.254.169.254), reserved, multicast and unspecified ranges.
    """
    scheme, host, port = _parse_http_url(url)
    del scheme
    for ip in _resolve_ips(host, port):
        if _is_non_public(ip):
            raise UnsafeUrlError("URL resolves to a non-public address")


def validate_import_url(url: str, *, allow_private: bool = True) -> ResolvedUrl:
    """Validate an import-source base_url for outbound connector fetches.

    When ``allow_private`` is True (local-first default), RFC1918 and loopback are
    permitted so LAN Plex/Jellyfin/etc. work. Link-local / metadata / reserved /
    multicast / unspecified remain blocked. Returns a pinned IP for connect-time use.
    """
    scheme, host, port = _parse_http_url(url)
    ips = _resolve_ips(host, port)
    for ip in ips:
        if allow_private:
            if _is_always_blocked(ip):
                raise UnsafeUrlError("URL resolves to a blocked address")
        elif _is_non_public(ip):
            raise UnsafeUrlError("URL resolves to a non-public address")

    pinned = _normalize(ips[0])
    return ResolvedUrl(
        url=url,
        hostname=host,
        pinned_ip=str(pinned),
        port=port,
        scheme=scheme,
    )
