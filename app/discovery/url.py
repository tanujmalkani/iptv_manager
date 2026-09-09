from __future__ import annotations

from urllib.parse import SplitResult, urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    """Normalize URL syntax without changing query/authentication data."""
    value = url.strip()
    parsed = urlsplit(value)

    if parsed.scheme.lower() not in {"http", "https"}:
        return value

    hostname = parsed.hostname
    if hostname is None:
        return value

    host = hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    userinfo = ""
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        userinfo += "@"

    port = parsed.port
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    netloc = f"{userinfo}{host}" if port is None or default_port else f"{userinfo}{host}:{port}"

    normalized = SplitResult(
        scheme=parsed.scheme.lower(),
        netloc=netloc,
        path=parsed.path,
        query=parsed.query,
        fragment="",
    )
    return urlunsplit(normalized)


def hostname_from_url(url: str) -> str | None:
    """Return a lower-case hostname, or None for an invalid/non-URL value."""
    try:
        return urlsplit(url).hostname.lower() if urlsplit(url).hostname else None
    except ValueError:
        return None
