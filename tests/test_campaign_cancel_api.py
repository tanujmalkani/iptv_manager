from threading import Event

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.testing as testing_api
from app.db.models import Base, TestRun
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


def test_cancel_stream_test_api_sets_cancellation_event(monkeypatch) -> None:
    client, session = make_client()
    event = Event()
    try:
        def fake_start(test_run_id, *args):
            with testing_api._cancel_events_lock:
                testing_api._cancel_events[test_run_id] = event

        monkeypatch.setattr("app.api.testing._start_background_test", fake_start)
        response = client.post("/api/stream-tests")
        assert response.status_code == 200
        test_run_id = response.json()["test_run_id"]
        assert session.get(TestRun, test_run_id) is not None

        cancelled = client.post(f"/api/stream-tests/{test_run_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json() == {
            "test_run_id": test_run_id,
            "status": "cancellation_requested",
        }
        assert event.is_set()
    finally:
        with testing_api._cancel_events_lock:
            testing_api._cancel_events.clear()
        app.dependency_overrides.clear()
        session.close()


def test_cancel_stream_test_api_rejects_finished_run() -> None:
    client, session = make_client()
    try:
        test_run = TestRun(name="Finished", profile="quick", status="completed")
        session.add(test_run)
        session.commit()
        response = client.post(f"/api/stream-tests/{test_run.id}/cancel")
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()
        session.close()
