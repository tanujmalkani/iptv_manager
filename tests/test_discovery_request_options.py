from app.db.models.enums import StreamKind
from app.discovery.service import StreamDiscovery
from app.discovery.url import http_headers_from_options
import httpx


class FakeResponse:
    def __init__(self, url: str, content: bytes, content_type: str = "application/vnd.apple.mpegurl") -> None:
        self.url = httpx.URL(url)
        self.status_code = 200
        self.headers = {"content-type": content_type}
        self._content = content

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    def iter_bytes(self):
        yield self._content


class HeaderAwareFakeClient:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def stream(
        self,
        method: str,
        url: str,
        *,
        follow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        assert method == "GET"
        assert follow_redirects is True
        self.calls.append((url, dict(headers or {})))
        return self.responses[url]

    def close(self) -> None:
        return None


def test_master_request_headers_propagate_to_children() -> None:
    root = "https://example.test/master.m3u8"
    child = "https://example.test/video/720/index.m3u8"
    client = HeaderAwareFakeClient(
        {
            root: FakeResponse(
                root,
                b"#EXTM3U\n"
                b"#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720\n"
                b"video/720/index.m3u8\n",
            ),
            child: FakeResponse(
                child,
                b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\nsegment.ts\n",
            ),
        }
    )

    reference = root + "|Referer=https://www.zeebiz.com/&User-Agent=Kodi"
    with StreamDiscovery(client=client) as discovery:
        results = discovery.discover(reference)

    assert [result.kind for result in results] == [
        StreamKind.MASTER_PLAYLIST,
        StreamKind.MEDIA_PLAYLIST,
    ]
    assert client.calls == [
        (root, http_headers_from_options({"Referer": "https://www.zeebiz.com/", "User-Agent": "Kodi"})),
        (child, http_headers_from_options({"Referer": "https://www.zeebiz.com/", "User-Agent": "Kodi"})),
    ]
    assert results[0].final_url.endswith("|Referer=https://www.zeebiz.com/&User-Agent=Kodi")
    assert results[1].final_url.endswith("|Referer=https://www.zeebiz.com/&User-Agent=Kodi")
