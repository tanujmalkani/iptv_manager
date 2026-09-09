import httpx

from app.db.models.enums import StreamKind
from app.discovery.classifier import classify_response
from app.discovery.hls import parse_master_playlist
from app.discovery.service import StreamDiscovery
from app.discovery.url import hostname_from_url, normalize_url


def test_normalize_url_preserves_query_and_removes_default_port() -> None:
    url = "HTTPS://Example.COM:443/live/index.m3u8?token=ABC#fragment"
    assert normalize_url(url) == "https://example.com/live/index.m3u8?token=ABC"
    assert hostname_from_url(url) == "example.com"


def test_classify_master_and_media_playlists() -> None:
    master = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100000\nlow/index.m3u8\n"
    media = b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\nsegment.ts\n"

    assert (
        classify_response("https://example.test/master", "text/plain", master)
        == StreamKind.MASTER_PLAYLIST
    )
    assert (
        classify_response(
            "https://example.test/live", "application/vnd.apple.mpegurl", media
        )
        == StreamKind.MEDIA_PLAYLIST
    )
    assert (
        classify_response(
            "https://example.test/live.ts", "application/octet-stream", b"TS"
        )
        == StreamKind.MEDIA_STREAM
    )


def test_parse_master_variants() -> None:
    text = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720,FRAME-RATE=25.0,CODECS="avc1.4d401f,mp4a.40.2"
video/720/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360
video/360/index.m3u8
"""
    variants = parse_master_playlist(text, "https://example.test/root/master.m3u8")

    assert len(variants) == 2
    assert variants[0].url == "https://example.test/root/video/720/index.m3u8"
    assert variants[0].metadata.bandwidth == 2_000_000
    assert variants[0].metadata.width == 1280
    assert variants[0].metadata.height == 720
    assert variants[0].metadata.frame_rate == 25.0
    assert variants[0].metadata.codecs == "avc1.4d401f,mp4a.40.2"


class FakeStreamResponse:
    def __init__(
        self,
        url: str,
        content: bytes,
        *,
        status_code: int = 200,
        content_type: str = "application/vnd.apple.mpegurl",
        chunks: list[bytes] | None = None,
    ) -> None:
        self.url = httpx.URL(url)
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self._content = content
        self._chunks = chunks

    def __enter__(self) -> FakeStreamResponse:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    def iter_bytes(self):
        if self._chunks is not None:
            yield from self._chunks
        else:
            yield self._content


class FakeClient:
    def __init__(self, responses: dict[str, FakeStreamResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def stream(self, method: str, url: str, *, follow_redirects: bool = True) -> FakeStreamResponse:
        assert method == "GET"
        assert follow_redirects is True
        self.calls.append(url)
        return self.responses[url]

    def close(self) -> None:
        return None


def test_recursive_master_discovery() -> None:
    responses = {
        "https://example.test/master.m3u8": FakeStreamResponse(
            "https://example.test/master.m3u8",
            (
                b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100000,RESOLUTION=640x360\n"
                b"variant.m3u8\n"
            ),
        ),
        "https://example.test/variant.m3u8": FakeStreamResponse(
            "https://example.test/variant.m3u8",
            b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\nsegment.ts\n",
        ),
    }
    client = FakeClient(responses)

    with StreamDiscovery(client=client) as discovery:
        results = discovery.discover("https://example.test/master.m3u8")

    assert [result.kind for result in results] == [
        StreamKind.MASTER_PLAYLIST,
        StreamKind.MEDIA_PLAYLIST,
    ]
    assert results[1].parent_url == "https://example.test/master.m3u8"
    assert results[1].variant_metadata is not None
    assert results[1].variant_metadata.width == 640
    assert client.calls == [
        "https://example.test/master.m3u8",
        "https://example.test/variant.m3u8",
    ]


def test_recursive_discovery_deduplicates_urls() -> None:
    responses = {
        "https://example.test/master.m3u8": FakeStreamResponse(
            "https://example.test/master.m3u8",
            b"#EXTM3U\n"
            b"#EXT-X-STREAM-INF:BANDWIDTH=100000\nvariant.m3u8\n"
            b"#EXT-X-STREAM-INF:BANDWIDTH=200000\nvariant.m3u8\n",
        ),
        "https://example.test/variant.m3u8": FakeStreamResponse(
            "https://example.test/variant.m3u8",
            b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\nsegment.ts\n",
        ),
    }
    client = FakeClient(responses)

    with StreamDiscovery(client=client) as discovery:
        results = discovery.discover("https://example.test/master.m3u8")

    assert len(results) == 2
    assert client.calls.count("https://example.test/variant.m3u8") == 1


def test_discovery_enforces_max_response_bytes() -> None:
    response = FakeStreamResponse(
        "https://example.test/master.m3u8",
        b"abcdef",
        chunks=[b"abc", b"def"],
    )
    client = FakeClient({"https://example.test/master.m3u8": response})

    with StreamDiscovery(client=client, max_response_bytes=5) as discovery:
        results = discovery.discover("https://example.test/master.m3u8")

    assert len(results) == 1
    assert results[0].kind == StreamKind.UNKNOWN
    assert results[0].error == "response exceeds maximum size of 5 bytes"


def test_discovery_stops_recursion_at_max_depth() -> None:
    responses = {
        "https://example.test/root.m3u8": FakeStreamResponse(
            "https://example.test/root.m3u8",
            b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100000\nlevel1.m3u8\n",
        ),
        "https://example.test/level1.m3u8": FakeStreamResponse(
            "https://example.test/level1.m3u8",
            b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100000\nlevel2.m3u8\n",
        ),
        "https://example.test/level2.m3u8": FakeStreamResponse(
            "https://example.test/level2.m3u8",
            b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\nsegment.ts\n",
        ),
    }
    client = FakeClient(responses)

    with StreamDiscovery(client=client, max_depth=1) as discovery:
        results = discovery.discover("https://example.test/root.m3u8")

    assert [result.url for result in results] == [
        "https://example.test/root.m3u8",
        "https://example.test/level1.m3u8",
    ]
    assert client.calls == [
        "https://example.test/root.m3u8",
        "https://example.test/level1.m3u8",
    ]
