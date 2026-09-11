from __future__ import annotations

from app.db.models import TestRun


def test_stream_test_api_defaults_to_quick_and_supports_deep(monkeypatch) -> None:
    client, session = make_client()
    started: list[tuple[int, str, int]] = []

    def fake_start(
        test_run_id,
        source_playlist_id,
        test_type,
        timeout,
        duration,
        ffmpeg,
        concurrency,
    ):
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

        deep = client.post(
            "/api/stream-tests?test_type=deep&playback_duration_seconds=5&concurrency=8"
        )
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
