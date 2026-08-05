from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}


class UnsafeUrlError(ValueError):
    """Raised when a user-supplied URL is not safe to fetch server-side (SSRF guard)."""


def _normalize(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> (
    ipaddress.IPv4Address | ipaddress.IPv6Address
):
    # ::ffff:127.0.0.1 style mapped addresses would otherwise evade the v4 checks.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    ip = _normalize(ip)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_public_url(url: str) -> None:
    """Reject non-http(s) URLs and any host that resolves to a non-public address.

    Blocks SSRF against loopback, private RFC1918, link-local (incl. cloud metadata
    169.254.169.254), reserved, multicast and unspecified ranges. Called both when a
    user registers an import source and immediately before each outbound sync so a
    later DNS change cannot smuggle in an internal address.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("URL scheme must be http or https")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL must include a host")

    try:
        infos = socket.getaddrinfo(host, parsed.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve host: {host}") from exc
    if not infos:
        raise UnsafeUrlError(f"Could not resolve host: {host}")

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_blocked(ip):
            raise UnsafeUrlError("URL resolves to a non-public address")
