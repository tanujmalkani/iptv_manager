from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager
from typing import Protocol

import httpx

from app.db.models.enums import StreamKind
from app.discovery.classifier import classify_response
from app.discovery.hls import parse_master_playlist
from app.discovery.models import DiscoveryResult, VariantMetadata
from app.discovery.url import (
    format_stream_reference,
    http_headers_from_options,
    normalize_url,
    split_stream_reference,
)


class _ResponseContext(AbstractContextManager[httpx.Response], Protocol):
    pass


class _Client(Protocol):
    def stream(
        self,
        method: str,
        url: str,
        *,
        follow_redirects: bool = True,
        headers: Mapping[str, str] | None = None,
    ) -> _ResponseContext: ...

    def close(self) -> None: ...


class StreamDiscovery:
    """Sequentially discover playable streams and HLS variants from a root URL."""

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 10 * 1024 * 1024,
        max_depth: int = 5,
        max_streams: int = 100,
        client: _Client | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_depth = max_depth
        self.max_streams = max_streams
        self._client = client
        self._owns_client = client is None

    def __enter__(self) -> StreamDiscovery:
        if self._client is None:
            self._client = httpx.Client(
                follow_redirects=True,
                timeout=self.timeout_seconds,
                headers={"User-Agent": "IPTV-Manager/0.1"},
            )
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def discover(self, root_url: str) -> list[DiscoveryResult]:
        """Discover the root and recursively referenced HLS variants with inherited headers."""
        if self._client is None:
            with self:
                return self.discover(root_url)

        root_base_url, request_options = split_stream_reference(root_url)
        headers = http_headers_from_options(request_options)
        root_reference = format_stream_reference(normalize_url(root_base_url), request_options)
        results: list[DiscoveryResult] = []
        visited: set[str] = set()
        pending: list[tuple[str, str | None, int, VariantMetadata | None]] = [
            (root_reference, None, 0, None)
        ]

        while pending and len(results) < self.max_streams:
            url, parent_url, depth, variant_metadata = pending.pop(0)
            normalized = normalize_url(url)
            if normalized in visited:
                continue
            visited.add(normalized)

            result, children = self._inspect(url, parent_url, depth, variant_metadata, headers)
            result.children = [
                format_stream_reference(child.url, request_options) for child in children
            ]
            results.append(result)

            if result.kind == StreamKind.MASTER_PLAYLIST and depth < self.max_depth:
                for child in children:
                    child_reference = format_stream_reference(child.url, request_options)
                    if normalize_url(child_reference) not in visited:
                        pending.append(
                            (
                                child_reference,
                                result.final_url,
                                depth + 1,
                                child.variant_metadata,
                            )
                        )

        return results

    def _inspect(
        self,
        url: str,
        parent_url: str | None,
        depth: int,
        variant_metadata: VariantMetadata | None,
        headers: Mapping[str, str],
    ) -> tuple[DiscoveryResult, list[_Child]]:
        base_url, _ = split_stream_reference(url)
        try:
            try:
                response_context = self._client.stream(
                    "GET", base_url, follow_redirects=True, headers=headers
                )
            except TypeError:
                response_context = self._client.stream(
                    "GET", base_url, follow_redirects=True
                )
            with response_context as response:
                final_base_url = normalize_url(str(response.url))
                final_url = format_stream_reference(
                    final_base_url,
                    self._options_from_headers(headers),
                )
                content_type = response.headers.get("content-type")
                kind = classify_response(final_base_url, content_type, b"")

                if kind == StreamKind.MEDIA_STREAM:
                    return (
                        DiscoveryResult(
                            url=url,
                            final_url=final_url,
                            kind=kind,
                            content_type=content_type,
                            http_status=response.status_code,
                            parent_url=parent_url,
                            depth=depth,
                            variant_metadata=variant_metadata,
                            error=(
                                f"HTTP {response.status_code}"
                                if response.status_code >= 400
                                else None
                            ),
                        ),
                        [],
                    )

                body = self._read_limited(response)
                kind = classify_response(final_base_url, content_type, body)
        except httpx.TimeoutException as exc:
            return (
                DiscoveryResult(
                    url=url,
                    final_url=url,
                    kind=StreamKind.UNKNOWN,
                    content_type=None,
                    http_status=None,
                    parent_url=parent_url,
                    depth=depth,
                    variant_metadata=variant_metadata,
                    error=f"timeout: {exc}",
                ),
                [],
            )
        except httpx.HTTPError as exc:
            return (
                DiscoveryResult(
                    url=url,
                    final_url=url,
                    kind=StreamKind.UNKNOWN,
                    content_type=None,
                    http_status=None,
                    parent_url=parent_url,
                    depth=depth,
                    variant_metadata=variant_metadata,
                    error=str(exc),
                ),
                [],
            )
        except ValueError as exc:
            return (
                DiscoveryResult(
                    url=url,
                    final_url=url,
                    kind=StreamKind.UNKNOWN,
                    content_type=None,
                    http_status=None,
                    parent_url=parent_url,
                    depth=depth,
                    variant_metadata=variant_metadata,
                    error=str(exc),
                ),
                [],
            )

        if response.status_code >= 400:
            result = DiscoveryResult(
                url=url,
                final_url=final_url,
                kind=StreamKind.UNKNOWN,
                content_type=content_type,
                http_status=response.status_code,
                parent_url=parent_url,
                depth=depth,
                variant_metadata=variant_metadata,
                error=f"HTTP {response.status_code}",
            )
            return result, []

        children: list[_Child] = []
        if kind == StreamKind.MASTER_PLAYLIST:
            text = body.decode("utf-8-sig", errors="replace")
            children = [
                _Child(url=item.url, variant_metadata=item.metadata)
                for item in parse_master_playlist(text, final_base_url)
            ]

        return (
            DiscoveryResult(
                url=url,
                final_url=final_url,
                kind=kind,
                content_type=content_type,
                http_status=response.status_code,
                parent_url=parent_url,
                depth=depth,
                variant_metadata=variant_metadata,
            ),
            children,
        )

    @staticmethod
    def _options_from_headers(headers: Mapping[str, str]) -> dict[str, str]:
        return {key: value for key, value in headers.items() if value}

    def _read_limited(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            if total + len(chunk) > self.max_response_bytes:
                raise ValueError(
                    f"response exceeds maximum size of {self.max_response_bytes} bytes"
                )
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)


class _Child:
    def __init__(self, url: str, variant_metadata: VariantMetadata | None = None) -> None:
        self.url = url
        self.variant_metadata = variant_metadata


def iter_playable_results(results: list[DiscoveryResult]) -> Iterator[DiscoveryResult]:
    """Yield discovered media candidates while excluding HLS master manifests."""
    for result in results:
        if result.kind in {StreamKind.MEDIA_PLAYLIST, StreamKind.MEDIA_STREAM, StreamKind.UNKNOWN}:
            yield result
