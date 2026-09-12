from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, Channel, ChannelStream, PlaylistEntry, Stream, StreamVariant
from app.db.models.enums import StreamKind
from app.discovery.models import DiscoveryResult, VariantMetadata
from app.importer.service import PlaylistImporter


class FakeDiscovery:
    def discover(self, url: str) -> list[DiscoveryResult]:
        root = "https://example.test/master.m3u8"
        variant = "https://example.test/720/index.m3u8"
        return [
            DiscoveryResult(
                url=root,
                final_url=root,
                kind=StreamKind.MASTER_PLAYLIST,
                content_type="application/vnd.apple.mpegurl",
                http_status=200,
                parent_url=None,
                depth=0,
            ),
            DiscoveryResult(
                url=variant,
                final_url=variant,
                kind=StreamKind.MEDIA_PLAYLIST,
                content_type="application/vnd.apple.mpegurl",
                http_status=200,
                parent_url=root,
                depth=1,
                variant_metadata=VariantMetadata(
                    bandwidth=2_000_000,
                    width=1280,
                    height=720,
                    frame_rate=25.0,
                    codecs="avc1.4d401f",
                ),
            ),
        ]


class CountingDiscovery:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def discover(self, url: str) -> list[DiscoveryResult]:
        self.calls.append(url)
        return [
            DiscoveryResult(
                url=url,
                final_url=url,
                kind=StreamKind.MEDIA_PLAYLIST,
                content_type="application/vnd.apple.mpegurl",
                http_status=200,
                parent_url=None,
                depth=0,
            )
        ]


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_import_persists_channel_streams_options_and_variants() -> None:
    session = make_session()
    playlist = (
        '#EXTM3U\n'
        '#EXTINF:-1 tvg-id="bbc1.uk" tvg-name="BBC One" '
        'tvg-logo="https://logo/bbc1.png" group-title="UK",BBC One\n'
        'https://example.test/master.m3u8\n'
    )

    result = PlaylistImporter(discovery=FakeDiscovery()).import_text(
        session, "Test Playlist", playlist
    )

    assert result.entries == 1
    assert result.channels == 1
    assert result.new_channels == 1
    assert result.discovered_streams == 2
    assert result.identical_version is False

    channel = session.scalar(select(Channel).where(Channel.normalized_name == "bbc one"))
    assert channel is not None
    assert {option.value for option in channel.options} == {
        "BBC One",
        "bbc1.uk",
        "https://logo/bbc1.png",
        "UK",
    }

    entries = session.scalars(select(PlaylistEntry)).all()
    streams = session.scalars(select(Stream)).all()
    channel_streams = session.scalars(select(ChannelStream)).all()
    variants = session.scalars(select(StreamVariant)).all()
    assert len(entries) == 1
    assert len(streams) == 2
    assert len(channel_streams) == 1
    assert channel_streams[0].stream.stream_kind == StreamKind.MEDIA_PLAYLIST.value
    assert len(variants) == 1
    assert variants[0].resolution_width == 1280
    assert variants[0].resolution_height == 720


def test_import_same_content_creates_no_second_version() -> None:
    session = make_session()
    playlist = "#EXTM3U\n#EXTINF:-1,News\nhttps://example.test/news.m3u8\n"
    importer = PlaylistImporter(discovery=FakeDiscovery())

    first = importer.import_text(session, "Test Playlist", playlist)
    second = importer.import_text(session, "Test Playlist", playlist)

    assert first.version_number == 1
    assert second.version_number == 1
    assert second.identical_version is True
    assert len(session.scalars(select(PlaylistEntry)).all()) == 1


def test_import_deduplicates_discovery_for_repeated_url() -> None:
    session = make_session()
    discovery = CountingDiscovery()
    playlist = (
        "#EXTM3U\n"
        "#EXTINF:-1,Channel One\nhttps://example.test/live.m3u8\n"
        "#EXTINF:-1,Channel Two\nhttps://EXAMPLE.test:443/live.m3u8\n"
    )

    result = PlaylistImporter(discovery=discovery).import_text(
        session, "Test Playlist", playlist
    )

    assert result.entries == 2
    assert result.duplicate_urls == 1
    assert discovery.calls == ["https://example.test/live.m3u8"]
    assert len(session.scalars(select(Stream)).all()) == 1


def test_import_reports_progress_stages_and_entry_counts() -> None:
    session = make_session()
    playlist = (
        "#EXTM3U\n"
        "#EXTINF:-1,Channel One\nhttps://example.test/live-one.m3u8\n"
        "#EXTINF:-1,Channel Two\nhttps://example.test/live-two.m3u8\n"
    )
    events: list[tuple[str, int, int, str]] = []

    class PerUrlDiscovery(CountingDiscovery):
        def discover(self, url: str) -> list[DiscoveryResult]:
            self.calls.append(url)
            return [
                DiscoveryResult(
                    url=url,
                    final_url=url,
                    kind=StreamKind.MEDIA_PLAYLIST,
                    content_type="application/vnd.apple.mpegurl",
                    http_status=200,
                    parent_url=None,
                    depth=0,
                )
            ]

    result = PlaylistImporter(discovery=PerUrlDiscovery()).import_text(
        session,
        "Progress Playlist",
        playlist,
        progress=lambda stage, current, total, message: events.append(
            (stage, current, total, message)
        ),
    )

    stages = [event[0] for event in events]
    assert stages[0] == "parsing"
    assert "parsed" in stages
    assert "discovering" in stages
    assert "saving" in stages
    assert stages[-1] == "complete"
    assert events[-1][1:3] == (2, 2)
    assert result.entries == 2
