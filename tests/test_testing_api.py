from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Channel, ChannelStream, Stream
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


def add_stream(session: Session) -> None:
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


def test_start_quick_stream_test_creates_pending_run(monkeypatch) -> None:
    client, session = make_client()
    try:
        add_stream(session)
        monkeypatch.setattr(
            "app.api.testing._start_background_test",
            lambda *args: None,
        )
        response = client.post(
            "/api/stream-tests",
            params={"timeout_seconds": 5},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["test_run_id"] > 0

        run_response = client.get(f"/api/stream-tests/{body['test_run_id']}")
        assert run_response.status_code == 200
        run = run_response.json()
        assert run["status"] == "pending"
        assert run["total_streams"] == 1
        assert run["completed_streams"] == 0
        assert run["configuration"]["test_type"] == "quick"
        assert run["configuration"]["timeout_seconds"] == 5
        assert "playback_duration_seconds" not in run["configuration"]
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_start_deep_stream_test_persists_playback_duration(monkeypatch) -> None:
    client, session = make_client()
    try:
        add_stream(session)
        monkeypatch.setattr(
            "app.api.testing._start_background_test",
            lambda *args: None,
        )
        response = client.post(
            "/api/stream-tests",
            params={
                "test_type": "deep",
                "timeout_seconds": 5,
                "playback_duration_seconds": 2,
            },
        )

        assert response.status_code == 200
        body = response.json()
        run_response = client.get(f"/api/stream-tests/{body['test_run_id']}")
        run = run_response.json()
        assert run["configuration"]["test_type"] == "deep"
        assert run["configuration"]["playback_duration_seconds"] == 2
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_start_stream_test_rejects_invalid_duration() -> None:
    client, session = make_client()
    try:
        response = client.post("/api/stream-tests?timeout_seconds=0")
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_stream_test_run_returns_404_for_unknown_run() -> None:
    client, session = make_client()
    try:
        assert client.get("/api/stream-tests/999").status_code == 404
    finally:
        app.dependency_overrides.clear()
        session.close()
