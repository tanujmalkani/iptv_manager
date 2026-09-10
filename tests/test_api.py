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


def test_frontend_and_health_are_served() -> None:
    client, session = make_client()
    try:
        assert client.get("/").status_code == 200
        assert "IPTV Manager" in client.get("/").text
        assert client.get("/frontend/app.js").status_code == 200
        assert client.get("/frontend/styles.css").status_code == 200
        assert client.get("/health").json() == {"status": "ok"}
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_source_playlist_api_returns_latest_completed_version() -> None:
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
        session.add_all(
            [
                SourcePlaylistVersion(
                    source_playlist_id=playlist.id,
                    version_number=1,
                    content_hash="a" * 64,
                    entry_count=2,
                    status="completed",
                ),
                SourcePlaylistVersion(
                    source_playlist_id=playlist.id,
                    version_number=2,
                    content_hash="b" * 64,
                    entry_count=3,
                    status="completed",
                ),
                SourcePlaylistVersion(
                    source_playlist_id=playlist.id,
                    version_number=3,
                    content_hash="c" * 64,
                    entry_count=4,
                    status="importing",
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
    started: list[tuple[int, str]] = []

    def fake_start(test_run_id, source_playlist_id, test_type, timeout, duration, ffmpeg):
        started.append((test_run_id, test_type))

    monkeypatch.setattr("app.api.testing._start_background_test", fake_start)
    try:
        quick = client.post("/api/stream-tests")
        assert quick.status_code == 200
        quick_run = session.get(TestRun, quick.json()["test_run_id"])
        assert quick_run is not None
        assert quick_run.profile == "quick"
        assert quick_run.configuration_json["test_type"] == "quick"
        assert "playback_duration_seconds" not in quick_run.configuration_json

        deep = client.post("/api/stream-tests?test_type=deep&playback_duration_seconds=5")
        assert deep.status_code == 200
        deep_run = session.get(TestRun, deep.json()["test_run_id"])
        assert deep_run is not None
        assert deep_run.profile == "deep"
        assert deep_run.configuration_json["test_type"] == "deep"
        assert deep_run.configuration_json["playback_duration_seconds"] == 5.0
        assert started == [
            (quick_run.id, "quick"),
            (deep_run.id, "deep"),
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
        test_run = TestRun(name="Stream Test", profile="quick", status="completed")
        session.add(test_run)
        session.flush()
        session.add(
            StreamTest(
                test_run_id=test_run.id,
                stream_id=stream.id,
                attempt_number=1,
                test_type="quick",
                result="success",
                started_at=datetime.now(UTC).replace(tzinfo=None),
                completed_at=datetime.now(UTC).replace(tzinfo=None),
                available=True,
                first_frame_ms=250.0,
                extra_metrics={
                    "playback_duration_ms": 10_000.0,
                    "observed_fps": 25.0,
                    "stable": True,
                },
            )
        )
        session.commit()

        summaries = client.get("/api/channels")
        assert summaries.status_code == 200
        assert summaries.json()[0]["channel_name"] == "News"
        assert summaries.json()[0]["primary_stream_id"] == stream.id

        detail = client.get(f"/api/channels/{channel.id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["primary_stream_id"] == stream.id
        assert body["streams"][0]["is_primary"] is True
        assert body["streams"][0]["performance"]["median_first_frame_ms"] == 250.0

        stream_performance = client.get(f"/api/streams/{stream.id}/performance")
        assert stream_performance.status_code == 200
        assert stream_performance.json()["success_rate"] == 1.0
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_optimized_m3u_export_uses_primary_stream_and_preserves_metadata() -> None:
    client, session = make_client()
    try:
        playlist = SourcePlaylist(
            name="Test Playlist",
            source_type="text",
            source_location="test",
        )
        version = SourcePlaylistVersion(
            source_playlist=playlist,
            version_number=1,
            content_hash="a" * 64,
            entry_count=1,
            original_header="#EXTM3U x-tvg-url=\"https://epg.test/guide.xml\"",
            status="completed",
        )
        channel = Channel(canonical_name="News", normalized_name="news")
        original = Stream(
            url="https://example.test/original.m3u8",
            normalized_url="https://example.test/original.m3u8",
            stream_kind="media_playlist",
        )
        faster = Stream(
            url="https://example.test/fast.m3u8",
            normalized_url="https://example.test/fast.m3u8",
            stream_kind="media_playlist",
        )
        session.add_all([playlist, version, channel, original, faster])
        session.flush()
        session.add_all(
            [
                ChannelStream(channel_id=channel.id, stream_id=original.id),
                ChannelStream(channel_id=channel.id, stream_id=faster.id),
                PlaylistEntry(
                    source_playlist_version_id=version.id,
                    channel_id=channel.id,
                    stream_id=original.id,
                    original_position=0,
                    original_name="News HD",
                    original_group="News",
                    original_tvg_id="news.uk",
                    original_attributes={
                        "tvg-id": "news.uk",
                        "group-title": "News",
                    },
                    original_directives=["#EXTVLCOPT:http-referrer=https://example.test"],
                    raw_extinf=(
                        '#EXTINF:-1 tvg-id="news.uk" group-title="News",News HD'
                    ),
                ),
            ]
        )
        test_run = TestRun(name="Stream Test", profile="quick", status="completed")
        session.add(test_run)
        session.flush()
        session.add(
            StreamTest(
                test_run_id=test_run.id,
                stream_id=faster.id,
                attempt_number=1,
                test_type="quick",
                result="success",
                started_at=datetime.now(UTC).replace(tzinfo=None),
                completed_at=datetime.now(UTC).replace(tzinfo=None),
                available=True,
                first_frame_ms=100.0,
            )
        )
        session.commit()

        response = client.get(f"/api/source-playlists/{playlist.id}/optimized.m3u")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/x-mpegurl")
        assert response.headers["content-disposition"].endswith('"')
        assert response.text == (
            '#EXTM3U x-tvg-url="https://epg.test/guide.xml"\n'
            "#EXTVLCOPT:http-referrer=https://example.test\n"
            '#EXTINF:-1 tvg-id="news.uk" group-title="News",News HD\n'
            "https://example.test/fast.m3u8\n"
        )
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_export_returns_404_when_completed_version_is_missing() -> None:
    client, session = make_client()
    try:
        assert client.get("/api/source-playlists/999/optimized.m3u").status_code == 404
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_performance_api_returns_404_for_unknown_resources() -> None:
    client, session = make_client()
    try:
        assert client.get("/api/channels/999").status_code == 404
        assert client.get("/api/streams/999/performance").status_code == 404
    finally:
        app.dependency_overrides.clear()
        session.close()
