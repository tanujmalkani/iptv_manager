from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Channel, ChannelStream, PlaylistEntry, SourcePlaylist, SourcePlaylistVersion, Stream, StreamTest, TestRun
from app.db.session import get_db
from app.main import app


def make_client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session


def test_channels_api_preserves_latest_playlist_order() -> None:
    client, session = make_client()
    try:
        playlist = SourcePlaylist(
            name="Ordered Playlist",
            source_type="text",
            source_location="test",
            entry_count=2,
        )
        version = SourcePlaylistVersion(
            source_playlist=playlist,
            version_number=1,
            content_hash="o" * 64,
            entry_count=2,
            status="completed",
        )
        first = Channel(canonical_name="Zulu News", normalized_name="zulu news")
        second = Channel(canonical_name="Alpha Sports", normalized_name="alpha sports")
        first_stream = Stream(
            url="https://example.test/zulu.m3u8",
            normalized_url="https://example.test/zulu.m3u8",
            stream_kind="media_playlist",
        )
        second_stream = Stream(
            url="https://example.test/alpha.m3u8",
            normalized_url="https://example.test/alpha.m3u8",
            stream_kind="media_playlist",
        )
        session.add_all([playlist, version, first, second, first_stream, second_stream])
        session.flush()
        session.add_all(
            [
                ChannelStream(channel_id=first.id, stream_id=first_stream.id),
                ChannelStream(channel_id=second.id, stream_id=second_stream.id),
                PlaylistEntry(
                    source_playlist_version_id=version.id,
                    channel_id=first.id,
                    stream_id=first_stream.id,
                    original_position=0,
                    raw_extinf="#EXTINF:-1,Zulu News",
                ),
                PlaylistEntry(
                    source_playlist_version_id=version.id,
                    channel_id=second.id,
                    stream_id=second_stream.id,
                    original_position=1,
                    raw_extinf="#EXTINF:-1,Alpha Sports",
                ),
            ]
        )
        test_run = TestRun(name="Order Test", profile="quick", status="completed")
        session.add(test_run)
        session.flush()
        now = datetime.now(UTC).replace(tzinfo=None)
        session.add_all(
            [
                StreamTest(
                    test_run_id=test_run.id,
                    stream_id=first_stream.id,
                    attempt_number=1,
                    test_type="quick",
                    result="success",
                    started_at=now,
                    completed_at=now,
                    available=True,
                    first_frame_ms=100.0,
                    extra_metrics={"stable": True},
                ),
                StreamTest(
                    test_run_id=test_run.id,
                    stream_id=second_stream.id,
                    attempt_number=1,
                    test_type="quick",
                    result="success",
                    started_at=now,
                    completed_at=now,
                    available=True,
                    first_frame_ms=100.0,
                    extra_metrics={"stable": True},
                ),
            ]
        )
        session.commit()

        response = client.get(f"/api/channels?source_playlist_id={playlist.id}")

        assert response.status_code == 200
        assert [item["channel_name"] for item in response.json()] == [
            "Zulu News",
            "Alpha Sports",
        ]
    finally:
        app.dependency_overrides.clear()
        session.close()
