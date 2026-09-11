from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Channel, ChannelStream, SourcePlaylist, SourcePlaylistVersion, Stream, StreamTest, TestRun
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


def test_source_playlist_api_returns_latest_version() -> None:
    client, session = make_client()
    try:
        playlist = SourcePlaylist(name="Test Playlist", source_type="text", source_location="test")
        session.add(playlist)
        session.flush()
        session.add_all(
            [
                SourcePlaylistVersion(
                    source_playlist_id=playlist.id,
                    version_number=1,
                    content_hash="hash-1",
                    entry_count=2,
                    status="completed",
                ),
                SourcePlaylistVersion(
                    source_playlist_id=playlist.id,
                    version_number=2,
                    content_hash="hash-2",
                    entry_count=3,
                    status="completed",
                ),
            ]
        )
        session.commit()

        response = client.get("/api/source-playlists")
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": playlist.id,
                "name": "Test Playlist",
                "source_type": "text",
                "source_location": "test",
                "entry_count": 2,
                "latest_version_id": playlist.versions[1].id,
                "latest_version_number": 2,
                "latest_version_entry_count": 3,
            }
        ]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_stream_test_api_defaults_to_quick_and_supports_deep(monkeypatch) -> None:
    client, session = make_client()
    started: list[tuple[int, str, int]] = []

    def fake_start(test_run_id, source_playlist_id, test_type, timeout, duration, ffmpeg, concurrency):
        started.append((test_run_id, test_type, concurrency))

    monkeypatch.setattr("app.api.testing._start_background_test", fake_start)
    try:
        quick = client.post("/api/stream-tests")
        assert quick.status_code == 200
        quick_run = session.get(TestRun, quick.json()["test_run_id"])
        assert quick_run is not None
        assert quick_run.profile == "quick"
        assert quick_run.configuration_json["test_type"] == "quick"
        assert quick_run.configuration_json["concurrency"] == 4
        assert "playback_duration_seconds" not in quick_run.configuration_json

        deep = client.post("/api/stream-tests?test_type=deep&playback_duration_seconds=5&concurrency=8")
        assert deep.status_code == 200
        deep_run = session.get(TestRun, deep.json()["test_run_id"])
        assert deep_run is not None
        assert deep_run.profile == "deep"
        assert deep_run.configuration_json["test_type"] == "deep"
        assert deep_run.configuration_json["playback_duration_seconds"] == 5.0
        assert deep_run.configuration_json["concurrency"] == 8
        assert started == [
            (quick_run.id, "quick", 4),
            (deep_run.id, "deep", 8),
        ]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_performance_api_returns_channel_and_stream_metrics() -> None:
    client, session = make_client()
    try:
        channel = Channel(canonical_name="News", normalized_name="news")
        stream = Stream(
            url="https://example.test/news.m3u8",
            normalized_url="https://example.test/news.m3u8",
            stream_kind="media_playlist",
        )
        session.add_all([channel, stream])
        session.flush()
        session.add(ChannelStream(channel_id=channel.id, stream_id=stream.id))
        session.commit()
        response = client.get(f"/api/channels/{channel.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["channel_id"] == channel.id
        assert body["streams"][0]["stream_id"] == stream.id
    finally:
        app.dependency_overrides.clear()
        session.close()
