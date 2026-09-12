from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import get_db
from app.importer.job import create_import_job
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


def test_import_api_returns_job_and_exposes_progress(monkeypatch) -> None:
    client, session = make_client()
    job = create_import_job()

    def fake_start_import_job(name: str, text: str, source_location: str | None):
        assert name == "Test Playlist"
        assert text.startswith("#EXTM3U")
        assert source_location == "https://example.test/playlist.m3u"
        return job

    monkeypatch.setattr("app.api.playlists.start_import_job", fake_start_import_job)
    try:
        response = client.post(
            "/api/source-playlists/import",
            json={
                "name": "Test Playlist",
                "text": "#EXTM3U\n#EXTINF:-1,News\nhttps://example.test/news.m3u8\n",
                "source_location": "https://example.test/playlist.m3u",
            },
        )
        assert response.status_code == 200
        assert response.json() == {"import_id": job.id, "status": "pending"}

        progress = client.get(f"/api/source-playlists/import/{job.id}")
        assert progress.status_code == 200
        body = progress.json()
        assert body["id"] == job.id
        assert body["status"] == "pending"
        assert body["stage"] == "queued"
        assert body["result"] is None
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_import_api_returns_404_for_unknown_job() -> None:
    client, session = make_client()
    try:
        response = client.get("/api/source-playlists/import/not-a-real-job")
        assert response.status_code == 404
        assert response.json()["detail"] == "Import job not found"
    finally:
        app.dependency_overrides.clear()
        session.close()
