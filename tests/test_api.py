from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, Channel, ChannelStream, Stream, StreamTest, TestRun
from app.db.session import get_db
from app.main import app


def make_client() -> tuple[TestClient, Session]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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


def test_performance_api_returns_404_for_unknown_resources() -> None:
    client, session = make_client()
    try:
        assert client.get("/api/channels/999").status_code == 404
        assert client.get("/api/streams/999/performance").status_code == 404
    finally:
        app.dependency_overrides.clear()
        session.close()
