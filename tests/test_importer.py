import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, Channel, PlaylistEntry, Stream, StreamVariant
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
    variants = session.scalars(select(StreamVariant)).all()
    assert len(entries) == 1
    assert len(streams) == 2
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
