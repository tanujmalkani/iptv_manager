from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

_SUPPORTED_HEADERS = {
    "referer": "Referer",
    "referrer": "Referer",
    "user-agent": "User-Agent",
    "cookie": "Cookie",
    "origin": "Origin",
    "authorization": "Authorization",
    "accept": "Accept",
    "icy-metadata": "Icy-MetaData",
}
_OPTION_KEY_RE = re.compile(
    r"(?:^|[&|])(" + "|".join(re.escape(key) for key in _SUPPORTED_HEADERS) + r")=",
    re.IGNORECASE,
)


def split_stream_reference(reference: str) -> tuple[str, dict[str, str]]:
    """Split a Kodi-style URL|option=value reference into URL and options."""
    value = reference.strip()
    match = re.search(r"(?:\||%7c)", value, re.IGNORECASE)
    if match is None:
        return value, {}

    base_url = value[: match.start()]
    option_text = value[match.end() :]
    matches = list(_OPTION_KEY_RE.finditer(option_text))
    options: dict[str, str] = {}
    for index, option_match in enumerate(matches):
        key = option_match.group(1)
        value_start = option_match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(option_text)
        option_value = unquote(option_text[value_start:value_end].strip("&|").strip())
        options[key] = option_value
    return base_url, options


def http_headers_from_options(options: Mapping[str, str]) -> dict[str, str]:
    """Map supported Kodi stream options to HTTP request headers."""
    return {
        header_name: value
        for key, value in options.items()
        if (header_name := _SUPPORTED_HEADERS.get(key.casefold())) is not None and value
    }


def format_stream_reference(url: str, options: Mapping[str, str]) -> str:
    """Render a URL and HTTP options in Kodi's URL|option=value form."""
    if not options:
        return url
    parts = [f"{key}={value}" for key, value in options.items() if value]
    return f"{url}|{'&'.join(parts)}" if parts else url


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
