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


def test_recursive_master_discovery() -> None:
    responses = {
        "https://example.test/master.m3u8": httpx.Response(
            200,
            headers={"content-type": "application/vnd.apple.mpegurl"},
            content=(
                b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100000,RESOLUTION=640x360\n"
                b"variant.m3u8\n"
            ),
            request=httpx.Request("GET", "https://example.test/master.m3u8"),
        ),
        "https://example.test/variant.m3u8": httpx.Response(
            200,
            headers={"content-type": "application/vnd.apple.mpegurl"},
            content=b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\nsegment.ts\n",
            request=httpx.Request("GET", "https://example.test/variant.m3u8"),
        ),
    }

    class FakeClient:
        def get(self, url: str, follow_redirects: bool = True) -> httpx.Response:
            return responses[url]

    with StreamDiscovery(client=FakeClient()) as discovery:  # type: ignore[arg-type]
        results = discovery.discover("https://example.test/master.m3u8")

    assert [result.kind for result in results] == [
        StreamKind.MASTER_PLAYLIST,
        StreamKind.MEDIA_PLAYLIST,
    ]
    assert results[1].parent_url == "https://example.test/master.m3u8"
