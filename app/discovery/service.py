from __future__ import annotations

from collections.abc import Iterator

import httpx

from app.db.models.enums import StreamKind
from app.discovery.classifier import classify_response
from app.discovery.hls import parse_master_playlist
from app.discovery.models import DiscoveryResult
from app.discovery.url import normalize_url


class StreamDiscovery:
    """Sequentially discover playable streams and HLS variants from a root URL."""

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 10 * 1024 * 1024,
        max_depth: int = 5,
        max_streams: int = 100,
        client: httpx.Client | None = None,
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
        """Discover the root and all recursively referenced HLS variants."""
        if self._client is None:
            with self:
                return self.discover(root_url)

        results: list[DiscoveryResult] = []
        visited: set[str] = set()
        pending: list[tuple[str, str | None, int]] = [(normalize_url(root_url), None, 0)]

        while pending and len(results) < self.max_streams:
            url, parent_url, depth = pending.pop(0)
            normalized = normalize_url(url)
            if normalized in visited:
                continue
            visited.add(normalized)

            result, children = self._inspect(normalized, parent_url, depth)
            result.children = [normalize_url(child.url) for child in children]
            results.append(result)

            if result.kind == StreamKind.MASTER_PLAYLIST and depth < self.max_depth:
                for child in children:
                    if normalize_url(child.url) not in visited:
                        pending.append((child.url, result.final_url, depth + 1))

        return results

    def _inspect(
        self, url: str, parent_url: str | None, depth: int
    ) -> tuple[DiscoveryResult, list[_Child]]:
        try:
            response = self._client.get(url, follow_redirects=True)
            final_url = normalize_url(str(response.url))
            content_type = response.headers.get("content-type")
            body = self._read_limited(response)
            kind = classify_response(final_url, content_type, body)
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
                error=f"HTTP {response.status_code}",
            )
            return result, []

        children: list[_Child] = []
        if kind == StreamKind.MASTER_PLAYLIST:
            text = body.decode("utf-8-sig", errors="replace")
            children = [_Child(url=item.url) for item in parse_master_playlist(text, final_url)]

        return (
            DiscoveryResult(
                url=url,
                final_url=final_url,
                kind=kind,
                content_type=content_type,
                http_status=response.status_code,
                parent_url=parent_url,
                depth=depth,
            ),
            children,
        )

    def _read_limited(self, response: httpx.Response) -> bytes:
        if response.content and len(response.content) <= self.max_response_bytes:
            return response.content
        if len(response.content) > self.max_response_bytes:
            return response.content[: self.max_response_bytes]
        return b""


class _Child:
    def __init__(self, url: str) -> None:
        self.url = url


def iter_playable_results(results: list[DiscoveryResult]) -> Iterator[DiscoveryResult]:
    """Yield discovered media candidates while excluding HLS master manifests."""
    for result in results:
        if result.kind in {StreamKind.MEDIA_PLAYLIST, StreamKind.MEDIA_STREAM, StreamKind.UNKNOWN}:
            yield result
