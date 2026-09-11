from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Channel,
    ChannelStream,
    PlaylistEntry,
    SourcePlaylist,
    SourcePlaylistVersion,
    Stream,
    StreamTest,
    TestRun,
)
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


def test_optimization_preview_returns_profile_scoring_and_primary() -> None:
    client, session = make_client()
    try:
        playlist = SourcePlaylist(
            name="Test Playlist",
            source_type="text",
            source_location="test",
            entry_count=2,
        )
        session.add(playlist)
        session.flush()
        version = SourcePlaylistVersion(
            source_playlist_id=playlist.id,
            version_number=1,
            content_hash="a" * 64,
            entry_count=2,
            status="completed",
        )
        channel = Channel(canonical_name="News", normalized_name="news")
        fast = Stream(
            url="https://example.test/fast.m3u8",
            normalized_url="https://example.test/fast.m3u8",
            stream_kind="media_playlist",
        )
        slow = Stream(
            url="https://example.test/slow.m3u8",
            normalized_url="https://example.test/slow.m3u8",
            stream_kind="media_playlist",
        )
        session.add_all([version, channel, fast, slow])
        session.flush()
        session.add_all(
            [
                ChannelStream(channel_id=channel.id, stream_id=fast.id),
                ChannelStream(channel_id=channel.id, stream_id=slow.id),
                PlaylistEntry(
                    source_playlist_version_id=version.id,
                    channel_id=channel.id,
                    stream_id=fast.id,
                    original_position=0,
                    raw_extinf="#EXTINF:-1,News",
                ),
                PlaylistEntry(
                    source_playlist_version_id=version.id,
                    channel_id=channel.id,
                    stream_id=slow.id,
                    original_position=1,
                    raw_extinf="#EXTINF:-1,News",
                ),
            ]
        )
        test_run = TestRun(name="Optimization Test", profile="quick", status="completed")
        session.add(test_run)
        session.flush()
        now = datetime.now(UTC).replace(tzinfo=None)
        session.add_all(
            [
                StreamTest(
                    test_run_id=test_run.id,
                    stream_id=fast.id,
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
                    stream_id=slow.id,
                    attempt_number=1,
                    test_type="quick",
                    result="success",
                    started_at=now,
                    completed_at=now,
                    available=True,
                    first_frame_ms=500.0,
                    extra_metrics={"stable": True},
                ),
            ]
        )
        session.commit()

        response = client.get(
            f"/api/source-playlists/{playlist.id}/optimization?profile=fast"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["profile"] == "fast"
        assert body["version_number"] == 1
        assert body["policy"]["speed_weight"] == 0.5
        assert body["channels"][0]["channel_name"] == "News"
        assert body["channels"][0]["primary_stream_id"] == fast.id
        assert body["channels"][0]["candidates"][0]["stream_id"] == fast.id
        assert (
            body["channels"][0]["candidates"][0]["speed_score"]
            > body["channels"][0]["candidates"][1]["speed_score"]
        )
    finally:
        app.dependency_overrides.clear()
        session.close()
